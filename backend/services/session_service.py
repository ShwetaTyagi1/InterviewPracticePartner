# services/session_service.py
"""
Session service - provides:
- session lifecycle: create_session, delete_all_sessions, get_session, touch_session
- single-session helpers: _get_single_session_doc, _ensure_session_exists
- question flow: start_question_for_session
- answer routing: route_answer_for_session
- answer evaluation: _evaluate_answer_with_gemini, check_main_answer, check_followup_answer

Note: This file uses the Google GenAI SDK via services.gemini_client.call_gemini.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pymongo.collection import Collection
from pydantic import ValidationError
import logging
import uuid
import os
import json

from db import db  # expects db to expose the pymongo database handle
from models.session_model import SessionModel
from services.gemini_client import call_gemini

logger = logging.getLogger(__name__)

# Configurable: how many minutes until session TTL expires (db.py also uses SESSION_TTL_MINUTES env)
from os import getenv
SESSION_TTL_MINUTES = int(getenv("SESSION_TTL_MINUTES", "30"))


# --- collection helper ---
def _sessions_collection() -> Collection:
    return db.get_collection("sessions")


# -------------------------
# Session lifecycle
# -------------------------
def create_session(target_role: Optional[str] = None, experience_level: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a new session document and insert it into MongoDB.
    Returns the inserted session document as a plain dict (BSON-like).
    """
    # Instantiate a Pydantic SessionModel (gives defaults and timestamps)
    session = SessionModel.new_session(target_role=target_role, experience_level=experience_level)

    # Ensure TTL is set/updated
    session.ttl_expires_at = datetime.utcnow() + timedelta(minutes=SESSION_TTL_MINUTES)
    session.last_activity_at = datetime.utcnow()

    # Convert to dict for Mongo insertion
    session_doc = session.to_bson()

    col = _sessions_collection()
    res = col.insert_one(session_doc)
    logger.info("Created new session with id=%s (inserted_id=%s)", session_doc.get("_id"), res.inserted_id)

    # Return the stored session as a Python dict
    return session_doc


