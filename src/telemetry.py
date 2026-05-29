"""
Neatlogs observability — initialised once at startup, before any LLM imports.

Traces everything automatically:
  - Every LLM call (via LiteLLM instrumentation)
  - Every CrewAI agent execution and task
  - Every tool call (risk_scorer, notion_publisher)

Each pipeline run becomes one WORKFLOW span containing:
  3 AGENT spans -> each with N LLM child spans + timing
  tool calls wired in as children of the agent spans
"""

import os


_BASE_TAGS = [
    "meeting-agent",
    "notion",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "crewai",
]


def init(tags: list[str] | None = None) -> bool:
    """
    Initialise neatlogs. Returns True if tracing is active, False if skipped.
    Called from main.py before any crew/agent imports.
    Optionally accepts run-specific tags; falls back to base tags.
    """
    api_key  = os.getenv("NEATLOGS_API_KEY", "")
    endpoint = os.getenv("NEATLOGS_ENDPOINT", "")

    if not api_key or not endpoint:
        return False

    import logging
    import neatlogs

    logging.getLogger("neatlogs").setLevel(logging.CRITICAL)

    neatlogs.init(
        api_key=api_key,
        endpoint=endpoint,
        workflow_name="Meeting Intelligence",
        instrumentations=["crewai", "litellm"],
        tags=_BASE_TAGS + (tags or []),
        auto_session=True,
        flush_interval=2.0,
        debug=False,
    )
    return True


def retag(tags: list[str]) -> None:
    """
    Update tags for the next run. Re-inits neatlogs with new tag set.
    Call this before each crew run in a batch to keep traces relevant.
    """
    api_key  = os.getenv("NEATLOGS_API_KEY", "")
    endpoint = os.getenv("NEATLOGS_ENDPOINT", "")

    if not api_key or not endpoint:
        return

    import logging
    import neatlogs

    logging.getLogger("neatlogs").setLevel(logging.CRITICAL)

    try:
        neatlogs.init(
            api_key=api_key,
            endpoint=endpoint,
            workflow_name="Meeting Intelligence",
            instrumentations=["crewai", "litellm"],
            tags=_BASE_TAGS + tags,
            auto_session=True,
            flush_interval=2.0,
            debug=False,
        )
    except Exception:
        pass


def workflow_span(func):
    """Decorator that wraps the crew run in a top-level WORKFLOW span."""
    import neatlogs
    return neatlogs.span(kind="WORKFLOW")(func)


def flush() -> None:
    """Force-send any buffered spans. Call after crew.kickoff() completes."""
    try:
        import neatlogs
        neatlogs.flush()
    except Exception:
        pass
