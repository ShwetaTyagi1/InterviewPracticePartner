# services/session_service.py

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pymongo.collection import Collection
from pydantic import ValidationError
import logging
import uuid
import os

from db import db  # expects db to expose the pymongo database handle
from models.session_model import SessionModel

logger = logging.getLogger(__name__)

# Configurable: how many minutes until session TTL expires (db.py also uses SESSION_TTL_MINUTES env)
from os import getenv
SESSION_TTL_MINUTES = int(getenv("SESSION_TTL_MINUTES", "30"))


def _sessions_collection() -> Collection:
    return db.get_collection("sessions")


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
