# routes/interaction_routes.py
from flask import Blueprint, request, jsonify
import logging

from services.interaction_service import determine_intent_from_user_message
from services.session_service import start_question_for_session, route_answer_for_session, check_main_answer, check_followup_answer
from services.clarify_service import clarify_current_question

logger = logging.getLogger(__name__)

bp = Blueprint("interaction_routes", __name__)

FORBIDDEN_INTENTS = {
    "ask_if_correct",
    "request_solution",
}


@bp.route("/interact", methods=["POST"])
def interact():
    
    if not request.is_json:
        return jsonify({"reply": "Invalid request: expected JSON body."}), 400

    data = request.get_json()
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"reply": "Message cannot be empty."}), 400

    try:
        # Determine intent using DB-based session + Gemini intent parser
        intent = determine_intent_from_user_message(message)

        # Forbidden intents (no LLM call)
        if intent in FORBIDDEN_INTENTS:
            if intent == "ask_if_correct":
                reply = (
                    "I can’t evaluate correctness on the spot. "
                    "Please give your full answer, and I will assess it afterwards."
                )
            else:  # request_solution
                reply = (
                    "I can't provide the complete answer or solution. "
                    "However, I can help with clarifying the question or giving hints."
                )

            return jsonify({"reply": reply}), 200

        # If the user said they are ready, start by picking a random question and
        # sending it to the frontend with its rubrics
        if intent == "positive_ready":
            try:
                q_payload = start_question_for_session()
                # Return the question prompt + rubric directly to the frontend
                return jsonify({
                    "reply": q_payload["reply"],
                    "question": q_payload["question"],
                    "rubric": q_payload["rubric"],
                    "q_id": q_payload["q_id"]
                }), 200
            except Exception as e:
                logger.exception("Failed to start question for session: %s", e)
                return jsonify({"reply": "Sorry, failed to fetch a question. Try again later."}), 200

        if intent == "clarify_question":
            # the frontend message is the user's clarify request
            try:
                clarification_reply = clarify_current_question(message)
                return jsonify({"reply": clarification_reply}), 200
            except Exception as e:
                logger.exception("Clarify service error: %s", e)
                return jsonify({"reply": "Sorry, I could not produce clarification right now."}), 200

        if intent == "answer":
            routing = route_answer_for_session(message)
            handler = routing.get("handler")

            try:
                if handler == "check_main_answer":
                    eval_res = check_main_answer(message)
                    # You requested a specific reply text:
                    return jsonify({"reply": "Okay, I have evaluated the answer and let's move on to the follow up question."}), 200

                elif handler == "check_followup_answer":
                    eval_res = check_followup_answer(message)
                    return jsonify({"reply": "Okay, I have evaluated the answer, let's move on to the next question."}), 200

                else:
                    return jsonify({"reply": "No active question to evaluate. Say 'I'm ready' to begin."}), 200

            except Exception as e:
                logger.exception("Error evaluating answer: %s", e)
                return jsonify({"reply": "Sorry, I couldn't evaluate the answer right now."}), 200

        # Placeholder for other intents (to be implemented)
        reply = f"(placeholder) Detected intent: {intent}"
        return jsonify({"reply": reply}), 200

    except Exception as e:
        logger.exception("Error in /interact: %s", e)
        return jsonify({
            "reply": "Sorry, something went wrong while processing your request."
        }), 200
