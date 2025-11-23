# models/question_model.py
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class QuestionModel(BaseModel):
    _id: Optional[str] = None         # you may store a string id like "q_001" or let Mongo generate ObjectId
    topic: str
    difficulty: int = Field(..., ge=1, le=5)
    type: str = Field(..., regex="^(conceptual|code|design)$")
    prompt: str
    rubric: List[str] = []
    requires_clarification_allowed: bool = True
    requires_llm: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_bson(self) -> dict:
        """
        Convert to a dict suitable for pymongo insertion.
        If _id is None we will omit it (Mongo will create ObjectId).
        """
        d = self.dict()
        if d.get("_id") is None:
            d.pop("_id", None)
        return d

    @classmethod
    def from_bson(cls, data: dict):
        # data is Mongo document; convert to Pydantic instance
        # ensure created_at is datetime (should be)
        return cls(**data)
