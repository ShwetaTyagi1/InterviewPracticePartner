# InterviewPracticePartner

# Setup Instructions

## Backend

1. Run `git clone https://github.com/ShwetaTyagi1/InterviewPracticePartner.git` in the terminal.
2. Run `pip install -r requirements.txt` in the terminal (inside backend directory).  
   **Example:**  
   `C:\InterviewPracticePartner\backend> pip install -r requirements.txt`
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

---

## Frontend

1. Run `npm install` in the frontend root directory.  
   **Example:**  
   `C:\InterviewPracticePartner\frontend> npm install`
2. Run `npm run dev` in the frontend directory.  
   **Example:**  
   `C:\InterviewPracticePartner\frontend> npm run dev`