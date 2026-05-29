#!/usr/bin/env python3
"""
Partial publish debug run.

8 action items scored — only 7 published.
The 4th notion_publisher call (a Critical security item) fails with a
simulated Notion API rate-limit error. The orchestrator receives the
error string, logs no retry, and moves on.

What the trace surfaces:
  - risk_scorer:        8 items enriched, 1 flagged SECURITY_SENSITIVE + Critical
  - notion_publisher:   8 tool calls visible, call #4 returns an error string
  - sprint_summary:     7 items (the Critical item is missing — no one noticed)

Debug question: "Risk scorer shows 8 items, sprint summary shows 7.
  Which one dropped? Looking at the trace... tool call #4 errored.
  Why didn't the orchestrator retry it?"
"""

import threading
from dotenv import load_dotenv
load_dotenv()

from src.telemetry import init as _telemetry_init, retag, flush
_telemetry_init()

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.live import Live

console = Console()

RUN = {
"title": "API Platform Security Review — Sprint Kickoff",
"tags": ["partial-publish", "silent-drop", "notion-error", "retry-missing", "critical-dropped"],
"transcript": """\
Meeting: API Platform Security Review — Sprint Kickoff
Date: April 4, 2026
Attendees: Priya (Engineering Lead), Seb (Backend Engineer), Zoe (Security),
           Marcus (DevOps), Tara (QA Lead), Leon (Product)

[00:00] Priya: Let's move fast. We have the security audit results back and
there are items we need to close before the partner integration goes live.
Everyone needs to leave with a named task and a date.

[00:18] Zoe: First and most urgent — the partner API has no authentication
on the /internal/sync endpoint. Any authenticated user in our system can
call it and read raw partner data. This is a P0. Seb, you need to patch
this today.

[00:32] Seb: Confirmed, I know the endpoint. I'll have a fix up for review
by 3pm.

[00:38] Zoe: Tara, I need you to write a test that would catch this class
of auth bypass — unauthenticated access to internal routes. We cannot rely
on manual review for these.

[00:48] Tara: I can have that test written by end of day alongside Seb's fix.

[00:55] Priya: Good. Marcus — the API gateway access logs are only retained
for 7 days. If this endpoint was being probed before we caught it, we have
no visibility. We need 90-day retention minimum.

[01:10] Marcus: I'll update the log retention config. Done by tomorrow EOD.

[01:18] Leon: On the product side — the partner integration dashboard has no
rate limiting on the data export endpoint. Partners can pull unlimited records.
We have one partner already pulling 500k rows a day. Seb, can you add rate
limiting there too?

[01:32] Seb: Rate limiting on the export endpoint — yes, I can do that.
Give me until Monday.

[01:40] Priya: Zoe, the API keys issued to partners — they never expire.
We have keys from the original pilot two years ago still active.

[01:50] Zoe: That needs to go on the remediation list. I'll write up the
key rotation policy and send it to all active partners. Two weeks — April 18th.

[02:00] Priya: Marcus, while we are on infrastructure — the staging environment
is running the old API gateway version. The security patches from last month
never got applied to staging. That needs to match prod.

[02:12] Marcus: I'll do a full staging sync this week, Thursday.

[02:20] Tara: One more from QA — we have no automated regression suite for
the auth layer. Every time someone touches auth code we are relying on
manual spot checks. Given today's finding, that is clearly not enough.

[02:32] Priya: Tara, scope out an auth regression suite. When can you
have a first pass?

[02:38] Tara: First pass by April 11th. I will need Seb to review the
test cases for the internal endpoint logic.

[02:48] Priya: Seb, flag that as a dependency. Okay — everyone has an item.
Let's close this out.
"""}


# ── Inject failure on call #4 ──────────────────────────────────────────────────

