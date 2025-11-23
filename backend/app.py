import os
import logging
from dotenv import load_dotenv
from flask import Flask, jsonify

# Load environment variables from .env
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# Initialize DB (import and call init_db from db.py)
# This will create the Mongo client and ensure indexes (including TTL) exist.
try:
    # db.py should expose init_db() and the `db` client/handle
    from db import init_db, db as mongo_db  # adjust import path if you moved db.py
    init_db()
    logger.info("MongoDB initialized successfully.")
except Exception as e:
    # If DB initialization fails, log exception but allow app to start for incremental development.
    logger.exception("Failed to initialize MongoDB on startup: %s", e)
    mongo_db = None

def create_app():
    """
    Flask application factory.
    Minimal app for now — only DB initialization and a health endpoint.
    Add route blueprints later when ready.
    """
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    from routes.session_routes import bp as session_bp
    from routes.question_routes import bp as question_bp
    from routes.interaction_routes import bp as interaction_bp

    app.register_blueprint(session_bp, url_prefix="/session")
    app.register_blueprint(question_bp, url_prefix="/questions")
    app.register_blueprint(interaction_bp, url_prefix="/interaction")

    @app.route("/health", methods=["GET"])
    def health():
        # Basic health check: if mongo_db is available, report DB ok
        db_status = "unavailable" if mongo_db is None else "ok"
        return jsonify({
            "status": "ok",
            "db": db_status
        }), 200

    return app

if __name__ == "__main__":
    # Run app for development
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", "5000"))

    application = create_app()
    application.run(host=host, port=port, debug=True)
