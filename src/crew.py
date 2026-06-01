import os
import time
from typing import Callable, Optional
from crewai import Crew, Process
from src.agents import meeting_analyst, risk_scorer_agent, notion_orchestrator
from src.tasks import build_tasks
from src.tools import create_sprint_summary, reset_session
from src.config import llm_fast, llm_slow, FAST_MODEL_WORD_THRESHOLD

_AGENTS = [
    meeting_analyst,
    risk_scorer_agent,
    notion_orchestrator,
]


def _traced_run(func):
    """Wrap func in a neatlogs WORKFLOW span if tracing is configured."""
    if os.getenv("NEATLOGS_API_KEY") and os.getenv("NEATLOGS_ENDPOINT"):
        try:
            import neatlogs
            return neatlogs.span(kind="WORKFLOW", name="Process Meeting")(func)
        except Exception:
            pass
    return func


def run(
    transcript: str,
    verbose: bool = False,
    on_task_complete: Optional[Callable[[int, float], None]] = None,
) -> tuple[str, str]:
    """
    Assemble and kick off the 7-agent pipeline.

    Returns:
        (result_str, summary_str) — pipeline final output + sprint summary status
    """
    reset_session()

    # Model routing: large transcripts tend to create extreme prompt token
    # counts, which can lead to large tail latencies on some providers/models.
    # We switch to a faster model when the input is large.
    transcript_words = len(transcript.split())
    use_fast = transcript_words >= FAST_MODEL_WORD_THRESHOLD
    if use_fast:
        meeting_analyst.llm = llm_fast
        risk_scorer_agent.llm = llm_fast
    else:
        meeting_analyst.llm = llm_slow
        risk_scorer_agent.llm = llm_slow

    # Wrap the inner kickoff in a WORKFLOW span so every LLM call is a child
    @_traced_run
    def process_meeting():
        return crew.kickoff()

    # Set verbosity on all agents
    for agent in _AGENTS:
        agent.verbose = verbose

    tasks = build_tasks(transcript)

    task_idx = [0]
    task_start = [time.time()]

    def _step_throttle(step_output) -> None:
        time.sleep(1)

    def _task_done(output) -> None:
        elapsed = time.time() - task_start[0]
        if on_task_complete:
            on_task_complete(task_idx[0], elapsed)
        task_idx[0] += 1
        task_start[0] = time.time()

    crew = Crew(
        agents=_AGENTS,
        tasks=tasks,
        process=Process.sequential,
        verbose=verbose,
        step_callback=_step_throttle,
        task_callback=_task_done,
    )

    result = process_meeting()
    summary = create_sprint_summary()

    return str(result), summary
