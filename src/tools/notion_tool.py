"""
NotionTool — publishes enriched action items to the Notion database.

Accepts a single item (object) or a batch (array). Batch publishes run in
parallel to reduce end-to-end latency.

Each page gets a rich structured body:
  📋 Assignment   — owner, deadline, priority, status
  ⚠️  Risk Analysis — score, flags
  🚀 Execution    — priority order, dependencies
  💬 Source Quote — exact transcript excerpt
  📝 Context & Notes — side remarks and concerns from the call

After all items are published, call create_sprint_summary() directly from
crew.py to create the grouped owner summary page — keeping the LLM's task
description simple so Groq doesn't generate preamble instead of tool calls.
"""

import json
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Type

from crewai.tools import BaseTool
from notion_client import Client
from pydantic import BaseModel, Field

# Module-level accumulator — populated by each _publish_item call so
# crew.py can call create_sprint_summary() after kickoff completes.
_session_items: list[dict] = []

_MAX_PARALLEL_PUBLISHES = 5


def reset_session() -> None:
    """Clear accumulated items (call before each crew run)."""
    _session_items.clear()


class NotionToolInput(BaseModel):
    action_items_json: str = Field(
        description=(
            "JSON string for one action item (object) or many (array). "
            "Each item must include title (str). Optional: owner, deadline, priority, "
            "risk_score, risk_flags, execution_order, dependencies, source_quote, notes."
        )
    )


# ── Block helpers ──────────────────────────────────────────────────────────────

def _text(content: str) -> dict:
    return {"type": "text", "text": {"content": content}}


def _rich(block_type: str, text: str) -> dict:
    return {"object": "block", "type": block_type, block_type: {"rich_text": [_text(text)]}}


def _h2(text: str) -> dict:
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [_text(text)]}}


def _h3(text: str) -> dict:
    return {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [_text(text)]}}


def _bullet(text: str) -> dict:
    return _rich("bulleted_list_item", text)


def _quote(text: str) -> dict:
    return _rich("quote", text)


def _callout(text: str) -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {"rich_text": [_text(text)], "icon": {"type": "emoji", "emoji": "•"}},
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _parse_items_json(raw: str) -> list[dict]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\]|\{.*\})", raw, re.DOTALL)
        if not match:
            raise ValueError(f"Cannot parse JSON — {raw[:200]}")
        parsed = json.loads(match.group())

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    raise ValueError(f"Expected object or array, got {type(parsed).__name__}")


def _publish_item(data: dict) -> str:
    title = str(data.get("title", "Untitled Action Item")).strip()
    owner = str(data.get("owner", "Unassigned"))
    deadline = str(data.get("deadline", "TBD"))
    priority = str(data.get("priority", "Medium")).strip()
    risk_score = int(data.get("risk_score", 0))
    risk_flags = data.get("risk_flags", [])
    execution_order = data.get("execution_order", "—")
    dependencies = str(data.get("dependencies", "None"))
    source_quote = str(data.get("source_quote", ""))
    notes = data.get("notes", [])

    risk_label = (
        "High Risk" if risk_score >= 70
        else "Medium Risk" if risk_score >= 40
        else "Low Risk"
    )
    flags_str = ", ".join(risk_flags) if risk_flags else "None"

    children = [
        _h3("Assignment"),
        _bullet(f"Owner: {owner}"),
        _bullet(f"Deadline: {deadline}"),
        _bullet(f"Priority: {priority}"),
        _bullet("Status: Not Started"),
        _divider(),
        _h3("Risk Analysis"),
        _bullet(f"Risk Score: {risk_score}/100  ({risk_label})"),
        _bullet(f"Flags: {flags_str}"),
        _divider(),
        _h3("Execution"),
        _bullet(f"Execution Order: #{execution_order}"),
        _bullet(f"Dependencies: {dependencies}"),
    ]

    if source_quote:
        children += [_divider(), _h3("Source Quote"), _quote(source_quote)]

    if notes:
        children.append(_divider())
        children.append(_h3("Context & Notes"))
        for note in (notes if isinstance(notes, list) else [notes]):
            children.append(_bullet(str(note)))

    notion = Client(auth=os.environ["NOTION_TOKEN"])
    database_id = os.environ["NOTION_DATABASE_ID"]

    page = notion.pages.create(
        parent={"database_id": database_id},
        properties={"Name": {"title": [_text(title)]}},
        children=children,
    )
    page_id = page.get("id", "unknown")

    _session_items.append(data)

    return (
        f"Published: '{title}' | Owner: {owner} | Deadline: {deadline} | "
        f"Priority: {priority} | Risk: {risk_score}/100 | Page ID: {page_id}"
    )


# ── Tool ───────────────────────────────────────────────────────────────────────

