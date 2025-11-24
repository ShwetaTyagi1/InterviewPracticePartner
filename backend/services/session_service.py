# services/session_service.py
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
    session = SessionModel.new_session(target_role=target_role, experience_level=experience_level)
    session.ttl_expires_at = datetime.utcnow() + timedelta(minutes=SESSION_TTL_MINUTES)
    session.last_activity_at = datetime.utcnow()
    session_doc = session.to_bson()
    col = _sessions_collection()
    res = col.insert_one(session_doc)
    logger.info("Created new session with id=%s (inserted_id=%s)", session_doc.get("_id"), res.inserted_id)
    return session_doc


def delete_all_sessions() -> int:
    col = _sessions_collection()
    result = col.delete_many({})
    logger.info("Deleted %d sessions from sessions collection.", result.deleted_count)
    return result.deleted_count


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    col = _sessions_collection()
    doc = col.find_one({"_id": session_id})
    return doc


def touch_session(session_id: str) -> bool:
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
    col = _sessions_collection()
    return col.find_one(sort=[("created_at", -1)])


def _ensure_session_exists() -> Dict[str, Any]:
    sessions = _sessions_collection()
    session = _get_single_session_doc()
    if session:
        try:
            session_id = session["_id"]
            touch_session(session_id)
        except Exception:
            pass
        return session

    new_session = SessionModel.new_session()
    new_session.ttl_expires_at = datetime.utcnow() + timedelta(minutes=SESSION_TTL_MINUTES)
    new_session.last_activity_at = datetime.utcnow()
    doc = new_session.to_bson()
    res = sessions.insert_one(doc)
    logger.info("Inserted new single session (inserted_id=%s)", res.inserted_id)
    return doc


def _pick_random_question() -> Optional[Dict[str, Any]]:
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
    sessions_col = _sessions_collection()
    questions_col = db.get_collection("questions")

    session = _ensure_session_exists()
    session_id = session.get("_id")

    question = _pick_random_question()
    if not question:
        logger.error("No questions found in questions collection.")
        raise RuntimeError("No questions available in the question bank.")

    q_id = str(question.get("_id"))
    prompt_text = question.get("prompt", "")
    rubric = question.get("rubric", []) or []
    q_type = question.get("type", "conceptual")
    topic = question.get("topic")

    current_question = {
        "q_id": q_id,
        "prompt": prompt_text,
        "rubric": rubric,
        "type": q_type,
        "topic": topic,
        "turn_type": "main",
        "assigned_at": datetime.utcnow()
    }

    turn_doc = {
        "turn_id": f"turn_{uuid.uuid4().hex[:8]}",
        "q_id": q_id,
        "turn_type": "main",
        "q_text": prompt_text,
        "answer_text": None,
        "timestamp": datetime.utcnow(),
        "feedback": None
    }

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

    return {
        "reply": prompt_text,
        "question": prompt_text,
        "rubric": rubric,
        "q_id": q_id
    }


# -------------------------
# Answer routing helper (in-session)
# -------------------------
def route_answer_for_session(user_answer: str) -> Dict[str, Any]:
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
    prompt = EVAL_PROMPT_TEMPLATE.format(
        question_text=question_text.replace('"', '\\"'),
        rubric_json=json.dumps(rubric or []),
        candidate_answer=candidate_answer.replace('"', '\\"')
    )

    try:
        raw = call_gemini(prompt=prompt, model="gemini-2.5-pro", max_tokens=400, temperature=0.0)
    except Exception as e:
        logger.exception("Gemini evaluation call failed: %s", e)
        return {
            "feedback": "Evaluation service currently unavailable. Please try again later.",
            "classification": "somewhat_correct",
            "confidence": 0.0
        }

    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
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

    feedback = parsed.get("feedback", "").strip() if isinstance(parsed.get("feedback", ""), str) else str(parsed.get("feedback", ""))
    classification = parsed.get("classification", "")
    confidence = parsed.get("confidence", 0.0)

    if classification not in ("correct", "somewhat_correct", "wrong"):
        logger.warning("Unexpected classification from Gemini: %s", classification)
        classification = "somewhat_correct"

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
    session = _get_single_session_doc()
    if not session:
        raise RuntimeError("No active session")

    session_id = session.get("_id")
    current_q = session.get("current_question", {})
    question_text = current_q.get("prompt", "")
    rubric = current_q.get("rubric", []) or []

    evaluation = _evaluate_answer_with_gemini(question_text=question_text, rubric=rubric, candidate_answer=user_answer)

    turns = session.get("turns", []) or []
    if not turns:
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

    session["turns"] = turns
    session["current_question"]["turn_type"] = "followup"
    session["main_questions_answered"] = int(session.get("main_questions_answered", 0)) + 1
    session["last_activity_at"] = datetime.utcnow()

    _update_session_doc(session_id, session)

    return evaluation