def delete_all_sessions() -> int:
    """
    Delete all session documents. Returns the count of deleted documents.
    Useful because your app is single-user and wants to clear sessions
    when the base URL is visited.
    """
    col = _sessions_collection()
    result = col.delete_many({})
    logger.info("Deleted %d sessions from sessions collection.", result.deleted_count)
    return result.deleted_count


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a session by its _id field (session._id).
    Returns None if not found.
    """
    col = _sessions_collection()
    doc = col.find_one({"_id": session_id})
    return doc


def touch_session(session_id: str) -> bool:
    """
    Update last_activity_at and extend ttl_expires_at for the given session.
    Returns True if the session was found and updated, False otherwise.
    """
    col = _sessions_collection()
    new_ttl = datetime.utcnow() + timedelta(minutes=SESSION_TTL_MINUTES)
    result = col.update_one(
        {"_id": session_id},
        {"$set": {"last_activity_at": datetime.utcnow(), "ttl_expires_at": new_ttl}}
    )
    return result.matched_count == 1


# -------------------------
# Single-session helpers
# -------------------------
def _get_single_session_doc() -> Optional[Dict[str, Any]]:
    """
    Return the single (most recent) session document, or None if none exists.
    """
    col = _sessions_collection()
    return col.find_one(sort=[("created_at", -1)])


def _ensure_session_exists() -> Dict[str, Any]:
    """
    Ensure there is a session document. If none exists, create a fresh one.
    Returns the session document (as stored in Mongo).
    """
    sessions = _sessions_collection()
    session = _get_single_session_doc()
    if session:
        # Touch/extend TTL on reuse
        try:
            session_id = session["_id"]
            touch_session(session_id)
        except Exception:
            pass
        return session

    # Create new session document using Pydantic helper
    new_session = SessionModel.new_session()
    # set TTL and timestamps explicitly
    new_session.ttl_expires_at = datetime.utcnow() + timedelta(minutes=SESSION_TTL_MINUTES)
    new_session.last_activity_at = datetime.utcnow()
    doc = new_session.to_bson()
    res = sessions.insert_one(doc)
    logger.info("Inserted new single session (inserted_id=%s)", res.inserted_id)
    # Return freshly inserted doc (with _id from doc)
    return doc


def _pick_random_question() -> Optional[Dict[str, Any]]:
    """
    Pick a random question document from the questions collection using $sample.
    Returns the question doc or None if the collection is empty.
    """
    qcol = db.get_collection("questions")
    cursor = qcol.aggregate([{"$sample": {"size": 1}}])
    try:
        question = next(cursor, None)
    except StopIteration:
        question = None
    return question


# -------------------------
# Business: start a question for session
# -------------------------
def start_question_for_session() -> Dict[str, Any]:
    """
    Pick a random question, store it as the current_question in the single session,
    and return the question prompt + rubric + q_id to be sent to the frontend.

    Returns dict: { "reply": str, "question": str, "rubric": [str], "q_id": str }
    Raises RuntimeError if no questions are available.
    """
    sessions_col = _sessions_collection()
    questions_col = db.get_collection("questions")

    # Ensure a session exists
    session = _ensure_session_exists()
    session_id = session.get("_id")

    # Pick a random question
    question = _pick_random_question()
    if not question:
        logger.error("No questions found in questions collection.")
        raise RuntimeError("No questions available in the question bank.")

    # Build current_question payload
    q_id = str(question.get("_id"))
    prompt_text = question.get("prompt", "")
    rubric = question.get("rubric", []) or []
    q_type = question.get("type", "conceptual")

    current_question = {
        "q_id": q_id,
        "prompt": prompt_text,
        "rubric": rubric,
        "type": q_type,
        "turn_type": "main",     # starts as the main question
        "assigned_at": datetime.utcnow()
    }

    # Create a new Turn entry to track this question being asked
    turn_doc = {
        "turn_id": f"turn_{uuid.uuid4().hex[:8]}",
        "q_id": q_id,
        "turn_type": "main",
        "q_text": prompt_text,
        "answer_text": None,
        "timestamp": datetime.utcnow(),
        "feedback": None,
        "classification": None,
        "confidence": None
    }

    # Update session in DB: set current_question, push to turns, append question_asked, update timestamps
    update_ops = {
        "$set": {
            "current_question": current_question,
            "last_activity_at": datetime.utcnow()
        },
        "$push": {
            "turns": turn_doc,
            "questions_asked": q_id
        }
    }

    sessions_col.update_one({"_id": session_id}, update_ops)

    # Optionally return an updated session doc (new current_question) - but return minimal payload for frontend.
    return {
        "reply": prompt_text,   # the text to show the user (question prompt)
        "question": prompt_text,
        "rubric": rubric,
        "q_id": q_id
    }


# -------------------------
# Answer routing helper (in-session)
# -------------------------
def route_answer_for_session(user_answer: str) -> Dict[str, Any]:
    """
    Inspect the single session's current_question and return a routing dict indicating
    whether this user_answer should be handled by the main-answer handler or the
    followup-answer handler.

    Assumptions: per your instruction, a question is guaranteed to have been asked previously,
    so current_question exists and has a valid turn_type ("main" or "followup").

    Returns a dict:
    {
        "handler": "check_main_answer" | "check_followup_answer",
        "q_type": "main" | "followup",
        "q_id": "<question id>",
        "question_text": "<prompt text>",
        "session_id": "<session _id>",
        "user_answer": "<user_answer>",
    }
    """
    session = _get_single_session_doc()
    if not session:
        logger.error("route_answer_for_session called but no active session found.")
        return {
            "handler": "no_active_session",
            "q_type": None,
            "q_id": None,
            "question_text": None,
            "session_id": None,
            "user_answer": user_answer,
        }

    session_id = session.get("_id")
    current_q = session.get("current_question", {})

    # Per guarantee, current_q exists and has turn_type
    turn_type = current_q.get("turn_type")
    q_id = current_q.get("q_id")
    q_text = current_q.get("prompt") or current_q.get("q_text") or ""

    if turn_type == "main":
        handler = "check_main_answer"
        q_type = "main"
    else:
        handler = "check_followup_answer"
        q_type = "followup"

    return {
        "handler": handler,
        "q_type": q_type,
        "q_id": q_id,
        "question_text": q_text,
        "session_id": session_id,
        "user_answer": user_answer,
    }


# -------------------------
# Evaluation via Gemini
# -------------------------
EVAL_PROMPT_TEMPLATE = """
You are an expert interview evaluator. Given a question, its rubric, and a candidate's answer,
produce STRICT JSON (no surrounding text) with exactly these fields:

{{
  "feedback": "<a concise human-readable critique of the answer (what was good, what was missing)>",
  "classification": "<one of: correct | somewhat_correct | wrong>",
  "confidence": <float between 0.0 and 1.0>
}}

Rules:
- Do NOT provide the solution or step-by-step hints.
- Judge the answer against the rubric items. If the answer satisfies most rubric points, mark 'correct'.
- If the answer partially matches or is incomplete, mark 'somewhat_correct'.
- If the answer is incorrect or irrelevant, mark 'wrong'.
- Confidence should reflect your estimate of correctness (0.0 - 1.0).
- Keep feedback practical and actionable (mention which rubric points are satisfied / missing).

Context:
Question:
\"\"\"{question_text}\"\"\"

Rubric:
{rubric_json}

