# models/session_model.py
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import uuid
import os

SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", "30"))

def gen_id(prefix: str = "session") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

class Turn(BaseModel):
    turn_id: str = Field(default_factory=lambda: f"turn_{uuid.uuid4().hex[:8]}")
    q_id: Optional[str] = None
    turn_type: str = Field(..., pattern="^(main|followup)$")
    q_text: Optional[str] = None
    answer_text: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    feedback: Optional[Dict[str, Any]] = None  # LLMEvaluation or fallback
    classification: Optional[str] = None       # correct|somewhat_correct|wrong
    confidence: Optional[float] = None

class SessionModel(BaseModel):
    id: str = Field(default_factory=gen_id, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity_at: datetime = Field(default_factory=datetime.utcnow)
    ttl_expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=SESSION_TTL_MINUTES))

    meta: Dict[str, Optional[str]] = Field(default_factory=lambda: {"target_role": None, "experience_level": None})
    current_question: Optional[Dict[str, Any]] = None
    turns: List[Turn] = Field(default_factory=list)
    summary: Optional[str] = None
    questions_asked: List[str] = Field(default_factory=list)
    main_questions_answered: int = 0
    followups_answered: int = 0
    final_report: Optional[str] = None

    def to_bson(self) -> dict:
        d = self.model_dump(by_alias=True)
        # Pydantic converts datetimes; safe for pymongo
        return d

    @classmethod
    def new_session(cls, target_role: Optional[str] = None, experience_level: Optional[str] = None):
        s = cls()
        if target_role:
            s.meta["target_role"] = target_role
        if experience_level:
            s.meta["experience_level"] = experience_level
        return s