def check_followup_answer(user_answer: str) -> Dict[str, Any]:
    session = _get_single_session_doc()
    if not session:
        raise RuntimeError("No active session")

    session_id = session.get("_id")
    current_q = session.get("current_question", {})
    question_text = current_q.get("prompt", "")
    rubric = current_q.get("rubric", []) or []

    evaluation = _evaluate_answer_with_gemini(question_text=question_text, rubric=rubric, candidate_answer=user_answer)

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
        last_turn["feedback"] = evaluation
        turns[-1] = last_turn

    session["turns"] = turns
    session["current_question"] = None
    session["followups_answered"] = int(session.get("followups_answered", 0)) + 1
    session["last_activity_at"] = datetime.utcnow()

    _update_session_doc(session_id, session)

    return evaluation


# -------------------------
# Follow-up generation & positive-ready handler
# -------------------------
FOLLOWUP_GEN_PROMPT = """
You are a helpful technical-interview assistant that generates a single FOLLOW-UP interview question
based on a previously asked question. Return ONLY a JSON object (no surrounding text) with exactly the fields:

{{
  "topic": "<one of: OOPS|DBMS|OS|CN>",
  "type": "<one of: conceptual|code|design>",
  "prompt": "<the follow-up question prompt text>",
  "rubric": ["<short rubric bullet 1>", "<rubric bullet 2>", ...],
  "requires_clarification_allowed": true,
  "requires_llm": true
}}

Constraints:
- The follow-up must be tightly related to the original question and probe deeper into one sub-area.
- Do NOT include the solution or hints.
- Keep prompt length reasonable (1-3 sentences).
- topic should match the original question's topic.
- type should be consistent with original question (prefer same type).

Context:
Original question:
\"\"\"{orig_question}\"\"\"

Original rubric:
{orig_rubric}

"""

def generate_followup_question(orig_question: str, orig_rubric: List[str], orig_topic: Optional[str], orig_type: Optional[str]) -> Dict[str, Any]:
    """
    Generate a follow-up question JSON via Gemini.
    Returns a dict matching QuestionModel-like fields.

    Raises RuntimeError with clear message on failure.
    """
    prompt = FOLLOWUP_GEN_PROMPT.format(
        orig_question=orig_question.replace('"', '\\"'),
        orig_rubric=json.dumps(orig_rubric or []),
    )

    try:
        raw = call_gemini(prompt=prompt, model="gemini-2.5-pro", max_tokens=300, temperature=0.0)
    except Exception as e:
        logger.exception("Failed to call Gemini for followup generation: %s", e)
        raise RuntimeError("Follow-up generation failed (LLM call)")

    # Normalize raw to string
    raw_text = "" if raw is None else str(raw).strip()

    # Try direct parse, otherwise try to extract substring between first { and last }
    parsed = None
    if not raw_text:
        logger.error("Empty response from Gemini while generating follow-up.")
        raise RuntimeError("Follow-up generation returned empty response")

    # Attempt to parse JSON-safe substring(s)
    parse_errors = []
    try:
        parsed = json.loads(raw_text)
    except Exception as e:
        parse_errors.append(str(e))
        # attempt to find first JSON object in the text
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = raw_text[start:end+1]
            try:
                parsed = json.loads(candidate)
            except Exception as e2:
                parse_errors.append(str(e2))

    if not parsed or not isinstance(parsed, dict):
        logger.exception("Failed to parse followup JSON. raw=%s parse_errors=%s", raw_text, parse_errors)
        raise RuntimeError("Follow-up generation returned invalid JSON")

    # Validate required fields
    topic = parsed.get("topic")
    qtype = parsed.get("type")
    prompt_text = parsed.get("prompt")
    rubric = parsed.get("rubric", [])

    if not (topic and qtype and prompt_text):
        logger.error("Followup JSON missing required fields: %s", parsed)
        raise RuntimeError("Invalid follow-up JSON from model: missing required fields")

    # Enforce allowed enums (fall back to original when invalid)
    if topic not in ("OOPS", "DBMS", "OS", "CN"):
        topic = orig_topic or topic
    if qtype not in ("conceptual", "code", "design"):
        qtype = orig_type or qtype

    followup = {
        "_id": f"generated_{uuid.uuid4().hex[:8]}",
        "topic": topic,
        "type": qtype,
        "prompt": prompt_text,
        "rubric": rubric,
        "requires_clarification_allowed": bool(parsed.get("requires_clarification_allowed", True)),
        "requires_llm": bool(parsed.get("requires_llm", True)),
        "created_at": datetime.utcnow()
    }
    return followup


