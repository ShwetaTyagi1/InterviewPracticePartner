# services/interaction_service.py
"""
Interaction layer that fetches the single session and uses gemini_intent() to
determine the user's intent given a message. Returns only the intent string.
"""

from typing import Dict, Any, List, Optional
import logging

from db import db
from services.gemini_intent import gemini_intent

logger = logging.getLogger(__name__)


def _get_single_session() -> Optional[Dict[str, Any]]:
    col = db.get_collection("sessions")
    session = col.find_one(sort=[("created_at", -1)])
    return session


def _infer_turn_type(session: Optional[Dict[str, Any]]) -> str:
    if not session:
        return "intro"
    current_q = session.get("current_question")
    if not current_q:
        return "intro"
    t = current_q.get("turn_type")
    if t in ("main", "followup"):
        return t
    return "intro"


def determine_intent_from_user_message(user_message: str) -> str:
    """
    Return only the intent string. Uses gemini_intent internally.
    """
    session = _get_single_session()
    turn_type = _infer_turn_type(session)

    question_text = ""
    rubric: List[str] = []
    session_summary = ""

    if session:
        current_q = session.get("current_question") or {}
        question_text = current_q.get("prompt", "") or ""
        rubric = current_q.get("rubric") or []
        session_summary = session.get("summary") or ""

    # call gemini_intent (this function returns a single intent string)
    intent = gemini_intent(
        user_message=user_message,
        question=question_text,
        rubric=rubric,
        session_summary=session_summary,
        turn_type=turn_type
    )

    # Defensive normalization: ensure string and allowed fallback
    if not isinstance(intent, str) or not intent:
        return "other"

    return intent
