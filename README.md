# Jobs Agent

An autonomous AI job search agent that scrapes 20+ job sources (LinkedIn + VC portfolio boards), intelligently filters for roles you want (configurable on the settings page, it is AI/ML roles by default), scores them with AI, and learns from results to improve search strategies over time.

<img width="1263" height="615" alt="image" src="https://github.com/user-attachments/assets/5ab56b70-cf8c-4b79-b461-417f7a77ccfe" />
<img width="1213" height="618" alt="image" src="https://github.com/user-attachments/assets/ad7b1ff8-68d4-44d4-8303-d6f1126e564f" />
<img width="1199" height="623" alt="image" src="https://github.com/user-attachments/assets/dc89a046-503d-499e-8229-6cfee4e47a3d" />
<img width="1227" height="626" alt="image" src="https://github.com/user-attachments/assets/1a9491e3-5b78-4f43-b750-249b24e4f740" />


## Features

- **20+ Job Sources** — LinkedIn (7 keyword searches - configurable) + 19 VC portfolio boards (a16z, Sequoia, Accel, Battery, General Catalyst, and more)
- **AI Scoring** — Each job is scored 1-10 by Groq LLM based on your resume and preferences
- **Smart Filters** — Automatically filters senior roles, hybrid positions, and non-AI titles
- **Autonomous Agent** — LLM-driven decision loop that decides what to search, when to research companies, when to email you, and when to reflect on strategy performance
- **Chat Interface** — Ask questions about your saved jobs, get stats, or trigger agent cycles
- **Settings Page** — Configure API keys, search keywords, and upload your resume via the dashboard
- **Web Dashboard** — Filter, sort, and browse all jobs with AI scores

## Quick Start

### Prerequisites

- Python 3.10+
- [Groq API key](https://console.groq.com) (free tier available, need to input it manually to .env or set it on the settings page)

### Installation

```bash
git clone <repo-url>
cd jobs_agent
pip install -r requirements.txt
playwright install chromium
```

### Configuration

Copy the example env file and add your Groq API key:

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```
GROQ_API_KEY="gsk_your_key_here"
```

### Run

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000 in your browser.

## Project Structure

```
app/
  main.py              # FastAPI routes and dashboard
  config.py            # Configuration constants
  database.py          # SQLAlchemy models (Job, ScrapeLog, Setting, etc.)
  scheduler.py         # APScheduler for periodic scraping + agent cycles
  ai/
    engine.py          # Groq LLM integration for job scoring
  scrapers/
    base.py            # JobData dataclass, BaseScraper, shared JSON-LD parser
    linkedin.py        # LinkedIn guest API scraper
    consider.py        # Consider-powered VC board scrapers (Playwright)
    getro.py           # Getro-powered VC board scrapers
    custom.py          # Custom board scrapers (Generation She, January Ventures)
  agent/
    engine.py          # JobAgent — THINK -> ACT -> LEARN loop
    tools/
      skill_analysis.py  # Resume vs job description gap analysis
      email_notifier.py  # SMTP email digests
      web_research.py    # Company info research
  sheets/
    export.py          # Google Sheets export (optional)
  utils/
    env_writer.py      # .env file reader/writer
  templates/           # Jinja2 templates (dashboard, logs, chat, settings)
  static/
    style.css          # Dark premium design system
data/
  jobs.db              # SQLite database (auto-created)
```

## How the Agent Works

Every `AGENT_CYCLE_HOURS` (default: 4), the agent runs one cycle:

1. **Build Context** — Gathers active strategies, recent actions, DB stats, and persistent memory
2. **Decide (LLM)** — Reviews context and picks the most valuable next action: SEARCH, RESEARCH, SEND_EMAIL, REFLECT, or WAIT
3. **Execute** — Runs the chosen action
4. **Learn** — Updates strategy priority scores, logs the action, updates memory

Strategy priority adjusts automatically:
- Yield > 30% → priority boosted
- Yield < 5% → priority reduced
- Zero yield after 20+ runs with priority ≤ 1 → auto-deactivated

## Job Sources

| Category | Sources |
|---|---|
| LinkedIn | 7 keyword searches (AI Engineer, AI Builder, AI Product Manager, etc.) |
| VC Boards (Consider) | a16z, Accel, Bain Capital, Battery, Conversion Capital, Craft Ventures, Female Founders, Forerunner, Gaingels, Headline, LSVP, Sequoia, Serena, Sogal |
| VC Boards (Getro) | BBG Ventures, Canvas, General Catalyst |
| Custom Boards | Generation She, January Ventures |

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python FastAPI |
| Frontend | Jinja2 + Alpine.js + HTMX |
| Database | SQLite (SQLAlchemy) |
| Scraping | httpx + BeautifulSoup + Playwright |
| AI | Groq API |
| Scheduling | APScheduler |
