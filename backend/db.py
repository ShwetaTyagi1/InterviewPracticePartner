# db.py
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "interview_practice_db")
SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", "30"))

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]

def init_db():
    """
    Ensure collections and indexes exist.
    - questions: index on topic (optional)
    - sessions: TTL index on 'ttl_expires_at' to auto-delete sessions
    """
    # Questions collection:
    questions = db.get_collection("questions")
    # ensure index on topic for faster sampling by topic
    questions.create_index([("topic", ASCENDING)], background=True)
    questions.create_index([("created_at", ASCENDING)], background=True)

    # Sessions collection:
    sessions = db.get_collection("sessions")
    # TTL index on ttl_expires_at will remove sessions after the given datetime passes.
    # Note: Create the index once; if it already exists, create_index is idempotent.
    sessions.create_index([("ttl_expires_at", ASCENDING)], expireAfterSeconds=0, background=True)
    # Also index last_activity_at (optional) for metrics queries
    sessions.create_index([("last_activity_at", ASCENDING)], background=True)

    # Optional: uniqueness for question IDs (if you manage your own _id)
    # _id is unique by default in MongoDB, so we don't need to explicitly create a unique index for it.
    # Attempting to do so with unique=True can cause an OperationFailure.

    print(f"[db] Initialized DB '{MONGO_DB_NAME}'. Session TTL = {SESSION_TTL_MINUTES} minutes")
