"""investment_research_workflow — investment research demo with triaged prompt fixes.

Run modes via env var RUN={BROKEN,FIXED}:
  BROKEN — unsanitized questions + legacy researcher prompt (may 400 on OpenAI).
  FIXED  — sanitize questions, moderation pre-check, policy-safe prompt templates.

Example:
    COMPANY=Microsoft RUN=FIXED python investment_research.py
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# --- 1. Init MUST happen before OpenAI imports
import neatlogs

neatlogs.init(
    api_key=os.environ["NEATLOGS_API_KEY"],
    endpoint=os.environ.get("NEATLOGS_ENDPOINT"),
    workflow_name="investment_research_workflow",
    tags=["sdk-examples", "investment-research", "triaged", "azure-openai"],
    instrumentations=["openai"],
    capture_logs=True,
    pii_enabled=True,
    pii_span_types=["LLM"],
)

# --- 2. OpenAI client after neatlogs init
from openai import AzureOpenAI, BadRequestError

from moderation import assert_moderation_passes, check_moderation
from prompt_sanitizer import sanitize_research_questions
from prompts import RESEARCHER_SYSTEM, RESEARCHER_SYSTEM_BROKEN, RESEARCHER_USER
from research_questions import (
    MICROSOFT_RESEARCH_QUESTIONS,
    MICROSOFT_RESEARCH_QUESTIONS_BROKEN,
)

_ACTIVE: dict[str, Any] = {}


def _azure_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    )


def _format_questions(questions: list[str]) -> str:
    return "\n".join(f"{idx}. {question}" for idx, question in enumerate(questions, start=1))


@neatlogs.span(kind="TOOL", name="Sanitize Research Questions", tool_name="Sanitize Research Questions")
def sanitize_questions_span(questions: list[str]) -> list[str]:
    sanitized = sanitize_research_questions(questions)
    neatlogs.log(
        "Sanitized {count} research question(s) for policy-safe LLM input",
        count=len(sanitized),
    )
    return sanitized


@neatlogs.span(kind="TOOL", name="Moderation Pre-Check", tool_name="Moderation Pre-Check")
def moderation_precheck_span(prompt_text: str) -> dict:
    client = _azure_client()
    result = check_moderation(client, prompt_text)
    neatlogs.log(
        "Moderation {status} via {model}",
        status="passed" if result.passed else "flagged",
        model=result.model,
    )
    if not result.passed:
        flagged = [name for name, active in result.categories.items() if active]
        raise ValueError(f"Prompt blocked by moderation: {', '.join(flagged)}")
    return {
        "flagged": result.flagged,
        "model": result.model,
        "categories": result.categories,
    }


@neatlogs.span(kind="AGENT", name="Researcher", capture_input=False)
def run_researcher() -> str:
    """Draft investment research memo from run-scoped prompt templates."""
    company = _ACTIVE["company"]
    questions = _ACTIVE["questions"]
    system_tpl = _ACTIVE["system_tpl"]
    user_tpl = _ACTIVE["user_tpl"]
    questions_block = _format_questions(questions)

    with neatlogs.trace(
        "Generate Research Memo",
        kind="LLM",
        system_prompt_template=system_tpl,
        user_prompt_template=user_tpl,
    ):
        compiled_system = system_tpl.compile()
        compiled_user = user_tpl.compile(company=company, questions=questions_block)
        prompt_for_moderation = f"{compiled_system}\n\n{compiled_user}"

        if _ACTIVE.get("use_moderation_precheck"):
            assert_moderation_passes(_azure_client(), prompt_for_moderation)

        client = _azure_client()
        resp = client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            messages=[
                {"role": "system", "content": compiled_system},
                {"role": "user", "content": compiled_user},
            ],
        )
    return resp.choices[0].message.content or ""


@neatlogs.span(kind="WORKFLOW", name="Investment Research", capture_input=False)
def investment_research_workflow() -> dict:
    from opentelemetry import trace as _otel_trace

    company = _ACTIVE["company"]
    questions = _ACTIVE["questions"]
    span = _otel_trace.get_current_span()
    span.set_attribute("input.value", f"Company: {company}\nQuestions: {len(questions)}")
    span.set_attribute("input.mime_type", "text/plain")
    span.set_attribute("neatlogs.workflow.input", company)

    neatlogs.log(
        "Starting investment research for {company} ({count} questions)",
        company=company,
        count=len(questions),
    )

    if _ACTIVE.get("sanitize_questions"):
        questions = sanitize_questions_span(questions)
        _ACTIVE["questions"] = questions

    memo = run_researcher()
    return {
        "company": company,
        "question_count": len(questions),
        "memo_preview": memo[:500],
        "memo": memo,
    }


def _activate_run(
    *,
    company: str,
    questions: list[str],
    system_tpl,
    user_tpl,
    sanitize_questions: bool,
    use_moderation_precheck: bool,
) -> None:
    _ACTIVE.clear()
    _ACTIVE.update(
        {
            "company": company,
            "questions": questions,
            "system_tpl": system_tpl,
            "user_tpl": user_tpl,
            "sanitize_questions": sanitize_questions,
            "use_moderation_precheck": use_moderation_precheck,
        }
    )


def run_broken(company: str = "Microsoft") -> dict:
    _activate_run(
        company=company,
        questions=list(MICROSOFT_RESEARCH_QUESTIONS_BROKEN),
        system_tpl=RESEARCHER_SYSTEM_BROKEN,
        user_tpl=RESEARCHER_USER,
        sanitize_questions=False,
        use_moderation_precheck=False,
    )
    return investment_research_workflow()


def run_fixed(company: str = "Microsoft") -> dict:
    _activate_run(
        company=company,
        questions=list(MICROSOFT_RESEARCH_QUESTIONS_BROKEN),
        system_tpl=RESEARCHER_SYSTEM,
        user_tpl=RESEARCHER_USER,
        sanitize_questions=True,
        use_moderation_precheck=True,
    )
    return investment_research_workflow()


RUNS = {"BROKEN": run_broken, "FIXED": run_fixed}


def main() -> int:
    mode = os.environ.get("RUN", "FIXED").upper()
    company = os.environ.get("COMPANY", "Microsoft")

    if mode not in RUNS:
        print(f"Unknown RUN={mode}. Choose from {sorted(RUNS)}", file=sys.stderr)
        return 2

    result_payload = None
    error_payload = None
    try:
        result_payload = RUNS[mode](company=company)
    except (BadRequestError, ValueError) as exc:
        error_payload = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        neatlogs.flush()
        import time

        time.sleep(2)
        neatlogs.shutdown()

    print(json.dumps({"mode": mode, "company": company, "result": result_payload, "error": error_payload}, indent=2))
    return 0 if error_payload is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
