"""
Question Generator — RAG-augmented interview question generation using Granite
"""
import uuid
import logging
from typing import List, Dict, Optional

from rag_engine import RAGEngine
from granite_client import GraniteClient

logger = logging.getLogger(__name__)

QUESTION_TYPES = {
    "technical": [
        "data structures and algorithms",
        "system design",
        "coding practices",
        "debugging and problem solving",
        "architecture patterns"
    ],
    "behavioral": [
        "teamwork and collaboration",
        "conflict resolution",
        "leadership and initiative",
        "time management",
        "communication skills"
    ],
    "role-specific": [
        "domain knowledge",
        "tools and technologies",
        "project experience",
        "industry practices",
        "responsibilities and deliverables"
    ],
    "scenario": [
        "real-world problem solving",
        "decision making under pressure",
        "handling ambiguity",
        "prioritization",
        "stakeholder management"
    ]
}


class QuestionGenerator:
    def __init__(self, rag_engine: RAGEngine, granite_client: GraniteClient):
        self.rag = rag_engine
        self.granite = granite_client

    async def generate_question(
        self,
        profile: dict,
        interview_type: str,
        question_number: int,
        previous_questions: List[str]
    ) -> dict:
        """Generate a contextually relevant interview question."""

        # Build RAG query
        rag_query = _build_rag_query(profile, interview_type, question_number)
        chunks = self.rag.retrieve(rag_query, top_k=4)
        context = self.rag.format_context(chunks, max_chars=1500)
        resume_excerpt = str(profile.get("resume_text", "")).strip()[:2500]

        # Determine question category
        category = _pick_category(interview_type, question_number)

        prev_text = ""
        if previous_questions:
            prev_list = "\n".join(f"- {q}" for q in previous_questions[-3:])
            prev_text = f"\nPrevious questions already asked (do NOT repeat these):\n{prev_list}\n"

        prompt = f"""You are an expert technical interviewer preparing a {profile.get('experience_level', 'mid')}-level {profile.get('target_role', 'Software Engineer')} candidate for a real interview.

Candidate profile:
- Name: {profile.get('name', 'Candidate')}
- Target role: {profile.get('target_role', 'Software Engineer')}
- Experience level: {profile.get('experience_level', 'mid')}
- Years of experience: {profile.get('years_experience', 0)}
- Skills: {', '.join(profile.get('skills', []))}
- Current role: {profile.get('current_role', 'Not specified')}
{prev_text}
{f"Resume highlights (use only as candidate-specific context):{chr(10)}{resume_excerpt}" if resume_excerpt else ""}
Relevant interview knowledge:
{context if context else "Use your expertise to generate a high-quality question."}

Task: Generate question #{question_number} — a {category} interview question.
Requirements:
- Tailor it precisely to the candidate's role and experience level
- Make it realistic, specific, and challenging (but not impossible)
- For technical questions: focus on {', '.join(profile.get('skills', ['general programming'])[:3])}
- Do NOT repeat previous questions
- Output ONLY the question text, nothing else

Question:"""

        try:
            question_text = await self.granite.generate(prompt, max_tokens=200, temperature=0.75)
            question_text = _clean_question(question_text)
        except Exception as e:
            logger.error(f"Granite question gen error: {e}")
            question_text = _fallback_question(profile, category, question_number)

        question_id = str(uuid.uuid4())
        return {
            "id": question_id,
            "text": question_text,
            "category": category,
            "number": question_number,
            "context_used": len(chunks) > 0,
            "rag_sources": [c["source"] for c in chunks[:2]]
        }

    async def generate_followup(
        self,
        profile: dict,
        original_question: dict,
        candidate_answer: str,
        feedback: str
    ) -> str:
        """Generate a follow-up question based on the candidate's answer."""

        rag_query = f"follow-up interview question {profile.get('target_role', '')} {original_question.get('text', '')}"
        chunks = self.rag.retrieve(rag_query, top_k=3)
        context = self.rag.format_context(chunks, max_chars=800)

        prompt = f"""You are an expert interviewer conducting a {profile.get('target_role', 'Software Engineer')} interview.

Original question: {original_question.get('text', '')}

Candidate's answer: {candidate_answer[:600]}

Feedback given: {feedback[:400]}

{f"Relevant knowledge: {context}" if context else ""}

Generate ONE targeted follow-up question that:
- Probes deeper into a specific aspect of their answer
- Addresses a gap or weakness identified in the feedback
- Is appropriate for {profile.get('experience_level', 'mid')}-level {profile.get('target_role', 'Software Engineer')}
- Encourages the candidate to demonstrate more depth

Output ONLY the follow-up question, nothing else:"""

        try:
            followup = await self.granite.generate(prompt, max_tokens=150, temperature=0.7)
            return _clean_question(followup)
        except Exception as e:
            logger.error(f"Follow-up gen error: {e}")
            return "Can you elaborate further on how you would handle the most challenging aspect of that scenario?"


def _build_rag_query(profile: dict, interview_type: str, q_num: int) -> str:
    role = profile.get("target_role", "software engineer")
    level = profile.get("experience_level", "mid")
    skills = ", ".join(profile.get("skills", [])[:3])
    category = _pick_category(interview_type, q_num)
    return f"{category} interview questions for {level} {role} with skills in {skills}"


def _pick_category(interview_type: str, q_num: int) -> str:
    if interview_type == "technical":
        return "technical"
    if interview_type == "behavioral":
        return "behavioral"
    if interview_type == "role-specific":
        return "role-specific"
    # Mixed: rotate through categories
    cats = ["technical", "behavioral", "role-specific", "scenario", "technical", "behavioral"]
    return cats[(q_num - 1) % len(cats)]


def _clean_question(text: str) -> str:
    text = text.strip()
    for prefix in ["Question:", "Q:", "Interview question:", "Here is", "Here's"]:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    if text and not text.endswith("?"):
        text += "?"
    return text or "Tell me about your most challenging technical project and how you overcame the obstacles you faced."


def _fallback_question(profile: dict, category: str, q_num: int) -> str:
    role = profile.get("target_role", "Software Engineer")
    level = profile.get("experience_level", "mid")
    skills = profile.get("skills", ["programming"])

    fallbacks = {
        "technical": f"As a {level}-level {role}, describe a complex technical problem you solved using {skills[0] if skills else 'your core skills'}. Walk me through your approach, the trade-offs you considered, and what you would do differently today.",
        "behavioral": "Tell me about a time when you had to work with a difficult team member or stakeholder. How did you handle the situation, and what was the outcome?",
        "role-specific": f"What key responsibilities do you expect in a {level} {role} role, and how does your current experience prepare you for those responsibilities?",
        "scenario": f"Imagine you are a {level} {role} and you discover a critical bug in production two hours before a major release. Walk me through exactly how you would handle this situation."
    }
    return fallbacks.get(category, fallbacks["technical"])
