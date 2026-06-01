# Investment Research Workflow (Triaged)

Demo workflow for institutional investment research with triage fixes for OpenAI usage-policy violations.

## What changed

| Area | Before (BROKEN) | After (FIXED) |
|---|---|---|
| Research questions | Raw phrases like "antitrust risk", "regulatory scrutiny" | Sanitized via `prompt_sanitizer.py` |
| Researcher system prompt | Direct enforcement/legal exposure framing | Neutral investment-research language |
| Pre-flight checks | None | OpenAI Moderation API gate before LLM call |

## Setup

```bash
cd investment_research_workflow
cp .env.example .env
pip install -r requirements.txt
```

## Run

**Fixed path (Microsoft verification):**

```bash
RUN=FIXED COMPANY=Microsoft python investment_research.py
```

**Broken regression (may return OpenAI 400):**

```bash
RUN=BROKEN COMPANY=Microsoft python investment_research.py
```

## Tests

From repo root:

```bash
python -m unittest discover -s investment_research_workflow/tests -v
```

Tests cover phrase sanitization and moderation helper behavior (mocked — no API key required).