def handle_positive_ready() -> Dict[str, Any]:
    """
    Handles 'positive_ready' intent per rules:
    - if no session/current_question -> start a main question
    - if current is followup:
        - if last turn is MAIN and has answer_text -> generate follow-up (user answered main)
        - if last turn is FOLLOWUP and has answer_text -> move to next main (followup answered)
        - else -> ask user to answer the current question first
    - if current is main:
        - if last turn has no answer_text -> ask to answer
        - if last turn has answer_text -> generate follow-up
    """
    try:
        session = _get_single_session_doc()
        if not session:
            return start_question_for_session()

        current_q = session.get("current_question")
        turns = session.get("turns", []) or []
        last_turn = turns[-1] if turns else None

        # If there's no current question, start a main
        if not current_q:
            return start_question_for_session()

        turn_type = current_q.get("turn_type")
        last_has_answer = bool(last_turn and last_turn.get("answer_text"))
        last_turn_type = last_turn.get("turn_type") if last_turn else None

        # CASE: current is followup
        if turn_type == "followup":
            # If the last turn was the MAIN question and it has an answer -> user answered main; generate followup
            if last_turn_type == "main" and last_has_answer:
                # generate followup based on the main that was answered
                orig_question_text = current_q.get("prompt", "")
                orig_rubric = current_q.get("rubric", []) or []
                orig_topic = current_q.get("topic")
                orig_type = current_q.get("type")

                try:
                    followup = generate_followup_question(
                        orig_question=orig_question_text,
                        orig_rubric=orig_rubric,
                        orig_topic=orig_topic,
                        orig_type=orig_type
                    )
                except Exception as e:
                    logger.exception("generate_followup_question failed: %s", e)
                    return {"reply": "Sorry — failed to generate a follow-up question. Try again later."}

                session_id = session.get("_id")
                followup_qid = str(followup.get("_id"))
                current_question = {
                    "q_id": followup_qid,
                    "prompt": followup.get("prompt"),
                    "rubric": followup.get("rubric", []),
                    "type": followup.get("type"),
                    "topic": followup.get("topic"),
                    "turn_type": "followup",
                    "assigned_at": datetime.utcnow()
                }

                followup_turn = {
                    "turn_id": f"turn_{uuid.uuid4().hex[:8]}",
                    "q_id": followup_qid,
                    "turn_type": "followup",
                    "q_text": followup.get("prompt"),
                    "answer_text": None,
                    "timestamp": datetime.utcnow(),
                    "feedback": None
                }

                _sessions_collection().update_one(
                    {"_id": session_id},
                    {
                        "$set": {"current_question": current_question, "last_activity_at": datetime.utcnow()},
                        "$push": {"turns": followup_turn}
                    }
                )

                return {
                    "reply": followup.get("prompt"),
                    "question": followup.get("prompt"),
                    "rubric": followup.get("rubric", []),
                    "q_id": followup_qid
                }

            # If the last turn was a FOLLOWUP and it has an answer -> move to next main
            if last_turn_type == "followup" and last_has_answer:
                return start_question_for_session()

            # Otherwise no answer yet for the relevant turn
            return {"reply": "Please answer the current question first before moving on."}

        # CASE: current is main
        if turn_type == "main":
            # If main hasn't been answered yet
            if not last_has_answer:
                return {"reply": "Please answer the current question first before I generate a follow-up."}

            # Main answered -> generate follow-up (same as above)
            orig_question_text = current_q.get("prompt", "")
            orig_rubric = current_q.get("rubric", []) or []
            orig_topic = current_q.get("topic")
            orig_type = current_q.get("type")

            try:
                followup = generate_followup_question(
                    orig_question=orig_question_text,
                    orig_rubric=orig_rubric,
                    orig_topic=orig_topic,
                    orig_type=orig_type
                )
            except Exception as e:
                logger.exception("generate_followup_question failed: %s", e)
                return {"reply": "Sorry — failed to generate a follow-up question. Try again later."}

            session_id = session.get("_id")
            followup_qid = str(followup.get("_id"))
            current_question = {
                "q_id": followup_qid,
                "prompt": followup.get("prompt"),
                "rubric": followup.get("rubric", []),
                "type": followup.get("type"),
                "topic": followup.get("topic"),
                "turn_type": "followup",
                "assigned_at": datetime.utcnow()
            }

            followup_turn = {
                "turn_id": f"turn_{uuid.uuid4().hex[:8]}",
                "q_id": followup_qid,
                "turn_type": "followup",
                "q_text": followup.get("prompt"),
                "answer_text": None,
                "timestamp": datetime.utcnow(),
                "feedback": None
            }

            _sessions_collection().update_one(
                {"_id": session_id},
                {
                    "$set": {"current_question": current_question, "last_activity_at": datetime.utcnow()},
                    "$push": {"turns": followup_turn}
                }
            )

            return {
                "reply": followup.get("prompt"),
                "question": followup.get("prompt"),
                "rubric": followup.get("rubric", []),
                "q_id": followup_qid
            }

        # Fallback: start a new main
        return start_question_for_session()

    except Exception as exc:
        logger.exception("handle_positive_ready error: %s", exc)
        return {"reply": "Sorry — something went wrong handling your request."}