class NotionTool(BaseTool):
    name: str = "Publish Action Item"
    description: str = (
        "Creates richly formatted action item pages in the Notion database. "
        "Pass a JSON object for one item or a JSON array to publish all items in one call. "
        "Each page includes assignment details, risk analysis, execution order, "
        "dependencies, the source quote from the meeting, and any context/notes."
    )
    args_schema: Type[BaseModel] = NotionToolInput

    def _run(self, action_items_json: str) -> str:
        try:
            items = _parse_items_json(action_items_json)
        except (json.JSONDecodeError, ValueError) as exc:
            return f"Error: {exc}"

        if not items:
            return "Error: No action items provided."

        if len(items) == 1:
            try:
                return _publish_item(items[0])
            except Exception as exc:
                title = items[0].get("title", "?")
                return f"Error publishing '{title}': {exc}"

        results: list[str] = []
        errors: list[str] = []
        workers = min(_MAX_PARALLEL_PUBLISHES, len(items))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_publish_item, item): item for item in items}
            for future in as_completed(futures):
                item = futures[future]
                title = item.get("title", "?")
                try:
                    results.append(future.result())
                except Exception as exc:
                    errors.append(f"Error publishing '{title}': {exc}")

        lines = [f"Batch published {len(results)}/{len(items)} items."]
        lines.extend(results)
        if errors:
            lines.append(f"Failures ({len(errors)}):")
            lines.extend(errors)
        return "\n".join(lines)


# ── Post-run sprint summary (called from crew.py) ─────────────────────────────

def create_sprint_summary() -> str:
    """
    Creates the master Sprint Summary page from items accumulated during the run.
    Call this from crew.py after crew.kickoff() completes.
    """
    items = _session_items
    if not items:
        return "No items accumulated — sprint summary skipped."

    try:
        today = datetime.now().strftime("%B %d, %Y")
        blocks: list[dict] = []

        total = len(items)
        critical_count = sum(1 for i in items if str(i.get("priority", "")).lower() == "critical")
        high_risk_count = sum(1 for i in items if int(i.get("risk_score", 0)) >= 50)

        blocks.append(_callout(
            f"{total} action items  •  {critical_count} critical  •  {high_risk_count} high-risk"
        ))
        blocks.append(_divider())

        # ── Ownership Breakdown ────────────────────────────────────────────────
        blocks.append(_h2("Ownership Breakdown"))
        by_owner: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            raw = str(item.get("owner", "Unassigned")).strip()
            for owner in re.split(r"[,/&]", raw):
                by_owner[owner.strip()].append(item)

        for owner, owned in sorted(by_owner.items()):
            overload = "  [OVERLOADED]" if len(owned) >= 3 else ""
            blocks.append(_h3(f"{owner}  ({len(owned)} item{'s' if len(owned) != 1 else ''}){overload}"))
            for item in sorted(owned, key=lambda x: int(x.get("execution_order", 99))):
                t = item.get("title", "Untitled")
                dl = item.get("deadline", "TBD")
                rs = item.get("risk_score", 0)
                order = item.get("execution_order", "—")
                priority = item.get("priority", "Medium")
                flags = item.get("risk_flags", [])
                flag_str = f"  [{', '.join(flags)}]" if flags else ""
                blocks.append(_bullet(f"#{order}  {priority}  {t}  |  due {dl}  |  risk {rs}/100{flag_str}"))

        blocks.append(_divider())

        # ── Escalations ────────────────────────────────────────────────────────
        escalations = [i for i in items if int(i.get("risk_score", 0)) >= 50]
        if escalations:
            blocks.append(_h2("Escalations  (risk >= 50)"))
            for item in sorted(escalations, key=lambda x: -int(x.get("risk_score", 0))):
                rs = item.get("risk_score", 0)
                t = item.get("title", "Untitled")
                owner = item.get("owner", "Unassigned")
                flags = item.get("risk_flags", [])
                flag_str = f"  [{', '.join(flags)}]" if flags else ""
                blocks.append(_bullet(f"{t}  |  {owner}  |  {rs}/100{flag_str}"))
            blocks.append(_divider())

        # ── Critical Path ──────────────────────────────────────────────────────
        blocks.append(_h2("Critical Path  (execution order)"))
        for item in sorted(items, key=lambda x: int(x.get("execution_order", 99))):
            order = item.get("execution_order", "—")
            t = item.get("title", "Untitled")
            owner = item.get("owner", "Unassigned")
            deps = str(item.get("dependencies", "None"))
            dep_str = (
                f"  <- blocked by: {deps}"
                if deps.lower() not in ("none", "-", "", "n/a")
                else ""
            )
            blocks.append(_bullet(f"#{order}  {t}  [{owner}]{dep_str}"))
        blocks.append(_divider())

        # ── Timeline Conflicts ─────────────────────────────────────────────────
        conflicts: list[str] = []
        for owner, owned in by_owner.items():
            dl_map: dict[str, list[str]] = defaultdict(list)
            for item in owned:
                dl = str(item.get("deadline", "TBD"))[:10]
                dl_map[dl].append(item.get("title", "?"))
            for dl, titles in dl_map.items():
                if len(titles) >= 2:
                    conflicts.append(
                        f"{owner} has {len(titles)} items due {dl}: "
                        + " & ".join(f'"{t}"' for t in titles)
                    )

        if conflicts:
            blocks.append(_h2("Timeline Conflicts"))
            for c in conflicts:
                blocks.append(_bullet(c))
            blocks.append(_divider())

        notion = Client(auth=os.environ["NOTION_TOKEN"])
        database_id = os.environ["NOTION_DATABASE_ID"]

        page = notion.pages.create(
            parent={"database_id": database_id},
            properties={"Name": {"title": [_text(f"Sprint Summary — {today}")]}},
            children=blocks,
        )
        page_id = page.get("id", "unknown")
        owner_list = ", ".join(sorted(by_owner.keys()))
        return (
            f"Sprint Summary published | {total} items | "
            f"Owners: {owner_list} | Escalations: {len(escalations)} | Page ID: {page_id}"
        )

    except Exception as exc:
        return f"Error creating sprint summary: {exc}"
