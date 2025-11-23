# models/question_model.py
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class QuestionModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")         # you may store a string id like "q_001" or let Mongo generate ObjectId
    topic: str = Field(..., pattern="^(OOPS|DBMS|OS|CN)$")
    type: str = Field(..., pattern="^(conceptual|code|design)$")
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
        d = self.model_dump(by_alias=True)
        if d.get("_id") is None:
            d.pop("_id", None)
        return d

    @classmethod
    def from_bson(cls, data: dict):
        # data is Mongo document; convert to Pydantic instance
        # ensure created_at is datetime (should be)
        return cls(**data)