# -------------------------
# Final report generation
# -------------------------
FINAL_REPORT_PROMPT = """
You are an experienced technical-interview coach. Given the candidate's interview session data below,
produce a single cohesive final review (300-400 words). The review must include:

1) A short introduction sentence.
2) Question-wise feedback (3 bullets) — for each main question + its follow-up, include:
   - a one-line summary identifying which question (short snippet) and whether the user answered it correctly/partly/incorrectly,
   - a one-line note on the key strength or gap for that question (use the stored 'feedback' entry).
3) Overall strengths (2 short bullet points).
4) Overall weaknesses / areas for improvement (2-4 short bullet points).
5) Actionable suggestions: short, concrete tips — e.g. be more comprehensive, align answers to rubric points, structure responses, show examples, clarify assumptions, etc.
6) A single closing sentence encouraging practice.

Rules:
- Do NOT provide the solution to any question or step-by-step answers.
- Keep the review professional and constructive.
- Output plain text only (no JSON, no extra headers). Aim for 300-400 words total.
- Use the context below.

Context:
{context}
"""

def _build_final_context_from_session(session: Dict[str, Any]) -> str:
    """
    Build a compact context summary from the session turns.
    We'll pick the latest 3 main question turns and their followups (if present),
    and include question prompt (shortened), the stored LLM feedback text, classification, and confidence.
    """
    turns = session.get("turns", []) or []
    # Collect last answered turns grouped by q_id, keep order
    grouped: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for t in turns:
        qid = t.get("q_id") or "<unknown>"
        if qid not in grouped:
            grouped[qid] = {"main": None, "followup": None, "q_text": t.get("q_text") or ""}
            order.append(qid)
        # classify by turn_type
        tt = t.get("turn_type")
        if tt == "main" and grouped[qid]["main"] is None:
            grouped[qid]["main"] = t
            if not grouped[qid]["q_text"]:
                grouped[qid]["q_text"] = t.get("q_text") or ""
        elif tt == "followup" and grouped[qid]["followup"] is None:
            grouped[qid]["followup"] = t
            if not grouped[qid]["q_text"]:
                grouped[qid]["q_text"] = t.get("q_text") or ""

    # We want the most recent 3 main qids (preserve recency)
    # order is insertion order; we prefer the last items
    selected_qids = [q for q in reversed(order)][:3]
    selected_qids.reverse()  # keep chronological order oldest->newest

    parts = []
    for idx, qid in enumerate(selected_qids, start=1):
        entry = grouped.get(qid, {})
        qtext = (entry.get("q_text") or "")[:220].replace("\n", " ").strip()
        main_turn = entry.get("main")
        follow_turn = entry.get("followup")

        parts.append(f"Question {idx} (snippet): \"{qtext}\"")

        if main_turn and main_turn.get("feedback"):
            fb = main_turn["feedback"]
            fb_text = fb.get("feedback", "") if isinstance(fb, dict) else str(fb)
            classification = fb.get("classification") if isinstance(fb, dict) else None
            confidence = fb.get("confidence") if isinstance(fb, dict) else None
            parts.append(f"  - Main answer: {classification or 'unknown'} (conf={confidence}). Feedback: {fb_text[:220]}")
        else:
            parts.append("  - Main answer: no evaluation available.")

        if follow_turn and follow_turn.get("feedback"):
            fb = follow_turn["feedback"]
            fb_text = fb.get("feedback", "") if isinstance(fb, dict) else str(fb)
            classification = fb.get("classification") if isinstance(fb, dict) else None
            confidence = fb.get("confidence") if isinstance(fb, dict) else None
            parts.append(f"  - Follow-up: {classification or 'unknown'} (conf={confidence}). Feedback: {fb_text[:220]}")
        else:
            parts.append("  - Follow-up: not answered / not evaluated.")

    # Add simple aggregate stats
    main_count = int(session.get("main_questions_answered", 0))
    follow_count = int(session.get("followups_answered", 0))
    parts.append(f"Session stats: main_answered={main_count}, followup_answered={follow_count}.")

    # Candidate metadata if present
    meta = session.get("meta", {}) or {}
    if meta.get("target_role") or meta.get("experience_level"):
        parts.append(f"Candidate meta: role={meta.get('target_role')}, exp={meta.get('experience_level')}")

    return "\n".join(parts)


