"""
Answer Evaluator — RAG-augmented, rubric-based evaluation using IBM Granite.

The evaluator deliberately separates relevance from answer length. Granite judges
multiple dimensions, while a small deterministic guard prevents an obviously
irrelevant answer from receiving a high score just because it is long.
"""
import json
import logging
import re
from typing import Dict, List

from rag_engine import RAGEngine
from granite_client import GraniteClient

logger = logging.getLogger(__name__)

# Words that are common in interview prompts but carry little evidence that an
# answer actually addressed the question.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so", "to", "of",
    "in", "on", "at", "for", "from", "with", "by", "as", "into", "about", "over",
    "under", "during", "through", "while", "after", "before", "between", "this",
    "that", "these", "those", "it", "its", "they", "them", "their", "there",
    "here", "you", "your", "yours", "we", "our", "ours", "i", "me", "my", "mine",
    "he", "she", "his", "her", "who", "whom", "which", "what", "when", "where",
    "why", "how", "can", "could", "would", "should", "will", "may", "might", "do",
    "does", "did", "have", "has", "had", "be", "is", "are", "was", "were", "been",
    "being", "tell", "describe", "explain", "discuss", "walk", "through", "give",
    "share", "talk", "time", "situation", "example", "question", "answer", "approach",
    "handle", "handling", "using", "used", "use", "one", "also", "very", "really",
    "most", "more", "some", "any", "such", "each", "both", "either", "rather",
    "perhaps", "current", "based", "specific", "exactly", "key", "following", "following",
}

_REFUSAL_PATTERNS = [
    r"^i\s+(do\s*not|don't|dont)\s+know\b",
    r"^i\s+have\s+no\s+idea\b",
    r"^no\s+idea\b",
    r"^i\s+can't\s+answer\b",
    r"^i\s+cannot\s+answer\b",
    r"^i\s+don['’]?t\s+have\s+an?\s+answer\b",
    r"^sorry[,\s]+i\s+(do\s+not|don't|dont)\s+know\b",
]


