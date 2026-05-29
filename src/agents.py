"""
Three-agent pipeline.

  meeting_analyst      → pure LLM — extracts action items as structured JSON
  risk_scorer_agent    → calls risk_scorer tool (deterministic Python scorer)
  notion_orchestrator  → calls notion_publisher tool (one call per item)

Trace topology:
  meeting_analyst     → 1-2 LLM calls
  risk_scorer_agent   → 1 LLM call + 1 tool call (risk_scorer)
  notion_orchestrator → 1 LLM call + N tool calls (notion_publisher, one per item)
"""

from crewai import Agent
from src.config import llm_flash as LLM_FLASH
from src.config import llm_pro as LLM_PRO
from src.tools import NotionBatchTool, RiskScorerTool

_notion_tool = NotionBatchTool()
_risk_tool = RiskScorerTool()


meeting_analyst = Agent(
    role="Meeting Intelligence Analyst",
    goal=(
        "Analyse the meeting transcript and extract every action item as a "
        "structured JSON list. Each item must have id, title, owner, deadline, "
        "priority, and source_quote. Also capture the meeting type, participants, "
        "and key decisions made."
    ),
    backstory=(
        "You are a senior business analyst who has sat in on thousands of meetings. "
        "You read between the lines — you catch the unspoken tension, the ambiguous "
        "delegation, the optimistic deadline that has 'slip' written all over it. "
        "Your structured output feeds directly into the risk scorer."
    ),
    llm=LLM_PRO,
    verbose=False,
)


risk_scorer_agent = Agent(
    role="Risk & Priority Analyst",
    goal=(
        "Perform multi-pass risk analysis on the extracted action items. "
        "Flag vague items, missing deadlines on high-priority work, security-sensitive "
        "items, and overloaded owners. Assign a risk_score (0-100) and execution_order "
        "to each item, then produce the final enriched JSON ready for publishing."
    ),
    backstory=(
        "You are a risk engineer who has been burned by missed items, vague tasks, "
        "and overloaded team members too many times. You are systematic: you run "
        "every item through each detection pass and produce clean structured output "
        "that the publisher can use directly."
    ),
    llm=LLM_PRO,
    tools=[_risk_tool],
    verbose=False,
)


notion_orchestrator = Agent(
    role="Notion Publishing Orchestrator",
    goal=(
        "Publish every action item to Notion using the Publish Action Items tool. "
        "Call the tool exactly once with the full list of enriched action items. "
        "Never skip items — the tool must receive the complete payload."
    ),
    backstory=(
        "You are meticulous and patient. This publishing step is latency-sensitive, "
        "so you always use the batch publishing tool and send the full list of "
        "action items in one call. Every item deserves its own page."
    ),
    llm=LLM_FLASH,
    tools=[_notion_tool],
    verbose=False,
)