Candidate answer:
\"\"\"{candidate_answer}\"\"\"
"""


def _evaluate_answer_with_gemini(question_text: str, rubric: List[str], candidate_answer: str) -> Dict[str, Any]:
    """
    Call Gemini to evaluate the candidate's answer. Returns dict with keys:
    - feedback (str)
    - classification (str) in {"correct","somewhat_correct","wrong"}
    - confidence (float)
    If LLM fails or returns invalid output, returns a conservative fallback.
    """
    prompt = EVAL_PROMPT_TEMPLATE.format(
        question_text=question_text.replace('"', '\\"'),
        rubric_json=json.dumps(rubric or []),
        candidate_answer=candidate_answer.replace('"', '\\"'),
    )

    try:
        raw = call_gemini(prompt=prompt, model="gemini-2.0-flash", max_tokens=400, temperature=0.0)
    except Exception as e:
        logger.exception("Gemini evaluation call failed: %s", e)
        return {
            "feedback": "Evaluation service currently unavailable. Please try again later.",
            "classification": "somewhat_correct",
            "confidence": 0.0
        }

    # Parse JSON strictly; try substring extraction if needed
    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        # try to extract JSON substring
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            parsed = json.loads(raw[start:end])
        except Exception as e:
            logger.exception("Failed to parse Gemini eval output: %s; raw output: %s", e, raw)
            return {
                "feedback": "Received invalid evaluation output from evaluator.",
                "classification": "somewhat_correct",
                "confidence": 0.0
            }

    # Validate fields
    feedback = parsed.get("feedback", "").strip() if isinstance(parsed.get("feedback", ""), str) else str(parsed.get("feedback", ""))
    classification = parsed.get("classification", "")
    confidence = parsed.get("confidence", 0.0)

    # Normalize and validate classification
    if classification not in ("correct", "somewhat_correct", "wrong"):
        logger.warning("Unexpected classification from Gemini: %s", classification)
        classification = "somewhat_correct"

    # Coerce confidence to float and clamp
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "feedback": feedback,
        "classification": classification,
        "confidence": confidence
    }


# -------------------------
# Update helpers
# -------------------------
def _update_session_doc(session_id: str, new_doc: Dict[str, Any]) -> None:
    col = _sessions_collection()
    col.replace_one({"_id": session_id}, new_doc)


# -------------------------
# Public functions to check answers and update session
# -------------------------
def check_main_answer(user_answer: str) -> Dict[str, Any]:
    """
    Evaluate the user's answer for the current MAIN question, update the last turn and session,
    set current_question.turn_type to 'followup', and increment main_questions_answered.
    Returns the evaluation dict returned by the LLM.
    """
    session = _get_single_session_doc()
    if not session:
        raise RuntimeError("No active session")

    session_id = session.get("_id")
    current_q = session.get("current_question", {})
    question_text = current_q.get("prompt", "")
    rubric = current_q.get("rubric", []) or []

    # Evaluate via Gemini
    evaluation = _evaluate_answer_with_gemini(question_text=question_text, rubric=rubric, candidate_answer=user_answer)

    # Update last turn in session.turns (update the last element)
    turns = session.get("turns", []) or []
    if not turns:
        # Defensive: if no turn exists, create one
        turn = {
            "turn_id": f"turn_{uuid.uuid4().hex[:8]}",
            "q_id": current_q.get("q_id"),
            "turn_type": "main",
            "q_text": question_text,
            "answer_text": user_answer,
            "timestamp": datetime.utcnow(),
            "feedback": evaluation,
        }
        turns.append(turn)
    else:
        last_turn = turns[-1]
        last_turn["answer_text"] = user_answer
        last_turn["timestamp"] = datetime.utcnow()
        last_turn["feedback"] = evaluation
        turns[-1] = last_turn

    # Update session fields: set current_question.turn_type -> followup; increment main_questions_answered
    session["turns"] = turns
    session["current_question"]["turn_type"] = "followup"
    session["main_questions_answered"] = int(session.get("main_questions_answered", 0)) + 1
    session["last_activity_at"] = datetime.utcnow()

    # Persist by replacing document (single-user app; this is acceptable)
    _update_session_doc(session_id, session)

    return evaluation


def check_followup_answer(user_answer: str) -> Dict[str, Any]:
    """
    Evaluate the user's answer for the current FOLLOWUP question, update the last turn and session,
    clear current_question and increment followups_answered.
    Returns the evaluation dict returned by the LLM.
    """
    session = _get_single_session_doc()
    if not session:
        raise RuntimeError("No active session")

    session_id = session.get("_id")
    current_q = session.get("current_question", {})
    question_text = current_q.get("prompt", "")
    rubric = current_q.get("rubric", []) or []

    # Evaluate via Gemini
    evaluation = _evaluate_answer_with_gemini(question_text=question_text, rubric=rubric, candidate_answer=user_answer)

    # Update last turn
    turns = session.get("turns", []) or []
    if not turns:
        turn = {
            "turn_id": f"turn_{uuid.uuid4().hex[:8]}",
            "q_id": current_q.get("q_id"),
            "turn_type": "followup",
            "q_text": question_text,
            "answer_text": user_answer,
            "timestamp": datetime.utcnow(),
            "feedback": evaluation,
        }
        turns.append(turn)
    else:
        last_turn = turns[-1]
        last_turn["answer_text"] = user_answer
        last_turn["timestamp"] = datetime.utcnow()
        # For followup, we might append feedback or merge it; here we replace feedback fields
        last_turn["feedback"] = evaluation
        turns[-1] = last_turn

    # Update session: clear current_question and increment followups_answered
    session["turns"] = turns
    session["current_question"] = None
    session["followups_answered"] = int(session.get("followups_answered", 0)) + 1
    session["last_activity_at"] = datetime.utcnow()

    _update_session_doc(session_id, session)

    return evaluation
