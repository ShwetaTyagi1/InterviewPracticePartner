# services/session_service.py
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pymongo.collection import Collection
from pydantic import ValidationError
import logging

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
    # Insert into MongoDB
    res = col.insert_one(session_doc)
    logger.info("Created new session with id=%s (inserted_id=%s)", session.id, res.inserted_id)

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
    result = col.update_one({"_id": session_id}, {"$set": {"last_activity_at": datetime.utcnow(), "ttl_expires_at": new_ttl}})
    return result.matched_count == 1
