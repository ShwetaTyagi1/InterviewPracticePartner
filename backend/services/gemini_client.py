# services/gemini_client.py

import os
import logging
from google import genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Single global client instance
_client = None


def _get_client():
    """Create a singleton Gemini client instance (no mock mode)."""
    global _client

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Cannot call Gemini API.")

    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)

    return _client


def call_gemini(
    prompt: str,
    model: str = "gemini-2.5-pro",
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> str:
    """
    Calls Google GenAI using the official SDK and returns ONLY the model's text output.
    No fallback, no mock mode, no silent failures.
    """

    client = _get_client()

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt
        )

        if hasattr(response, "text"):
            return response.text

        return str(response)

    except Exception as e:
        logger.exception("Gemini API call failed: %s", e)
        raise RuntimeError(f"Gemini API call failed: {e}")