class AnswerEvaluator:
    def __init__(self, rag_engine: RAGEngine, granite_client: GraniteClient):
        self.rag = rag_engine
        self.granite = granite_client

    async def evaluate(self, profile: dict, question: dict, answer: str) -> dict:
        """Evaluate a candidate answer using a transparent multi-dimension rubric."""
        answer = (answer or "").strip()
        question_text = question.get("text", "")
        category = question.get("category", "general")

        rag_query = (
            f"ideal answer evaluation criteria {category} {question_text} "
            f"{profile.get('target_role', '')} {' '.join(profile.get('skills', [])[:5])}"
        )
        chunks = self.rag.retrieve(rag_query, top_k=4)
        context = self.rag.format_context(chunks, max_chars=1600)

        relevance_details = _relevance_details(
            question_text,
            answer,
            profile,
            context,
            category,
        )
        relevance_signal = relevance_details["signal"]
        refusal = _is_refusal(answer)
        resume_excerpt = str(profile.get("resume_text", "")).strip()[:1800]

        prompt = f"""You are a strict senior interviewer evaluating one candidate answer.

Candidate level: {profile.get('experience_level', 'mid')}
Target role: {profile.get('target_role', 'Software Engineer')}
Interview category: {category}
{f"Candidate resume context (do not treat as an answer):{chr(10)}{resume_excerpt}" if resume_excerpt else ""}

QUESTION:
{question_text}

CANDIDATE ANSWER:
{answer[:1800]}

{f"RAG evaluation guidance (use as supporting evidence, not as the candidate's answer):{chr(10)}{context}" if context else ""}

Evaluate the candidate's answer against the QUESTION. Do not reward length by itself.
An answer that is detailed but answers a different topic is a POOR answer.
An answer that says the candidate does not know is a POOR answer, even if polite.
Judge relevance first, then correctness/reasoning, completeness, specificity/evidence,
and communication. For behavioral questions, use STAR qualities and ownership.
For technical questions, check whether the claims actually address the asked concept.
Do not assume missing facts are true. Do not give credit for content that does not
answer the question.

Use this rubric for each dimension from 0 to 10:
- relevance: directly addresses the question and its requested task
- accuracy: technically correct or logically sound for the question
- completeness: covers the important parts an interviewer would expect
- specificity: concrete actions, examples, trade-offs, evidence, metrics, or details
- communication: clear, structured, concise, professional

IMPORTANT SCORING RULES:
- Relevance is the gatekeeper. If relevance <= 2, the final score must be <= 3.
- If relevance is 3-4, the final score must be <= 5.
- Never increase a score because the answer is long.
- A concise but correct answer can score well on accuracy, but completeness and
  specificity should still reflect what is missing.
- The final score should represent interview usefulness, not writing length.

Return JSON only:
{{
  "relevance": <0-10>,
  "accuracy": <0-10>,
  "completeness": <0-10>,
  "specificity": <0-10>,
  "communication": <0-10>,
  "overall_assessment": "<2-3 concise sentences>",
  "strengths": ["<strength>", "<strength>", "<strength>"],
  "improvements": ["<improvement>", "<improvement>", "<improvement>"],
  "model_answer": "<concise but useful example of what an excellent answer would cover>",
  "key_concepts_covered": ["<concept>"],
  "key_concepts_missing": ["<concept>"],
  "tips": ["<specific actionable tip>", "<specific actionable tip>"],
  "technical_accuracy": "<accurate / partially accurate / inaccurate / not applicable>",
  "communication_quality": "<excellent / good / needs improvement>"
}}"""

        try:
            raw = await self.granite.generate(prompt, max_tokens=700, temperature=0.1)
            # A few watsonx responses can be empty even though the HTTP call
            # succeeds. Retry once with a compact JSON-only prompt before using
            # the deterministic local rubric.
            if not raw.strip():
                compact_prompt = f"""Evaluate this interview answer strictly. Return JSON only.
Question: {question_text}
Answer: {answer[:1600]}
Score relevance, accuracy, completeness, specificity and communication from 0-10.
Do not reward length or off-topic content. Relevance must dominate.
Return: {{"relevance":0,"accuracy":0,"completeness":0,"specificity":0,"communication":0,
"overall_assessment":"","strengths":[],"improvements":[],"model_answer":"",
"key_concepts_covered":[],"key_concepts_missing":[],"tips":[],
"technical_accuracy":"","communication_quality":""}}"""
                raw = await self.granite.generate(compact_prompt, max_tokens=500, temperature=0)
            evaluation = _parse_json_response(raw)
            evaluation = _finalize_score(evaluation, relevance_details, refusal)
            evaluation["question_text"] = question_text
            evaluation["question_category"] = category
            evaluation["context_used"] = len(chunks) > 0
            evaluation["relevance_signal"] = round(relevance_signal, 3)
            evaluation["evaluation_source"] = "IBM Granite"
            return evaluation
        except Exception as e:
            logger.error(f"Evaluation error; using local rubric: {e}")
            return _fallback_evaluation(question, answer, relevance_signal, relevance_details, context)

    async def generate_recommendations(self, session: dict) -> List[dict]:
        """Generate personalized preparation recommendations from session history."""
        profile = session.get("profile", {})
        evals = session.get("evaluations", [])

        if not evals:
            return _default_recommendations(profile)

        all_improvements = []
        scores_by_category: Dict[str, List[int]] = {}
        for e in evals:
            ev = e.get("evaluation", {})
            all_improvements.extend(ev.get("improvements", []))
            cat = ev.get("question_category", "general")
            score = ev.get("score", 0)
            # Skips have a score of 0 but are not evidence of a content weakness.
            if cat != "skipped":
                scores_by_category.setdefault(cat, []).append(score)

        weak_areas = list(dict.fromkeys(all_improvements))[:6]
        weakest_categories = sorted(
            scores_by_category.items(),
            key=lambda x: sum(x[1]) / len(x[1])
        )[:2]

        rag_query = (
            f"interview preparation recommendations {profile.get('target_role', '')} "
            f"{profile.get('experience_level', '')} {' '.join(weak_areas[:3])}"
        )
        chunks = self.rag.retrieve(rag_query, top_k=5)
        context = self.rag.format_context(chunks, max_chars=1000)

        prompt = f"""You are a career coach creating a personalized improvement plan for a
{profile.get('experience_level', 'mid')}-level {profile.get('target_role', 'Software Engineer')} candidate.

Identified weak areas from their mock interview:
{chr(10).join(f"- {a}" for a in weak_areas[:5])}

Categories needing most improvement: {', '.join(c[0] for c in weakest_categories) or 'Not enough answered questions yet'}
Skills profile: {', '.join(profile.get('skills', [])[:5])}

{f"Preparation resources and guidance:{chr(10)}{context}" if context else ""}

Create 5 specific, actionable preparation recommendations. Output as JSON array only:
[
  {{
    "area": "<focus area>",
    "priority": "<high/medium/low>",
    "recommendation": "<specific actionable recommendation>",
    "resources": ["<resource 1>", "<resource 2>"],
    "timeline": "<suggested timeline e.g. 1 week>"
  }}
]"""

        try:
            raw = await self.granite.generate(prompt, max_tokens=600, temperature=0.5)
            recs = _parse_json_array(raw)
            if recs:
                return recs
        except Exception as e:
            logger.error(f"Recommendations error: {e}")

        return _default_recommendations(profile)


