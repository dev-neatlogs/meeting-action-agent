#!/usr/bin/env python3
"""
meeting-agent — interactive terminal

Start:  python main.py
Then use slash commands to control it.
"""

import os
import sys
import time
import threading
from dotenv import load_dotenv

load_dotenv()

# Neatlogs must init before any LLM/CrewAI imports
from src.telemetry import init as _telemetry_init, flush as _telemetry_flush
_TRACING = _telemetry_init()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.rule import Rule
from rich import box as rbox

console = Console()

# ── Pipeline stages (display names + descriptions) ─────────────────────────────

STAGES = [
    ("Meeting Analyst",               "Extract action items from transcript"),
    ("Risk Scorer",                   "Score risks via tool call → flags, escalations"),
    ("Notion Publishing Orchestrator","Publish enriched items → Notion"),
]

_SPINNER = list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")

# ── Demo transcript ────────────────────────────────────────────────────────────

DEMO_TRANSCRIPT = """\
Meeting: Product Team Sprint Planning — April 2, 2026
Attendees: Simran (CPO), Marcus (Lead Engineer), Priya (Senior Designer),
           Tom (QA Lead), Diana (DevOps Engineer), Raj (Backend Engineer),
           Aisha (Data Scientist)

[00:00] Simran: Alright everyone, let's get through sprint planning. We have a lot to cover.
Marcus, what is the status on the authentication service refactor?

[00:45] Marcus: Still in progress. There are some edge cases I am working through.
Should be done by end of next week, maybe.

[01:02] Simran: "Maybe" is not a timeline. Can you commit to a specific date?

[01:15] Marcus: Fine. Friday the 10th. But I need Priya's mockups before I can
start on the frontend portion.

[01:28] Simran: Priya, the new dashboard designs are blocking Marcus. Where are you on those?

[01:35] Priya: I can get the core screens done by Wednesday, but I still need
the final copy from — who is handling that again? I thought Raj was.

[01:48] Raj: I thought you were sending me the copy brief, Simran.

[01:52] Simran: I delegated that to you last week, Raj.
Let's say you have it ready by tomorrow EOD.

[02:05] Raj: That is aggressive but okay, I will make it work.

[02:12] Simran: Good. Diana, I have been hearing that our production deploys are
taking forever — like 40 to 45 minutes. We need to look into that.

[02:23] Diana: Yeah, I have noticed it too. It is probably the test suite bloating
the CI pipeline. I will investigate.

[02:35] Simran: Tom, can you work with Diana on pinpointing the slow tests?

[02:40] Tom: Sure, though I am already heads-down on the regression suite for
the auth service. My plate is pretty full right now.

[02:52] Simran: We need both done. Prioritise the deploy investigation.

[02:57] Tom: Alright. I can have a slow-test report ready by Thursday.

[03:08] Simran: Aisha, the model performance dashboard — where are we?

[03:14] Aisha: Completely blocked. I am waiting on the cleaned dataset from
the new data pipeline. Marcus, I asked you about this two weeks ago.

[03:22] Marcus: Oh right, sorry. I can set up the pipeline access today.

[03:29] Simran: Marcus, also — the API documentation needs to be updated
before the external partner review on the 12th.

[03:38] Marcus: The 12th? That is the same week as the auth refactor deadline.
I genuinely do not think I can deliver both at the same quality.

[03:47] Simran: Let us flag that as a risk and figure it out offline.
Priya, we should also think about mobile responsiveness for the dashboard.
Not necessarily this sprint, but at some point.

[04:00] Priya: Do you want me to scope that out?

[04:04] Simran: Not urgently. And speaking of things that need doing —
someone needs to update the staging environment configuration.
It has been running on the old credentials since January.

[04:18] Tom: I can handle that. When do you need it?

[04:22] Simran: Before the auth service gets promoted to staging.
So before Marcus wraps up on the 10th.

[04:28] Tom: Great, another one for the pile.

[04:35] Simran: Last thing, and this is important — Raj, the security team
sent over an audit report flagging SQL injection vulnerabilities in the
user service. That needs to be addressed immediately.

[04:48] Raj: Understood. I will start on it today.

[04:52] Simran: It needs to go through full code review and Tom needs to
sign off on the QA side before it can merge to main. No shortcuts on this one.

[04:59] Tom: Copy that. Tag me when it is ready for review.

[05:05] Simran: Okay. Friday sync to check in on all of this.
Make sure you are all tracking your items.
"""


