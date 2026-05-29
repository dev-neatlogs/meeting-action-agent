"""
Three sequential tasks — one per agent.
"""

from crewai import Task
from src.agents import meeting_analyst, risk_scorer_agent, notion_orchestrator


def build_tasks(transcript: str) -> list[Task]:

    # ── Task 1: Extract action items ──────────────────────────────────────────
    extract_actions = Task(
        description=(
            "Analyse this meeting transcript and extract every action item.\n\n"
            f"TRANSCRIPT:\n{transcript}\n\n"
            "Output TWO sections:\n\n"
            "SECTION 1 — MEETING SUMMARY\n"
            "Meeting type, participants (name + role), and key decisions made.\n\n"
            "SECTION 2 — ACTION ITEMS (JSON array)\n"
            "Output a JSON array where each item has:\n"
            '  "id": "ACTION-001" (increment),\n'
            '  "title": "verb-first specific description",\n'
            '  "owner": "name or Unassigned",\n'
            '  "deadline": "specific date or TBD",\n'
            '  "priority": "Critical | High | Medium | Low",\n'
            '  "source_quote": "exact quote from transcript"\n\n'
            "Capture every commitment, task, and follow-up — including vague ones."
        ),
        expected_output=(
            "MEETING SUMMARY section followed by a JSON array of action items "
            "with id, title, owner, deadline, priority, source_quote."
        ),
        agent=meeting_analyst,
    )

    # ── Task 2: Risk scoring & enrichment ────────────────────────────────────
    score_risks = Task(
        description=(
            "Score the action items from the meeting analyst using the Analyse Risk & Priority tool.\n\n"
            "Step 1: Call the Analyse Risk & Priority tool with the full JSON array as items_json.\n\n"
            "Step 2: Take the scored_items from the tool result and add three fields to each:\n"
            '  "execution_order": int (1 = do first — unblocked, highest priority),\n'
            '  "dependencies": "ACTION-NNN or None",\n'
            '  "notes": ["concerns or constraints mentioned in the meeting"]\n\n'
            "Step 3: Output the final enriched JSON array labelled PUBLISH-READY JSON:"
        ),
        expected_output=(
            "PUBLISH-READY JSON: followed by a complete JSON array where every item has "
            "id, title, owner, deadline, priority, source_quote, risk_score, "
            "risk_flags, execution_order, dependencies, notes."
        ),
        agent=risk_scorer_agent,
        context=[extract_actions],
    )

    # ── Task 3: Publish to Notion ─────────────────────────────────────────────
    publish_to_notion = Task(
        description=(
            "Publish every action item from the PUBLISH-READY JSON to Notion.\n\n"
            "Call the Publish Action Items tool ONCE with the full JSON array.\n\n"
            "The tool will publish each item and return per-item SUCCESS/FAILED.\n"
            "After all items are processed, return a PUBLISH SUMMARY:\n"
            "- Total items published\n"
            "- Each item: title | owner | priority | risk_score | status\n"
            "- Overall result: SUCCESS / PARTIAL / FAILED"
        ),
        expected_output=(
            "PUBLISH SUMMARY listing every item with owner, priority, risk score, "
            "and publish status. Overall pipeline result at the bottom."
        ),
        agent=notion_orchestrator,
        context=[score_risks],
    )

    return [extract_actions, score_risks, publish_to_notion]