def _parse_json_response(text: str) -> dict:
    """Extract and validate JSON object from Granite response."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return _validate_evaluation(result)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, dict):
                return _validate_evaluation(result)
        except Exception:
            pass

    raise ValueError("Granite returned an invalid evaluation JSON response.")


def _as_score(value, default=5) -> int:
    try:
        return max(0, min(10, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def _validate_evaluation(evaluation: dict) -> dict:
    """Validate and normalize Granite's rubric response."""
    dimensions = {
        "relevance": _as_score(evaluation.get("relevance", 5)),
        "accuracy": _as_score(evaluation.get("accuracy", 5)),
        "completeness": _as_score(evaluation.get("completeness", 5)),
        "specificity": _as_score(evaluation.get("specificity", 5)),
        "communication": _as_score(evaluation.get("communication", 5)),
    }
    return {
        **dimensions,
        "score": _as_score(evaluation.get("score", 5)),
        "overall_assessment": str(evaluation.get("overall_assessment", "No assessment provided.")),
        "strengths": _clean_list(evaluation.get("strengths", [])),
        "improvements": _clean_list(evaluation.get("improvements", [])),
        "model_answer": str(evaluation.get("model_answer", "")),
        "key_concepts_covered": _clean_list(evaluation.get("key_concepts_covered", [])),
        "key_concepts_missing": _clean_list(evaluation.get("key_concepts_missing", [])),
        "tips": _clean_list(evaluation.get("tips", [])),
        "technical_accuracy": str(evaluation.get("technical_accuracy", "unknown")),
        "communication_quality": str(evaluation.get("communication_quality", "unknown")),
    }


def _clean_list(value) -> list:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:6]


def _finalize_score(evaluation: dict, relevance_details: dict, refusal: bool) -> dict:
    """Compute the displayed score from rubric dimensions and apply hard guards."""
    weighted = (
        evaluation["relevance"] * 0.35
        + evaluation["accuracy"] * 0.25
        + evaluation["completeness"] * 0.20
        + evaluation["specificity"] * 0.12
        + evaluation["communication"] * 0.08
    )
    score = int(round(weighted))

    signal = relevance_details["signal"]
    direct_overlap = relevance_details["direct_overlap"]
    anchor_overlap = relevance_details["anchor_overlap"]
    context_overlap = relevance_details["context_overlap"]
    category = relevance_details.get("category", "general")

    # Deterministic guardrails: an obviously irrelevant or refusal answer cannot
    # become a high score due to verbosity or an overly generous model judgment.
    if refusal:
        score = min(score, 2)
    elif signal < 0.015:
        score = min(score, 3)
    elif signal < 0.03:
        score = min(score, 4)
    elif category in {"technical", "role-specific"} and direct_overlap == 0 and context_overlap < 0.12:
        # For technical/role-specific questions, profile terms such as "Python"
        # alone are not enough; the answer must connect to the asked concept.
        score = min(score, 4)
    elif evaluation["relevance"] <= 2:
        score = min(score, 3)
    elif evaluation["relevance"] <= 4:
        score = min(score, 5)

    evaluation["score"] = max(1, min(10, score))
    return evaluation


def _is_refusal(answer: str) -> bool:
    normalized = re.sub(r"\s+", " ", (answer or "").strip().lower())
    return any(re.search(pattern, normalized) for pattern in _REFUSAL_PATTERNS)


