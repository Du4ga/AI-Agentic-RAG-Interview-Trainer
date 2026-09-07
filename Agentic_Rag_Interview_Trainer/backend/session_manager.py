"""
Session Manager — in-memory interview session store.

A session has at most MAX_QUESTIONS generated questions. Every generated question
must be completed exactly once by either submitting an answer or skipping it.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 10

# In-memory store (replace with Redis/DB for production)
_sessions: Dict[str, dict] = {}


class SessionManager:
    def create_session(self, profile: dict, interview_type: str) -> str:
        session_id = str(uuid.uuid4())
        _sessions[session_id] = {
            "session_id": session_id,
            "profile": profile,
            "interview_type": interview_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "questions": [],
            "answers": [],
            "evaluations": [],
            "status": "active",
            "max_questions": MAX_QUESTIONS,
        }
        logger.info(f"Session created: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        return _sessions.get(session_id)

    def generated_count(self, session_id: str) -> int:
        session = _sessions.get(session_id)
        return len(session.get("questions", [])) if session else 0

    def completed_count(self, session_id: str) -> int:
        session = _sessions.get(session_id)
        return len(session.get("answers", [])) if session else 0

    def is_complete(self, session_id: str) -> bool:
        session = _sessions.get(session_id)
        if not session:
            return False
        return len(session["answers"]) >= session.get("max_questions", MAX_QUESTIONS)

    def add_question(self, session_id: str, question: dict):
        session = _sessions.get(session_id)
        if not session:
            raise ValueError("Session not found")
        if self.is_complete(session_id):
            raise ValueError(f"Session has already completed {MAX_QUESTIONS} questions")
        if len(session["questions"]) >= session.get("max_questions", MAX_QUESTIONS):
            raise ValueError(f"Session has reached the maximum of {MAX_QUESTIONS} generated questions")
        session["questions"].append(question)

    def get_question(self, session_id: str, question_id: str) -> Optional[dict]:
        session = _sessions.get(session_id)
        if not session:
            return None
        for q in session["questions"]:
            if q.get("id") == question_id:
                return q
        return None

    def is_question_completed(self, session_id: str, question_id: str) -> bool:
        session = _sessions.get(session_id)
        if not session:
            return False
        return any(a.get("question_id") == question_id for a in session.get("answers", []))

    def is_question_skipped(self, session_id: str, question_id: str) -> bool:
        session = _sessions.get(session_id)
        if not session:
            return False
        return any(
            a.get("question_id") == question_id and a.get("answer") == "__skipped__"
            for a in session.get("answers", [])
        )

    def replace_skip_with_answer(self, session_id: str, question_id: str, answer: str, evaluation: dict):
        """Turn a previously skipped question into an answered question without
        increasing the number of completed questions."""
        session = _sessions.get(session_id)
        if not session:
            raise ValueError("Session not found")
        if not self.is_question_skipped(session_id, question_id):
            raise ValueError("Question was not skipped")

        session["answers"] = [
            a for a in session["answers"] if a.get("question_id") != question_id
        ]
        session["evaluations"] = [
            e for e in session["evaluations"] if e.get("question_id") != question_id
        ]
        session["answers"].append({
            "question_id": question_id,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        session["evaluations"].append({
            "question_id": question_id,
            "evaluation": evaluation,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        if self.is_complete(session_id):
            session["status"] = "completed"
        else:
            session["status"] = "active"

    def get_evaluation(self, session_id: str, question_id: str) -> Optional[dict]:
        session = _sessions.get(session_id)
        if not session:
            return None
        for item in session.get("evaluations", []):
            if item.get("question_id") == question_id:
                return item.get("evaluation")
        return None

    def current_question_id(self, session_id: str) -> Optional[str]:
        session = _sessions.get(session_id)
        if not session or not session.get("questions"):
            return None
        return session["questions"][-1].get("id")

    def ensure_current_question(self, session_id: str, question_id: str):
        """Ensure an action targets the latest generated, not-yet-completed question."""
        if self.current_question_id(session_id) != question_id:
            raise ValueError("This is not the active interview question")
        if self.is_question_completed(session_id, question_id):
            raise ValueError("This question has already been completed")

    def record_skip(self, session_id: str, question_id: str):
        session = _sessions.get(session_id)
        if not session:
            raise ValueError("Session not found")
        self.ensure_current_question(session_id, question_id)
        if self.is_complete(session_id):
            raise ValueError(f"Interview complete: maximum of {MAX_QUESTIONS} questions reached")

        session["answers"].append({
            "question_id": question_id,
            "answer": "__skipped__",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        session["evaluations"].append({
            "question_id": question_id,
            "evaluation": {
                "score": 0,
                "overall_assessment": "Question skipped.",
                "strengths": [],
                "improvements": ["Try to answer the question rather than skipping when possible."],
                "question_category": "skipped"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        if self.is_complete(session_id):
            session["status"] = "completed"

    def record_answer(self, session_id: str, question_id: str, answer: str, evaluation: dict):
        session = _sessions.get(session_id)
        if not session:
            raise ValueError("Session not found")
        self.ensure_current_question(session_id, question_id)
        if self.is_complete(session_id):
            raise ValueError(f"Interview complete: maximum of {MAX_QUESTIONS} questions reached")

        session["answers"].append({
            "question_id": question_id,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        session["evaluations"].append({
            "question_id": question_id,
            "evaluation": evaluation,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        if self.is_complete(session_id):
            session["status"] = "completed"

    def build_summary(self, session_id: str) -> dict:
        session = _sessions.get(session_id)
        if not session:
            return {}

        evals = session.get("evaluations", [])
        scored_evals = [
            e for e in evals
            if e.get("evaluation", {}).get("question_category") != "skipped"
            and isinstance(e.get("evaluation", {}).get("score"), (int, float))
        ]
        scores = [e["evaluation"]["score"] for e in scored_evals]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0

        strengths = []
        improvements = []
        category_scores = {}
        for e in evals:
            ev = e.get("evaluation", {})
            if ev.get("question_category") != "skipped":
                strengths.extend(ev.get("strengths", []))
                improvements.extend(ev.get("improvements", []))
            category = ev.get("question_category")
            if category and category != "skipped" and isinstance(ev.get("score"), (int, float)):
                category_scores.setdefault(category, []).append(ev["score"])

        category_breakdown = {
            category: round(sum(values) / len(values), 1)
            for category, values in category_scores.items()
        }

        completed = len(session.get("answers", []))
        skipped = sum(1 for a in session.get("answers", []) if a.get("answer") == "__skipped__")
        session["status"] = "completed" if completed >= session.get("max_questions", MAX_QUESTIONS) else "active"

        return {
            "session_id": session_id,
            "profile": session["profile"],
            "interview_type": session["interview_type"],
            "status": session["status"],
            "questions_answered": completed,
            "questions_skipped": skipped,
            "questions_generated": len(session.get("questions", [])),
            "max_questions": session.get("max_questions", MAX_QUESTIONS),
            "average_score": avg_score,
            "category_scores": category_breakdown,
            "top_strengths": list(dict.fromkeys(strengths))[:5],
            "top_improvements": list(dict.fromkeys(improvements))[:5],
            "created_at": session["created_at"],
            "completed_at": datetime.now(timezone.utc).isoformat() if session["status"] == "completed" else None
        }
