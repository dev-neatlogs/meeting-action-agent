# meeting-action-agent

A CrewAI-powered Python tool that reads a meeting transcript, extracts action items, assigns owners, and pushes everything to a Notion database — automatically.

## What it does

Three specialised AI agents work sequentially:

1. **Transcript Analyst** — reads the raw meeting transcript and extracts every task, commitment, and follow-up with deadline and priority context.
2. **Owner Assigner** — reviews the extracted items and refines ownership based on who said what in the conversation.
3. **Notion Publisher** — takes the final structured list and creates one Notion database page per action item, with owner, deadline, priority, and status written into the page body.

All agents run on **Groq's `llama-3.3-70b-versatile`** model via CrewAI's built-in LiteLLM integration.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```
GROQ_API_KEY=your_groq_api_key
NOTION_TOKEN=your_notion_integration_token
NOTION_DATABASE_ID=your_notion_database_id
SENDGRID_API_KEY=your_sendgrid_api_key
```

To get these:
- **GROQ_API_KEY**: [console.groq.com](https://console.groq.com)
- **NOTION_TOKEN**: Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations), then share your database with it
- **NOTION_DATABASE_ID**: The 32-character ID from your Notion database URL
- **SENDGRID_API_KEY**: SendGrid API key with **"Mail Send"** permission (used by the optional `Send Email` tool)

## Usage

### Demo mode (built-in sample transcript)

```bash
python main.py --demo
```

### From a file

```bash
python main.py --file /path/to/transcript.txt
```

### Inline text

```bash
python main.py --text "Alice: can you finish the report by Friday? Bob: Yes, I'll do it."
```

### From stdin

```bash
cat transcript.txt | python main.py
```

## What gets created in Notion

For each action item, the agent creates a new page in your Notion database with:

- **Name** (title): the action item description
- **Page body** (bulleted list):
  - Owner: the person responsible
  - Deadline: specific date or TBD
  - Priority: High / Medium / Low
  - Status: Not Started

The tool writes all metadata into the page body to ensure compatibility with any Notion database schema — no column setup required beyond the default "Name" title column.

## Example output

Given the demo transcript (a Q2 planning meeting with Sarah, Marcus, Priya, and Tom), the agent will extract items like:

- Finish API integration — Marcus, by Friday, High
- Design onboarding screens — Priya, by Wednesday, High
- Complete regression testing — Tom, by April 15, High
- Send roadmap to stakeholders — Sarah, today, Medium
- Update API documentation — Marcus, TBD, Medium
- Set up staging environment — Tom, tomorrow, Medium

Each becomes a separate Notion page.

## Project structure

```
meeting-action-agent/
├── .env                    # credentials (gitignored)
├── .env.example            # template with blank values
├── .gitignore
├── requirements.txt
├── README.md
├── main.py                 # CLI entry point
└── src/
    ├── __init__.py
    ├── agents.py           # CrewAI agent definitions
    ├── tasks.py            # CrewAI task definitions
    ├── crew.py             # Crew assembly and kickoff
    └── notion_tool.py      # Custom CrewAI tool to push to Notion
```