def _patch_notion_tool():
    """
    Monkey-patch NotionBulkTool._run to simulate a Notion API 429 error on the
    4th item within a single bulk publishing call.

    The bulk tool must still:
      - publish the other items
      - report per-item SUCCESS/FAILED
      - feed only successful items into sprint summary
    """
    import json
    import os
    import threading as _threading  # noqa: F401 (keeps existing import shape)
    from notion_client import Client

    import src.tools.notion_tool as notion_mod

    NotionBulkTool = notion_mod.NotionBulkTool
    _parse_items_json = notion_mod._parse_items_json
    _build_children_for_item = notion_mod._build_children_for_item

    def _patched_run(self, items_json: str) -> str:
        items = _parse_items_json(items_json)

        notion = Client(auth=os.environ["NOTION_TOKEN"])
        database_id = os.environ["NOTION_DATABASE_ID"]

        results: list[dict] = []
        success_count = 0

        for idx, item in enumerate(items, start=1):
            try:
                if idx == 4:
                    raise Exception(
                        "notion_client.errors.APIResponseError: Request to Notion API failed "
                        "with status 429 — rate_limited: The user or workspace is rate limited. "
                        "Retry-After: 32"
                    )

                children, normalized_item = _build_children_for_item(item)
                page = notion.pages.create(
                    parent={"database_id": database_id},
                    properties={"Name": {"title": [notion_mod._text(normalized_item.get("title", "Untitled"))]}},
                    children=children,
                )
                page_id = page.get("id", "unknown")

                notion_mod._session_items.append(normalized_item)
                success_count += 1

                results.append(
                    {
                        "status": "SUCCESS",
                        "page_id": page_id,
                        "id": normalized_item.get("id"),
                        "title": normalized_item.get("title"),
                        "owner": normalized_item.get("owner"),
                        "priority": normalized_item.get("priority"),
                        "risk_score": normalized_item.get("risk_score"),
                    }
                )
            except Exception as exc:
                title = str(item.get("title", "Untitled Action Item")).strip()
                owner = str(item.get("owner", "Unassigned"))
                results.append(
                    {
                        "status": "FAILED",
                        "error": str(exc),
                        "id": item.get("id"),
                        "title": title,
                        "owner": owner,
                        "priority": item.get("priority"),
                        "risk_score": item.get("risk_score"),
                    }
                )

        return json.dumps(
            {
                "counts": {"success": success_count, "failed": len(results) - success_count},
                "results": results,
            },
            indent=2,
        )

    NotionBulkTool._run = _patched_run


_patch_notion_tool()


# ── Runner (same boilerplate as other run scripts) ─────────────────────────────

def run_it() -> None:
    from src.crew import run as crew_run
    from main import STAGES, _progress_panel, _result_panel

    retag(RUN["tags"])
    console.print(Rule(f"[bold cyan]{RUN['title']}[/bold cyan]", style="cyan"))
    console.print()

    state: dict = {"completed": 0, "times": [], "done": False,
                   "result": None, "summary": None, "error": None}

    def on_task_complete(i: int, elapsed: float) -> None:
        state["times"].append(elapsed)
        state["completed"] = i + 1

    def worker() -> None:
        try:
            result, summary = crew_run(RUN["transcript"], verbose=False,
                                       on_task_complete=on_task_complete)
            state["result"] = result
            state["summary"] = summary
        except Exception as exc:
            state["error"] = exc
        finally:
            state["done"] = True

    import time as t
    start = t.time()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    with Live(_progress_panel(0, []), console=console, refresh_per_second=8) as live:
        while not state["done"]:
            live.update(_progress_panel(state["completed"], state["times"]))
            t.sleep(0.05)
        live.update(_progress_panel(len(STAGES), state["times"], done=True))

    thread.join()
    elapsed = t.time() - start

    if state["error"]:
        console.print(f"  [bold red]✗ Failed:[/bold red] {state['error']}\n")
        return

    items_published = len(state["times"])
    if state["summary"] and "items |" in state["summary"]:
        try:
            items_published = int(state["summary"].split("items |")[0].split("|")[-1].strip())
        except Exception:
            pass

    console.print()
    console.print(_result_panel(items_published, state["summary"] or "", elapsed))
    console.print()
    flush()


if __name__ == "__main__":
    console.print()
    console.print(Panel(
        "[bold white]partial publish debug run[/bold white]\n"
        "[dim]API Platform Security Review — Notion call #4 fails, Critical item dropped[/dim]",
        border_style="cyan", padding=(1, 4), expand=False,
    ))
    console.print()
    run_it()
