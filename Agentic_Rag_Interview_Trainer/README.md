# Agentic RAG Interview Trainer

An AI-powered, fully agentic interview preparation assistant built with **IBM Granite** (watsonx.ai), **Retrieval Augmented Generation (RAG)**, FastAPI, and a clean vanilla-JS frontend.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                     Frontend                         │
│  (Vanilla JS SPA — Home / Profile / Interview /      │
│   Evaluation / Recommendations / Summary)            │
└──────────────────────┬──────────────────────────────┘
                       │  HTTP / REST
┌──────────────────────▼──────────────────────────────┐
│                  FastAPI Backend                     │
│                                                      │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │  Session   │  │   Question   │  │   Answer    │  │
│  │  Manager   │  │  Generator   │  │  Evaluator  │  │
│  └────────────┘  └──────┬───────┘  └──────┬──────┘  │
│                         │                 │          │
│  ┌──────────────────────▼─────────────────▼───────┐  │
│  │                  RAG Engine                    │  │
│  │  (FAISS + sentence-transformers/all-MiniLM-L6) │  │
│  └──────────────────────┬─────────────────────────┘  │
│                         │                            │
│  ┌──────────────────────▼─────────────────────────┐  │
│  │              Granite Client                    │  │
│  │   IBM watsonx.ai  (ibm/granite-4-h-small)      │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│               Knowledge Base                         │
│  knowledge_base/*.json | *.txt | *.md                │
│  interview_knowledge.json · roles_and_levels.txt     │
│  behavioral_guide.txt                                │
└─────────────────────────────────────────────────────┘
```

### Key Components

| Component | File | Role |
|---|---|---|
| FastAPI App | `backend/main.py` | REST API, routing, file serving |
| RAG Engine | `backend/rag_engine.py` | FAISS index, chunk retrieval |
| Granite Client | `backend/granite_client.py` | IBM watsonx.ai text generation |
| Question Generator | `backend/question_generator.py` | RAG-augmented question creation |
| Answer Evaluator | `backend/answer_evaluator.py` | RAG-augmented answer scoring + feedback |
| Session Manager | `backend/session_manager.py` | In-memory interview session state |
| Frontend SPA | `frontend/` | Single-page app — all UI pages |
| Knowledge Base | `knowledge_base/` | Interview prep documents for RAG |

---

## Features

- **RAG Workflow** — Every question and evaluation is grounded in retrieved knowledge base content before Granite generates a response
- **IBM Granite** — Uses `ibm/granite-4-h-small` via watsonx.ai REST API
- **Personalized Questions** — Tailored to role, experience level, and skills
- **4 Question Types** — Technical, Behavioral, Role-Specific, Scenario-Based
- **Structured Evaluation** — Score (1–10), strengths, improvements, model answer, tips, key concepts covered/missing
- **Dynamic Follow-Up** — Context-aware follow-up questions based on candidate's specific answer
- **Preparation Recommendations** — Personalized study plan derived from session performance
- **Session Summary** — Overall score, top strengths, top improvement areas
- **Resume Parsing** — Upload PDF/TXT resume to further personalize questions
- **Honest Responses** — If retrieved context is insufficient, the system acknowledges it rather than hallucinating

---

## Setup

### Prerequisites

- Python 3.10+
- Internet access (for IBM IAM token + watsonx.ai API)

### 1. Configure Credentials

The `backend/.env` file contains your IBM watsonx.ai credentials. **Never commit this file.**

```env
WATSONX_URL=https://eu-de.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29
WATSONX_API_KEY=<your-ibm-cloud-api-key>
WATSONX_PROJECT_ID=<your-project-id>
WATSONX_MODEL_ID=ibm/granite-4-h-small
```

### 2. Install and Run

**Option A — Automated setup:**
```bash
cd backend
python setup.py
python main.py
```

**Option B — Manual:**
```bash
cd backend
pip install -r requirements.txt
python main.py
```

The server starts at **http://localhost:8000**.

On first start, the RAG engine builds the FAISS index over the knowledge base (~5–10 seconds). A status indicator in the top-right of the UI confirms when it is ready.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Server + KB status |
| POST | `/api/kb/initialize` | Rebuild knowledge base index |
| POST | `/api/session/create` | Create interview session |
| GET | `/api/session/{id}` | Get session state |
| POST | `/api/resume/upload` | Parse resume PDF/TXT |
| POST | `/api/interview/next-question` | Generate next question |
| POST | `/api/interview/evaluate` | Evaluate candidate answer |
| POST | `/api/interview/followup` | Generate follow-up question |
| POST | `/api/interview/recommendations` | Get prep recommendations |
| GET | `/api/interview/summary/{id}` | Session performance summary |

---

## Main Workflow

```
User fills profile (name, role, level, skills, optional resume)
    ↓
POST /api/session/create
    ↓ RAG retrieves relevant interview knowledge
    ↓ Granite generates personalized question
    ↓
Display question to candidate
    ↓
Candidate submits answer
    ↓
POST /api/interview/evaluate
    ↓ RAG retrieves evaluation criteria
    ↓ Granite scores and generates structured feedback
    ↓
Display: score, strengths, improvements, model answer, tips
    ↓
[Optional] POST /api/interview/followup → context-aware probe
    ↓
POST /api/interview/next-question → repeat
    ↓
POST /api/interview/recommendations → personalized study plan
GET  /api/interview/summary/{id}   → overall performance
```

---

## Extending the Knowledge Base

Add any `.txt`, `.md`, or `.json` file to `knowledge_base/`.

JSON format:
```json
[
  {
    "category": "technical",
    "tags": ["python", "async"],
    "content": "Your interview content here..."
  }
]
```

Then hit `POST /api/kb/initialize` or restart the server to rebuild the index.

---

## Security Notes

- API key is stored only in `backend/.env` — never in source code, frontend, or logs
- `.env` is excluded from version control via `.gitignore`
- The frontend never receives or displays any credentials
- IAM token exchange happens server-side only

---

## Project Structure

```
Agentic_Rag_Interview_Trainer/
├── backend/
│   ├── main.py               # FastAPI application
│   ├── granite_client.py     # IBM watsonx.ai REST client
│   ├── rag_engine.py         # FAISS RAG engine
│   ├── question_generator.py # Question generation
│   ├── answer_evaluator.py   # Answer evaluation + feedback
│   ├── session_manager.py    # Session state
│   ├── setup.py              # Setup & verification script
│   ├── requirements.txt      # Python dependencies
│   └── .env                  # Credentials (not committed)
├── frontend/
│   ├── index.html            # SPA entry point
│   └── static/
│       ├── css/styles.css    # All styles
│       └── js/
│           ├── api.js        # Backend API client
│           └── app.js        # SPA logic + all pages
├── knowledge_base/
│   ├── interview_knowledge.json  # Core interview Q&A KB
│   ├── roles_and_levels.txt      # Role-specific guidance
│   └── behavioral_guide.txt      # STAR method + behavioral
└── README.md
```

---

## Evaluation Rubric

Candidate answers are evaluated by IBM Granite using five explicit dimensions:

- **Relevance (35%)** — does the response directly answer the question?
- **Accuracy (25%)** — are the technical claims or reasoning correct?
- **Completeness (20%)** — does it cover the important parts an interviewer expects?
- **Specificity (12%)** — does it provide concrete actions, evidence, trade-offs, examples, or outcomes?
- **Communication (8%)** — is it clear, structured, and professional?

The final displayed score is calculated from these dimensions rather than copied directly from a single model score. A deterministic relevance guard also prevents an obviously off-topic or refusal response from receiving a high score simply because it is long. If Granite returns an empty/unparseable evaluation, the application retries once and then uses a transparent local rubric rather than the old fixed 5/10 fallback.

### Interview Completion

Each session contains a maximum of **10 generated questions**. Each session contains at most 10 generated questions. Skipping advances the interview, but a skipped question can be reopened from Question History and answered later without being counted twice. The backend enforces the 10-question generation limit and prevents duplicate completion records.

Skipped questions count toward session completion but are **excluded from the performance average**. The final summary shows completed questions, skipped questions, category scores, strengths, and improvement areas.

### Resume Personalisation

If a resume is uploaded, a bounded excerpt is passed as candidate-specific context to question generation and answer evaluation. The resume is treated as context and is not treated as the candidate's answer.

## Final Verification Checklist

Before a demo/submission, run these quick checks:

1. Start the backend with the configured `backend/.env`.
2. Open `http://localhost:8000` and confirm **KB Ready**.
3. Create a Mixed session and verify the counter starts at **Question 1 of 10**.
4. Skip through all questions and confirm the session ends at **10/10** with no Q11.
5. Start a new session and submit a direct, relevant answer. Confirm the rubric shows relevance/accuracy/completeness/specificity/communication scores.
6. Submit `I don't know` and confirm it receives a low score.
7. Submit a long answer that is clearly unrelated to the question. Confirm it cannot receive a high score.
8. Upload a PDF/TXT resume and confirm the upload is parsed successfully.
9. Open the final summary and confirm answered/skipped counts and category scores are shown.

Automated checks included in `backend/tests/test_core_logic.py` cover the 10-question limit, duplicate completion protection, refusal scoring, irrelevant-answer scoring guardrails, and a relevant-answer high-score path.
