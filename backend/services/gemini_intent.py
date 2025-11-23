# services/gemini_intent.py

from typing import List, Optional, Dict, Any
import json
import logging

from services.gemini_client import call_gemini

logger = logging.getLogger(__name__)

# Allowed intents
ALLOWED_INTENTS = {
    "clarify_question",
    "request_solution",
    "ask_if_correct",
    "answer",
    "positive_ready",
    "negative_ready",
    "skip_question",
    "off_topic",
    "other",
}

# Use a VALID Gemini SDK model
GEMINI_MODEL = "gemini-2.5-pro"
INTENT_MAX_TOKENS = 512
RETRY_ON_FAILURE = True

# Strict JSON-only prompt
INTENT_PROMPT_TEMPLATE = """
You are an intent classifier for a technical interview assistant.

Return ONLY a valid JSON object with NO text before or after it.

Schema:
{{
  "intent": "one of: clarify_question | request_solution | ask_if_correct |
             answer | positive_ready | negative_ready |
             skip_question | off_topic | other",
  "intent_confidence": 0.0,
  "clarify_target": "",
  "answer_text": "",
  "notes": ""
}}

RULES:
- STRICT JSON ONLY — no comments, no explanations.
- DO NOT provide answers or solutions.
- intent MUST be exactly one of the allowed strings.

Context:
turn_type: {turn_type}
question: "{question}"
rubric: {rubric_json}
session_summary: "{summary}"

User message:
"{user_message}"
"""

def _build_prompt(user_message: str, question: str,
                  rubric: List[str], summary: str, turn_type: str) -> str:

    safe_question = (question or "").replace("\n", " ").replace('"', '\\"')
    safe_msg = (user_message or "").replace("\n", " ").replace('"', '\\"')
    safe_summary = (summary or "").replace("\n", " ").replace('"', '\\"')
    rubric_json = json.dumps(rubric or [])

    return INTENT_PROMPT_TEMPLATE.format(
        turn_type=turn_type,
        question=safe_question,
        rubric_json=rubric_json,
        summary=safe_summary,
        user_message=safe_msg
    )


def _extract_json_from_raw(raw: str) -> Dict[str, Any]:
    """Parse JSON strictly from model output."""
    try:
        return json.loads(raw)
    except Exception:
        # Try extracting substring
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end+1])
            except Exception as e:
                raise ValueError(f"Could not parse JSON substring: {e}") from e
        raise ValueError("No JSON object found in raw output")


def gemini_intent(
    user_message: str,
    question: str = "",
    rubric: Optional[List[str]] = None,
    session_summary: str = "",
    turn_type: str = "main"
) -> str:

    rubric = rubric or []
    prompt = _build_prompt(user_message, question, rubric, session_summary, turn_type)

    # === FIRST CALL ===
    try:
        raw = call_gemini(
            prompt=prompt,
            model=GEMINI_MODEL,
            max_tokens=INTENT_MAX_TOKENS
        )
    except Exception:
        if turn_type == "intro":
            return "off_topic"
        return "other"

    # === FIRST PARSE ATTEMPT ===
    try:
        parsed = _extract_json_from_raw(raw)
    except Exception:
        if not RETRY_ON_FAILURE:
            return "off_topic" if turn_type == "intro" else "other"

        # === SECOND CALL ===
        try:
            retry_prompt = (
                prompt
                + "\n\nThe previous output was invalid. Return ONLY valid JSON matching the schema."
            )
            raw2 = call_gemini(
                prompt=retry_prompt,
                model=GEMINI_MODEL,
                max_tokens=INTENT_MAX_TOKENS
            )
            parsed = _extract_json_from_raw(raw2)
        except Exception:
            return "off_topic" if turn_type == "intro" else "other"

    # === VALIDATION ===
    intent = parsed.get("intent")
    confidence = parsed.get("intent_confidence", 0.0)

    if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
        return "off_topic" if turn_type == "intro" else "other"

    if turn_type == "intro":
        try:
            if intent == "positive_ready" and float(confidence) >= 0.5:
                return "positive_ready"
        except Exception:
            pass
        return "off_topic"

    return intent