# ── Rendering ──────────────────────────────────────────────────────────────────

def _progress_panel(completed: int, times: list[float], done: bool = False) -> Panel:
    frame = _SPINNER[int(time.time() * 8) % len(_SPINNER)]

    table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    table.add_column("n",    width=2,  justify="right", style="dim")
    table.add_column("icon", width=2)
    table.add_column("name", width=36)
    table.add_column("desc", style="dim")
    table.add_column("t",    width=6,  justify="right", style="dim green")

    for i, (name, desc) in enumerate(STAGES):
        if i < completed:
            icon  = Text("✓", style="bold green")
            nstyle = ""
            t     = f"{times[i]:.1f}s" if i < len(times) else ""
        elif i == completed and not done:
            icon  = Text(frame, style="bold cyan")
            nstyle = "bold cyan"
            t     = "…"
        else:
            icon  = Text("○", style="dim")
            nstyle = "dim"
            t     = ""

        table.add_row(str(i + 1), icon, Text(name, style=nstyle), desc, t)

    title = (
        "[bold green]✓ Pipeline Complete[/bold green]"
        if done else
        "[bold cyan]Pipeline Running[/bold cyan]"
    )
    border = "green" if done else "cyan"
    return Panel(table, title=title, border_style=border, padding=(0, 1))


def _result_panel(items_published: int, summary: str, elapsed: float) -> Panel:
    # Parse escalation count from summary string if present
    esc = ""
    if "Escalations:" in summary:
        try:
            n = summary.split("Escalations:")[1].split("|")[0].strip()
            esc = f"  •  {n} escalation{'s' if n != '1' else ''}"
        except Exception:
            pass

    owners = ""
    if "Owners:" in summary:
        try:
            owners = summary.split("Owners:")[1].split("|")[0].strip()
        except Exception:
            pass

    lines = [
        f"[bold green]✓[/bold green]  {items_published} action items published to Notion",
        f"[bold green]✓[/bold green]  Sprint Summary page created{esc}",
    ]
    if owners:
        lines.append(f"[dim]   Owners: {owners}[/dim]")
    lines.append(f"[dim]   Total runtime: {elapsed:.1f}s[/dim]")
    if _TRACING:
        lines.append("[dim]   Trace sent to Neatlogs ✓[/dim]")

    return Panel(
        "\n".join(lines),
        border_style="green",
        padding=(0, 2),
    )


# ── Pipeline runner ────────────────────────────────────────────────────────────

def _validate_env() -> list[str]:
    return [v for v in ("GEMINI_API_KEY", "NOTION_TOKEN", "NOTION_DATABASE_ID") if not os.getenv(v)]


def run_pipeline(transcript: str, verbose: bool = False) -> None:
    missing = _validate_env()
    if missing:
        console.print(f"\n  [bold red]✗ Missing:[/bold red] {', '.join(missing)}")
        console.print("  [dim]Add them to .env and retry.[/dim]\n")
        return

    from src.crew import run as crew_run

    state: dict = {"completed": 0, "times": [], "done": False, "result": None, "summary": None, "error": None}

    def on_task_complete(idx: int, elapsed: float) -> None:
        state["times"].append(elapsed)
        state["completed"] = idx + 1

    def worker() -> None:
        try:
            result, summary = crew_run(transcript, verbose=verbose, on_task_complete=on_task_complete)
            state["result"] = result
            state["summary"] = summary
        except Exception as exc:
            state["error"] = exc
        finally:
            state["done"] = True
            _telemetry_flush()

    console.print()
    start = time.time()

    if verbose:
        # Raw CrewAI output — no live display
        try:
            result, summary = crew_run(transcript, verbose=True, on_task_complete=on_task_complete)
            console.print(f"\n[dim]{summary}[/dim]\n")
        except Exception as exc:
            console.print(f"\n[bold red]Error:[/bold red] {exc}\n")
        return

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    with Live(
        _progress_panel(0, []),
        console=console,
        refresh_per_second=8,
        transient=False,
    ) as live:
        while not state["done"]:
            live.update(_progress_panel(state["completed"], state["times"]))
            time.sleep(0.05)
        # Final update — all complete
        live.update(_progress_panel(len(STAGES), state["times"], done=True))

    t.join()
    elapsed = time.time() - start

    if state["error"]:
        console.print(f"\n  [bold red]✗ Pipeline failed:[/bold red] {state['error']}\n")
        return

    # Count published items from summary string
    items_published = len(state["times"])  # rough proxy; summary has exact count
    if state["summary"] and "items |" in state["summary"]:
        try:
            items_published = int(state["summary"].split("items |")[0].split("|")[-1].strip())
        except Exception:
            pass

    console.print()
    console.print(_result_panel(items_published, state["summary"] or "", elapsed))
    console.print()


