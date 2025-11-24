# routes/interaction_routes.py
from flask import Blueprint, request, jsonify
import logging

from services.interaction_service import determine_intent_from_user_message
from services.session_service import (
    start_question_for_session,
    route_answer_for_session,
    check_main_answer,
    check_followup_answer,
    handle_positive_ready,
    generate_final_report_if_ready,  # <-- import final report generator
)
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

        # positive_ready → start or generate follow-up / next question
        if intent == "positive_ready":
            try:
                result = handle_positive_ready()
                return jsonify(result), 200
            except Exception as e:
                logger.exception("Failed to handle positive_ready: %s", e)
                return jsonify({"reply": "Sorry, failed to handle readiness. Try again later."}), 200

        # clarification request
        if intent == "clarify_question":
            try:
                clarification_reply = clarify_current_question(message)
                return jsonify({"reply": clarification_reply}), 200
            except Exception as e:
                logger.exception("Clarify service error: %s", e)
                return jsonify({"reply": "Sorry, I could not produce clarification right now."}), 200

        # answer handling (main / followup)
        if intent == "answer":
            routing = route_answer_for_session(message)
            handler = routing.get("handler")

            try:
                if handler == "check_main_answer":
                    eval_res = check_main_answer(message)

                    # After evaluating a main answer, check if final report is ready
                    final_report = generate_final_report_if_ready()
                    if final_report:
                        # return the final report as the reply itself
                        return jsonify({"reply": final_report}), 200

                    # Otherwise continue as normal
                    return jsonify({"reply": "Okay, I have evaluated the answer, shall we move on to the follow up question?"}), 200

                elif handler == "check_followup_answer":
                    eval_res = check_followup_answer(message)

                    # After evaluating a follow-up, check and return final report inline if ready
                    final_report = generate_final_report_if_ready()
                    if final_report:
                        return jsonify({"reply": final_report}), 200

                    return jsonify({"reply": "Okay, I have evaluated the answer, shall we move on to the next question?"}), 200

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