def _tokens(text: str) -> set:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", (text or "").lower())
    result = set()
    for word in words:
        word = word.strip(".-")
        if len(word) < 3 or word in _STOPWORDS:
            continue
        # Small normalization for common inflections without requiring another dependency.
        for suffix in ("ing", "ed", "es", "s"):
            if len(word) > 5 and word.endswith(suffix):
                word = word[:-len(suffix)]
                break
        result.add(word)
    return result


def _relevance_details(question: str, answer: str, profile: dict, context: str, category: str = "general") -> dict:
    """Estimate relevance using direct question evidence plus supporting signals."""
    q = _tokens(question)
    a = _tokens(answer)
    if not q or not a:
        return {"signal": 0.0, "direct_overlap": 0.0, "anchor_overlap": 0.0, "context_overlap": 0.0, "profile_overlap": 0.0}

    direct_overlap = len(q & a) / max(1, min(len(q), 10))

    profile_text = " ".join([
        str(profile.get("target_role", "")),
        str(profile.get("current_role", "")),
        " ".join(profile.get("skills", [])[:8]),
    ])
    p = _tokens(profile_text)
    profile_overlap = len(p & a) / max(1, min(len(p), 8)) if p else 0.0

    context_terms = _tokens(context)
    context_overlap = len(context_terms & a) / max(1, min(len(context_terms), 6)) if context_terms else 0.0

    category_anchors = {
        "behavioral": {"team", "teammate", "coworker", "colleague", "stakeholder", "conflict", "communicat", "leadership", "feedback", "result", "learn"},
        "technical": {"algorithm", "complexity", "api", "database", "model", "code", "system", "design", "debug", "test", "performance", "deploy"},
        "role-specific": {"project", "responsibil", "deliver", "role", "tool", "technology", "experience", "impact"},
        "scenario": {"priorit", "decision", "tradeoff", "incident", "risk", "stakeholder", "mitigat", "solution", "communicat"},
    }.get(category, set())
    anchor_overlap = len(category_anchors & a) / max(1, min(len(category_anchors), 3)) if category_anchors else 0.0

    signal = (
        0.58 * min(direct_overlap, 1.0)
        + 0.22 * min(context_overlap, 1.0)
        + 0.12 * min(anchor_overlap, 1.0)
        + 0.08 * min(profile_overlap, 1.0)
    )
    return {
        "signal": min(1.0, signal),
        "direct_overlap": min(1.0, direct_overlap),
        "anchor_overlap": min(1.0, anchor_overlap),
        "context_overlap": min(1.0, context_overlap),
        "profile_overlap": min(1.0, profile_overlap),
        "category": category,
    }


def _relevance_signal(question: str, answer: str, profile: dict, context: str, category: str = "general") -> float:
    """Backward-compatible scalar relevance helper."""
    return _relevance_details(question, answer, profile, context, category)["signal"]