def _word_count(text: str) -> int:
    return len(text.split())

def _truncate_to_word_limit(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip()

def generate_final_report_if_ready() -> Optional[str]:
    """
    If the session has >=3 main answers and >=3 followups answered, call Gemini to generate final review,
    store it in session['final_report'] and session['summary'] and persist, and return the report text.
    If not ready, return None.
    """
    session = _get_single_session_doc()
    if not session:
        return None

    main_count = int(session.get("main_questions_answered", 0))
    follow_count = int(session.get("followups_answered", 0))

    # Only generate when both counts are >= 3
    if main_count < 3 or follow_count < 3:
        return None

    # Build context from session
    context = _build_final_context_from_session(session)

    prompt = FINAL_REPORT_PROMPT.format(context=context)

    try:
        raw = call_gemini(prompt=prompt, model="gemini-2.5-pro", max_tokens=800, temperature=0.0)
        report = (raw or "").strip()
    except Exception as e:
        logger.exception("Final report Gemini call failed: %s", e)
        report = "Final feedback service is currently unavailable. Please try again later."

    # Basic sanitation: ensure we do not include overly long text (truncate at ~400 words)
    report = _truncate_to_word_limit(report, 400)

    # Save into session
    session_id = session.get("_id")
    session["final_report"] = report
    # Also store a short summary (first 60-120 words)
    session["summary"] = _truncate_to_word_limit(report, 120)
    session["last_activity_at"] = datetime.utcnow()

    try:
        _update_session_doc(session_id, session)
    except Exception:
        logger.exception("Failed to persist final_report into session (session_id=%s)", session_id)

    return report
