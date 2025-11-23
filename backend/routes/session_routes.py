# routes/session_routes.py
from flask import Blueprint, jsonify
from services.session_service import delete_all_sessions, create_session

bp = Blueprint("session_routes", __name__)

@bp.route("/start", methods=["GET"])
def start_session():
    """
    When frontend loads the website, it should call:
    GET /session/start

    This clears all old sessions and starts a fresh one.
    """
    delete_all_sessions()
    session_doc = create_session()

    return jsonify({
        "session_id": session_doc["_id"],
        "message": "Welcome to the application — this website provides interview practice on computer science fundamentals. Are you ready to begin?"
    }), 200

@bp.route("/delete", methods=["POST", "DELETE"])
def delete():
    """
    Delete all sessions immediately.
    POST /session/delete  or DELETE /session/delete

    Returns JSON with deleted_count.
    NOTE: This is a powerful operation (your app is single-user by design).
    You may want to protect this endpoint with a simple admin token or remove it in production.
    """

    deleted_count = delete_all_sessions()
    return jsonify({
        "ok": True,
        "deleted_count": deleted_count,
        "message": "All sessions deleted."
    }), 200