def _fallback_evaluation(
    question: dict,
    answer: str,
    relevance_signal: float = 0.0,
    relevance_details: dict = None,
    context: str = ""
) -> dict:
    """Deterministic safety-net rubric used only when Granite cannot be parsed.

    It intentionally distinguishes refusal, off-topic, short/partial, and
    well-supported answers instead of returning the old fixed 5/10 fallback.
    """
    details = relevance_details or {}
    direct = float(details.get("direct_overlap", 0.0))
    context_overlap = float(details.get("context_overlap", 0.0))
    answer_words = len(_tokens(answer))
    answer_chars = len(answer.strip())

    if _is_refusal(answer):
        score = 1
        dims = dict(relevance=0, accuracy=0, completeness=0, specificity=0, communication=2)
        assessment = "This answer indicates that you do not know the topic. In an interview, acknowledge the gap briefly and explain how you would approach learning or solving it."
        improvements = ["Give a brief reason or approach when you do not know", "Connect your response to the question", "Avoid stopping at 'I don't know'"]
    elif relevance_signal < 0.015:
        score = 2
        dims = dict(relevance=1, accuracy=1, completeness=1, specificity=1, communication=4)
        assessment = "The response is largely unrelated to the question. A strong interview answer must address the requested topic first."
        improvements = ["Answer the exact question first", "Remove unrelated details", "Use the question's key technical or behavioral terms"]
    else:
        # Estimate quality from evidence, not raw length. Direct question overlap
        # and overlap with retrieved RAG guidance are the strongest signals.
        evidence = min(1.0, 0.55 * direct + 0.45 * context_overlap)
        relevance_dim = round(min(10, max(2, relevance_signal * 14)))
        completeness_dim = round(min(10, max(2, 3 + evidence * 7)))
        specificity_dim = round(min(10, max(2, 2 + min(answer_words / 45, 1) * 4 + evidence * 4)))
        accuracy_dim = round(min(10, max(2, 3 + evidence * 7)))
        communication_dim = 7 if answer_chars >= 120 else 5
        # A concise answer can still score well if it contains strong evidence.
        score = int(round(
            relevance_dim * 0.35 + accuracy_dim * 0.25 +
            completeness_dim * 0.20 + specificity_dim * 0.12 +
            communication_dim * 0.08
        ))
        if evidence >= 0.55 and answer_words >= 18:
            score = max(score, 7)
        if evidence >= 0.72 and answer_words >= 30:
            score = max(score, 8)
        if evidence < 0.18:
            score = min(score, 4)
        score = max(3, min(8, score))
        dims = dict(
            relevance=relevance_dim, accuracy=accuracy_dim,
            completeness=completeness_dim, specificity=specificity_dim,
            communication=communication_dim
        )
        if score >= 7:
            assessment = "The response appears relevant and contains useful supporting evidence. Add any missing details or measurable outcomes to make it stronger."
        elif score >= 5:
            assessment = "The response has some relevant content but would benefit from clearer coverage of the question and more concrete evidence."
        else:
            assessment = "The response has limited evidence that it fully addresses the question. Focus on the requested topic and explain your reasoning more directly."
        improvements = ["Answer the exact question first", "Add concrete evidence, examples, or trade-offs", "Explain your reasoning clearly"]

    return {
        "score": score,
        **dims,
        "overall_assessment": assessment,
        "strengths": ["Attempted to respond" if answer.strip() else "No answer provided"],
        "improvements": improvements,
        "model_answer": "A strong answer should directly address the question, explain the reasoning or actions taken, and include a concrete example, trade-off, or result where appropriate.",
        "key_concepts_covered": [],
        "key_concepts_missing": [],
        "tips": ["Lead with the direct answer", "Use specific examples instead of general statements"],
        "technical_accuracy": "not assessed — local fallback used",
        "communication_quality": "good" if dims["communication"] >= 7 else "needs improvement",
        "question_text": question.get("text", ""),
        "question_category": question.get("category", "general"),
        "context_used": bool(context),
        "relevance_signal": round(relevance_signal, 3),
        "evaluation_source": "Local rubric fallback (Granite response unavailable)"
    }

def _parse_json_array(text: str) -> list:
    text = (text or "").strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except Exception:
        pass
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except Exception:
            pass
    return []


def _default_recommendations(profile: dict) -> list:
    role = profile.get("target_role", "Software Engineer")
    return [
        {
            "area": "Technical Skills",
            "priority": "high",
            "recommendation": f"Practice {role}-specific problems with a focus on explaining your reasoning, trade-offs, and complexity.",
            "resources": ["LeetCode", "HackerRank", "Interview practice problems"],
            "timeline": "2-3 weeks"
        },
        {
            "area": "Behavioral Interviews",
            "priority": "high",
            "recommendation": "Prepare 8-10 STAR stories covering leadership, conflict, failure, teamwork, and measurable outcomes.",
            "resources": ["STAR Method Guide", "Your project experiences"],
            "timeline": "1 week"
        },
        {
            "area": "System Design",
            "priority": "medium",
            "recommendation": "Practice requirements, scale estimates, architecture, data flow, reliability, and trade-offs for common systems.",
            "resources": ["System Design Primer", "Architecture case studies"],
            "timeline": "2 weeks"
        },
        {
            "area": "Answer Quality",
            "priority": "high",
            "recommendation": "Lead with the direct answer, then support it with a concrete example, reasoning, and measurable result when possible.",
            "resources": ["Mock interview sessions", "STAR framework"],
            "timeline": "Ongoing"
        },
        {
            "area": "Mock Interviews",
            "priority": "high",
            "recommendation": "Complete at least 3 focused mock interviews and review every missed concept after each session.",
            "resources": ["Peer practice", "Interview Trainer"],
            "timeline": "Ongoing"
        }
    ]
