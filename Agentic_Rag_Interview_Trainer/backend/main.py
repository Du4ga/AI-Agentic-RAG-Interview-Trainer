"""
Agentic RAG Interview Trainer - Main FastAPI Application
"""
import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from rag_engine import RAGEngine
from granite_client import GraniteClient
from session_manager import SessionManager, MAX_QUESTIONS
from question_generator import QuestionGenerator
from answer_evaluator import AnswerEvaluator

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agentic RAG Interview Trainer",
    description="AI-powered interview preparation using RAG and IBM Granite",
    version="1.0.0"
)

# CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
cors_origins.extend(["http://localhost:8000", "http://127.0.0.1:8000"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize core components
rag_engine = RAGEngine()
granite_client = GraniteClient()
session_manager = SessionManager()
question_generator = QuestionGenerator(rag_engine, granite_client)
answer_evaluator = AnswerEvaluator(rag_engine, granite_client)


# ─── Pydantic Models ──────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    name: str
    experience_level: str          # junior / mid / senior / lead
    target_role: str
    skills: List[str]
    education: Optional[str] = ""
    current_role: Optional[str] = ""
    years_experience: Optional[int] = 0
    resume_text: Optional[str] = ""

class SessionCreateRequest(BaseModel):
    profile: UserProfile
    interview_type: str = "mixed"  # technical / behavioral / mixed / role-specific

class AnswerRequest(BaseModel):
    session_id: str
    question_id: str
    answer: str

class FollowUpRequest(BaseModel):
    session_id: str
    question_id: str
    original_answer: str
    feedback_received: str

class NextQuestionRequest(BaseModel):
    session_id: str

class SkipRequest(BaseModel):
    session_id: str
    question_id: str

class RecommendationRequest(BaseModel):
    session_id: str


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    kb_ready = rag_engine.is_ready()
    return {
        "status": "ok",
        "knowledge_base": "ready" if kb_ready else "loading",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ─── Knowledge Base ───────────────────────────────────────────────────────────

@app.post("/api/kb/initialize")
async def initialize_kb():
    """Initialize / reload the RAG knowledge base."""
    try:
        count = rag_engine.build_index()
        return {"status": "success", "chunks_indexed": count}
    except Exception as e:
        logger.error(f"KB init error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Profile & Session ────────────────────────────────────────────────────────

@app.post("/api/session/create")
async def create_session(req: SessionCreateRequest):
    """Create a new interview session for a user profile."""
    try:
        session_id = session_manager.create_session(req.profile.model_dump(), req.interview_type)
        # Generate first question immediately
        question = await question_generator.generate_question(
            profile=req.profile.model_dump(),
            interview_type=req.interview_type,
            question_number=1,
            previous_questions=[]
        )
        session_manager.add_question(session_id, question)
        return {
            "session_id": session_id,
            "first_question": question,
            "profile_summary": _build_profile_summary(req.profile.model_dump())
        }
    except Exception as e:
        logger.error(f"Session create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Parse and extract text from a resume PDF or TXT."""
    try:
        content = await file.read()
        if file.filename.endswith(".pdf"):
            text = _extract_pdf_text(content)
        else:
            text = content.decode("utf-8", errors="ignore")
        return {"resume_text": text[:6000]}  # limit to 6k chars
    except Exception as e:
        logger.error(f"Resume upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Interview Flow ───────────────────────────────────────────────────────────

@app.post("/api/interview/next-question")
async def get_next_question(req: NextQuestionRequest):
    """Generate the next interview question for a session (max 10)."""
    session = session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    generated_count = session_manager.generated_count(req.session_id)
    completed_count = session_manager.completed_count(req.session_id)

    # Hard server-side limit and sequencing guard. A client cannot generate a
    # new question before completing the current one, and can never exceed 10.
    if session_manager.is_complete(req.session_id):
        raise HTTPException(
            status_code=400,
            detail=f"Interview complete: maximum of {MAX_QUESTIONS} questions reached"
        )
    if generated_count >= MAX_QUESTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Interview complete: maximum of {MAX_QUESTIONS} questions reached"
        )
    if completed_count < generated_count:
        raise HTTPException(
            status_code=409,
            detail="Complete the current question before requesting the next question"
        )

    previous_questions = [q["text"] for q in session.get("questions", [])]
    q_number = generated_count + 1

    question = await question_generator.generate_question(
        profile=session["profile"],
        interview_type=session["interview_type"],
        question_number=q_number,
        previous_questions=previous_questions
    )
    session_manager.add_question(req.session_id, question)
    return {"question": question, "questions_remaining": MAX_QUESTIONS - q_number}


@app.post("/api/interview/skip")
async def skip_question(req: SkipRequest):
    """Skip the current question — counts as one of the 10 questions."""
    session = session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    answered_count = session_manager.completed_count(req.session_id)
    if answered_count >= MAX_QUESTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Interview complete: maximum of {MAX_QUESTIONS} questions reached"
        )
    if not session_manager.get_question(req.session_id, req.question_id):
        raise HTTPException(status_code=404, detail="Question not found")

    try:
        session_manager.record_skip(req.session_id, req.question_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    answered_count = session_manager.completed_count(req.session_id)
    is_complete = answered_count >= MAX_QUESTIONS

    return {
        "skipped": True,
        "questions_completed": answered_count,
        "is_complete": is_complete
    }


@app.post("/api/interview/evaluate")
async def evaluate_answer(req: AnswerRequest):
    """Evaluate a candidate's answer and return structured feedback."""
    session = session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    question = session_manager.get_question(req.session_id, req.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")
    # A skipped question may be revisited later. In that case we replace the
    # skip record instead of counting a second completion.
    is_reopened_skip = session_manager.is_question_skipped(req.session_id, req.question_id)
    if not is_reopened_skip:
        try:
            session_manager.ensure_current_question(req.session_id, req.question_id)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    evaluation = await answer_evaluator.evaluate(
        profile=session["profile"],
        question=question,
        answer=req.answer
    )
    try:
        if is_reopened_skip:
            session_manager.replace_skip_with_answer(
                req.session_id, req.question_id, req.answer, evaluation
            )
        else:
            session_manager.record_answer(req.session_id, req.question_id, req.answer, evaluation)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    completed = session_manager.completed_count(req.session_id)
    evaluation["questions_completed"] = completed
    evaluation["questions_remaining"] = max(0, MAX_QUESTIONS - completed)
    evaluation["is_complete"] = completed >= MAX_QUESTIONS
    return evaluation


@app.post("/api/interview/followup")
async def get_followup(req: FollowUpRequest):
    """Generate a contextual follow-up question."""
    session = session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    question = session_manager.get_question(req.session_id, req.question_id)
    followup = await question_generator.generate_followup(
        profile=session["profile"],
        original_question=question,
        candidate_answer=req.original_answer,
        feedback=req.feedback_received
    )
    return {"followup_question": followup}


@app.post("/api/interview/recommendations")
async def get_recommendations(req: RecommendationRequest):
    """Return personalized preparation recommendations based on session history."""
    session = session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    recs = await answer_evaluator.generate_recommendations(session)
    return {"recommendations": recs}


@app.get("/api/interview/summary/{session_id}")
async def get_session_summary(session_id: str):
    """Return a full performance summary for a completed session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    summary = session_manager.build_summary(session_id)
    return summary


# ─── Static Frontend ──────────────────────────────────────────────────────────

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_path, "index.html"))

    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        file_path = os.path.join(frontend_path, path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_path, "index.html"))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_profile_summary(profile: dict) -> str:
    return (
        f"{profile.get('name', 'Candidate')} | "
        f"{profile.get('experience_level', '').title()} {profile.get('target_role', '')} | "
        f"{profile.get('years_experience', 0)} yrs exp"
    )


def _extract_pdf_text(content: bytes) -> str:
    try:
        import io
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", 8000)),
        reload=True
    )
