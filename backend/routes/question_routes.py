# routes/question_routes.py
from flask import Blueprint, jsonify, request
from models.question_model import QuestionModel
from db import db

bp = Blueprint("question_routes", __name__)

@bp.route("/add", methods=["POST"])
def add_question():
    """
    Add a new question to the database.

    POST /questions/add
    Body:
    {
        "_id": "q_oop_001",   // optional
        "topic": "OOP",
        "type": "conceptual",
        "prompt": "Explain polymorphism.",
        "rubric": ["definition", "example", "compile vs runtime"],
        "requires_clarification_allowed": true,
        "requires_llm": true
    }
    """

    if not request.is_json:
        return jsonify({"error": "Invalid JSON payload"}), 400

    try:
        # Validate request JSON using Pydantic
        question = QuestionModel(**request.get_json())
        
        # Convert to bson dict for mongo insertion
        q_doc = question.to_bson()

        # Insert into MongoDB
        result = db.questions.insert_one(q_doc)

        # Attach the generated _id for response (if not provided)
        q_doc["_id"] = str(result.inserted_id)

        return jsonify({
            "message": "Question added successfully",
            "question": q_doc
        }), 201

    except Exception as e:
        print("Error adding question:", e)
        return jsonify({"error": "Failed to add question", "details": str(e)}), 500
