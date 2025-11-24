# IntervueX

An AI-powered, state-aware interview practice platform for mastering Computer Science fundamentals.
IntervueX helps candidates improve their technical interview skills by simulating a realistic interviewer that adapts, evaluates, and guides—without behaving like a generic chatbot. It is built around a deterministic state machine that uses AI only when needed, ensuring structure, consistency, and pedagogical rigor.

## Key Features

Adaptive Questioning
Dynamically adjusts difficulty based on the user’s performance.

Intent-Driven Interaction
Identifies user intent (ready, clarify, answer, off-topic, etc.) and routes it through deterministic logic instead of relying solely on an LLM.

Clarification Without Spoilers
Provides hints or rephrasing for “clarify question” intents using a custom Clarification Service.

Structured Evaluation
User answers are graded as Correct, Partially Correct, or Incorrect based on rubrics stored in the database.

Guardrails for Off-Topic Queries
Off-topic messages trigger predefined refusal messages, preventing derailment.

Session Persistence & Cleanup
MongoDB stores the current question, state, and context. Sessions are automatically cleaned up on browser unload.

## Architecture Overview
Frontend
Built with React + Vite
Modern, responsive dark-mode UI
Styled with vanilla CSS
“Chat bar on demand” design for reduced cognitive load
Uses REST calls to drive the deterministic interview flow

Backend
Flask API orchestrating all logic

Handles:
Session creation & deletion
Question selection
Intent classification
Clarification logic
Evaluation routing
Follow-up question generation

AI Engine
Google Gemini Pro via the google-genai SDK

Used only for:
Natural language understanding
Clarifications
Evaluation support
All high-level interview logic is deterministic and rule-driven.

Database
MongoDB

Stores:
Session context
Current question I
Intent states
Question rubrics
User progression

CommunicatioN
RESTful API endpoints connecting React ↔ Flask
Real-time session management
Automatic cleanup using a beforeunload beacon request

## Interview Flow Logic

User starts a session → /session/start
User expresses readiness → Intent classifier detects positive_ready
Backend picks a CS question (OOP/OS/DBMS/CN) with rubric
User can ask clarification → Clarification Service rephrases without revealing the answer
User answers → Evaluation Engine compares to rubric
Follow-up questions trigger for partial answers
Off-topic queries are blocked with predefined responses
Session ends → /session/delete cleans MongoDB entry

## Design Philosophy

Reduce cognitive load by hiding the chat bar until onboarding completes
Provide a premium feel using glassmorphism and gradient-based UI
Maintain strict boundaries between “chatbot behavior” and “interviewer behavior”
Ensure consistent interview flow using deterministic state transitions



# Setup Instructions

## Backend

1. Run `git clone https://github.com/ShwetaTyagi1/InterviewPracticePartner.git` in the terminal.
2. Run `pip install -r requirements.txt` or `python -m pip install -r requirements.txt` in the terminal (inside backend directory).  
   **Example:**  
   `C:\InterviewPracticePartner\backend> python -m pip install -r requirements.txt`
3. Create a `.env` file in the backend directory containing:
   ```
   MONGO_URI=connection string to mongodb
   MONGO_DB_NAME=interview_practice_db
   SESSION_TTL_MINUTES=30
   GEMINI_API_KEY=Your key from Google AI studio
   PORT=5000
   ```
4. Run `python app.py` in the backend directory.  
   **Example:**  
   `C:\InterviewPracticePartner\backend> python app.py`

5. Use Postman to add a few questions to the database.
<img width="1071" height="434" alt="Screenshot 2025-11-24 134332" src="https://github.com/user-attachments/assets/c21c806a-256a-486b-8f89-f9b9260f3263" />
---

## Frontend

1. Run `npm install` in the frontend root directory.  
   **Example:**  
   `C:\InterviewPracticePartner\frontend> npm install`
2. Run `npm run dev` in the frontend directory.  
   **Example:**  
   `C:\InterviewPracticePartner\frontend> npm run dev`