# ── REPL ───────────────────────────────────────────────────────────────────────

_COMMANDS = [
    ("/demo",        "run with built-in demo transcript"),
    ("/paste",       "paste a transcript — type END on its own line to finish"),
    ("/file <path>", "load transcript from a file"),
    ("/verbose",     "toggle verbose mode (shows raw agent output)"),
    ("/help",        "show this help"),
    ("/quit",        "exit"),
]


def _print_banner() -> None:
    console.print()
    tracing_line = (
        "[dim]Observability: Neatlogs ✓[/dim]"
        if _TRACING else
        "[dim red]Observability: set NEATLOGS_ENDPOINT to enable tracing[/dim red]"
    )
    console.print(Panel(
        "[bold white]meeting-agent[/bold white]\n"
        "[dim]3-agent AI pipeline  •  Gemini 2.5 Pro/Flash  •  Notion[/dim]\n"
        "[dim]Risk detection  •  Owner resolution  •  Execution strategy[/dim]\n"
        + tracing_line,
        border_style="cyan",
        padding=(1, 4),
        expand=False,
    ))
    console.print()
    _print_help()


def _print_help() -> None:
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("cmd",  style="bold cyan")
    table.add_column("desc", style="dim")
    for cmd, desc in _COMMANDS:
        table.add_row(cmd, desc)
    console.print(table)
    console.print()


def _get_paste() -> str | None:
    console.print("  [dim]Paste your transcript. Type [bold]END[/bold] on a new line when done.[/dim]\n")
    lines: list[str] = []
    while True:
        try:
            line = input("  ")
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)

    if not lines:
        console.print("  [dim red]Nothing entered.[/dim red]\n")
        return None

    transcript = "\n".join(lines)
    words = len(transcript.split())
    console.print(f"\n  [dim]✓ {words} words received[/dim]\n")
    return transcript


def _load_file(path: str) -> str | None:
    try:
        with open(path.strip(), "r", encoding="utf-8") as f:
            content = f.read()
        words = len(content.split())
        console.print(f"  [dim]✓ Loaded {words} words from {path}[/dim]\n")
        return content
    except FileNotFoundError:
        console.print(f"  [bold red]✗ File not found:[/bold red] {path}\n")
        return None
    except Exception as exc:
        console.print(f"  [bold red]✗ Error reading file:[/bold red] {exc}\n")
        return None


def main() -> None:
    _print_banner()

    verbose = False

    while True:
        try:
            raw = input("❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n  [dim]Bye![/dim]\n")
            break

        if not raw:
            continue

        cmd = raw.lower()

        if cmd in ("/quit", "/exit", "q", "quit", "exit"):
            console.print("\n  [dim]Bye![/dim]\n")
            break

        elif cmd == "/demo":
            run_pipeline(DEMO_TRANSCRIPT, verbose)

        elif cmd == "/paste":
            transcript = _get_paste()
            if transcript:
                run_pipeline(transcript, verbose)

        elif raw.startswith("/file"):
            path = raw[5:].strip()
            if not path:
                console.print("  [dim red]Usage: /file <path>[/dim red]\n")
            else:
                transcript = _load_file(path)
                if transcript:
                    run_pipeline(transcript, verbose)

        elif cmd == "/verbose":
            verbose = not verbose
            state = "on" if verbose else "off"
            icon  = "[on]" if verbose else "[off]"
            console.print(f"  [dim]{icon}  Verbose mode: {state}[/dim]\n")

        elif cmd in ("/help", "help", "?", "h"):
            _print_help()

        else:
            console.print("  [dim]Unknown command — type [bold cyan]/help[/bold cyan][/dim]\n")


if __name__ == "__main__":
    main()
