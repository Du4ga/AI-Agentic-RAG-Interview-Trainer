# Final QA Notes

This build preserves the polished frontend and makes only targeted functional changes.

## Fixed
- IBM Granite evaluation now retries once when watsonx returns an empty response.
- Invalid/unavailable Granite evaluation no longer falls back to a fixed 5/10.
- Local fallback scoring distinguishes refusals, irrelevant answers, partial answers, and well-supported answers.
- Long irrelevant answers are capped by deterministic relevance guardrails.
- Skipped questions can be reopened and answered later without double-counting.
- Question history exposes skipped questions as actionable "return" items.
- The session remains capped at 10 generated questions.

## Verification performed
- Python syntax compilation passed for all backend modules.
- JavaScript syntax check passed.
- Automated backend tests passed, including the 10-question cap, refusal guard, irrelevant-answer guard, high-quality answer path, and skipped-question recovery.

## Run
From `backend`:
`python main.py`

Then open:
`http://localhost:8000`
