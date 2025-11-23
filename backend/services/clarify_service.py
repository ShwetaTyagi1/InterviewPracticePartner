# services/clarify_service.py

from typing import Dict, Any, Optional, List
import logging
import json

from db import db
from services.gemini_client import call_gemini

logger = logging.getLogger(__name__)

# model + generation config
GEMINI_MODEL = "gemini-2.5-pro"

def _get_single_session_doc() -> Optional[Dict[str, Any]]:
    col = db.get_collection("sessions")
    return col.find_one(sort=[("created_at", -1)])


def _build_clarify_prompt(user_query: str, question_text: str, rubric: List[str]) -> str:
    """
    Build a prompt instructing Gemini to EXPLAIN the question or a specific part,
    and to NEVER provide hints, partial solutions, or answers.
    The prompt includes the local file path (which the deployment will convert to a URL).
    """
    rubric_json = json.dumps(rubric or [])

    prompt = f"""
You are a careful technical interview assistant whose job is to EXPLAIN the *question text* to the candidate,
NOT to provide hints, partial solutions, or full answers. Follow these strict rules exactly:

1) Provide only explanation or rephrasing of the question text, or of the specific piece the user asked about.
   - Explain terminology, intent, requirements, constraints, or what the question is asking.
   - If the user asks about a specific line/phrase, explain the meaning/role of that line/phrase only.
2) NEVER provide hints, solution steps, algorithmic advice, pseudocode, code fragments, or anything that would
   materially help the user solve the problem. Avoid any examples that show how to solve the problem.
3) If the user explicitly requests the answer, a hint, or evaluation of their answer, REFUSE politely:
   - Reply: "I can't provide the solution or hints. I can only clarify the question or explain parts of it."
   - Then offer to rephrase the question, explain terminology, or point to concepts the question touches (without giving solution content).
4) Keep responses concise, factual, and focused on clarifying intent. Use short illustrative analogies only when they do not reveal how to solve the question.
5) If uncertain whether an explanation would reveal the answer, err on the side of withholding that explanatory detail and offer a safer, more general clarification.

Context:
Question:
\"\"\"{question_text}\"\"\"

Rubric (summary):
{rubric_json}

User clarification request:
\"\"\"{user_query}\"\"\"

Produce a single, focused clarification that follows the rules above. If you must refuse (user asked for answer/hint), respond with the polite refusal described in rule #3.
"""
    return prompt


def clarify_current_question(user_query: str) -> str:
    """
    Main entrypoint.
    - If no session or no current question -> return helpful guidance to start interview.
    - Otherwise call Gemini with the constructed prompt and return the textual reply.
    """
    session = _get_single_session_doc()
    if not session:
        return "There is no active interview session. Please start the interview first."

    current_q = session.get("current_question")
    if not current_q:
        return "No question is currently active. Say 'I'm ready' to start the interview and receive a question."

    question_text = current_q.get("prompt", "")
    rubric = current_q.get("rubric", []) or []

    prompt = _build_clarify_prompt(user_query=user_query, question_text=question_text, rubric=rubric)

    try:
        raw_out = call_gemini(prompt=prompt, model=GEMINI_MODEL)
        # raw_out is raw text from Gemini SDK; return stripped result
        return raw_out.strip() if isinstance(raw_out, str) else str(raw_out)
    except Exception as e:
        logger.exception("Clarify call to Gemini failed: %s", e)
        return "Sorry — I couldn't generate a clarification right now. Please try again in a moment."
