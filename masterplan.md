# Jobs Agent — Master Plan

## Mission
An autonomous AI job search agent that scrapes 20+ job sources (LinkedIn + VC portfolio boards), intelligently filters for **AI/ML roles**, scores them with AI, and proactively hunts for the best-matched roles — with autonomous decision-making, adaptive search strategies, and email notifications.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    JobAgent (decision loop)                   │
│  Every 4h: THINK → ACT(SEARCH|RESEARCH|SEND_EMAIL|REFLECT)   │
└──────┬──────────┬──────────┬──────────┬─────────────────────┘
       │          │          │          │
  ┌────▼──┐  ┌────▼───┐  ┌──▼───┐  ┌──▼──────────┐
  │Scrapers│  │ Tools  │  │Email  │  │Web          │
  │(6 types)│  │(skill  │  │Notifier│  │Dashboard    │
  │       │  │analysis│  │       │  │(HTMX)       │
  └────┬──┘  └────┬───┘  └──┬───┘  └──┬──────────┘
       │          │         │         │
  ┌────▼──────────▼─────────▼─────────▼──────┐
  │            AI Engine (Groq LLM)           │
  │     Scores jobs + Decides next action     │
  └───────────────────────────────────────────┘
  ┌───────────────────────────────────────────┐
  │              Storage Layer                 │
  │  SQLite (jobs, strategies, logs, memory)   │
  │  Google Sheets (optional export)           │
  └───────────────────────────────────────────┘
```

## Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| **Backend** | Python FastAPI | Async, auto-docs, fast |
| **Frontend** | Jinja2 + HTMX + Alpine.js | No build step, reactive, lightweight |
| **Database** | SQLite (SQLAlchemy) | Zero-config, single-user |
| **Scraping** | httpx + BeautifulSoup + Playwright | Static + dynamic page support |
| **AI** | Groq API (Llama 3 70B) | Free tier, fast, no GPU needed |
| **Scheduling** | APScheduler | In-process cron-like scheduling |
| **Email** | smtplib (stdlib) | Zero dependencies, any SMTP |

## Implementation Phases

| Phase | What | Status |
|---|---|---|
| 0 | Foundation: scrapers, dashboard, filters, AI scoring, scheduler | ✅ Done |
| **1** | **Agent Core — JobAgent class with THINK→ACT→LEARN loop** | **⬅️ Building** |
| **2** | **Autonomous Search Strategy — dynamic keyword/source selection** | **⬅️ Building** |
| **3** | **Tools: skill gap analysis, web research, email notifier** | **⬅️ Building** |
| 4 | Proactive Outreach — cover letter gen, application pipeline tracking | Future |
| 5 | Learning from Behavior — click tracking, save/dismiss, preference tuning | Future |

---

## Phase 0: Foundation (✅ Done)

### Job Sources (20 total)

| Category | Sources | Scraper |
|---|---|---|
| LinkedIn | 7 keyword searches (SEARCH_KEYWORDS in config.py) | linkedin.py |
| Consider boards | a16z, Sequoia, Battery, Bain, Craft, Forerunner, Gaingels, Headline, LSVP, Sogal, Accel, Conversion Capital, Female Founders, Serena | consider.py (Playwright) |
| Getro boards | General Catalyst, Canvas, BBG Ventures | getro.py |
| Custom boards | Generation She, January Ventures | custom.py |

### Database Schema

#### `jobs`
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| title | TEXT | Job title |
| company | TEXT | Company name |
| location | TEXT | Location |
| remote_status | TEXT | Remote / Hybrid / On-site |
| posted_date | TEXT | Date posted |
| description | TEXT | Full description |
| url | TEXT UNIQUE | Job posting URL |
| source | TEXT | Source identifier |
| ai_score | REAL | 1-10 priority score |
| ai_recommendation | TEXT | AI reasoning |
| created_at | DATETIME | When added |

#### `scrape_logs`
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| started_at | DATETIME | When scrape started |
| finished_at | DATETIME | When scrape ended |
| status | TEXT | running / success / error |
| jobs_found | INTEGER | Total jobs found |
| jobs_new | INTEGER | New (not seen before) |
| details | TEXT | JSON info about sources |

#### `chat_messages`
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| role | TEXT | user / assistant |
| content | TEXT | Message text |
| created_at | DATETIME | Timestamp |

### Filters Applied
- **Title filter**: Drops jobs with VP, Senior, Sr., Lead, Principal, Director, Staff, Head of, etc.
- **AI keyword filter**: Only keeps jobs whose title matches AI/ML keywords (ai engineer, machine learning, data scientist, etc.)
- **Remote filter**: For LinkedIn, drops jobs marked Remote but with a specific city location
- **Hybrid filter**: Drops all Hybrid jobs

---

## Phase 1: Agent Core (Building)

### New Files

| File | Purpose |
|---|---|
| `app/agent/__init__.py` | Package init |
| `app/agent/engine.py` | `JobAgent` — THINK → ACT → LEARN loop |

### New DB Models

#### `search_strategies`
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| keyword | TEXT | Search keyword |
| source_type | TEXT | linkedin / consider / getro / custom |
| source_name | TEXT | linkedin / a16z / accel / etc. |
| active | INTEGER | 1 = active, 0 = paused |
| priority | INTEGER | 1-10, higher = more likely to be chosen |
| total_yield | INTEGER | Total jobs found |
| good_yield | INTEGER | Jobs that passed filter |
| last_run_at | DATETIME | Last time this strategy was executed |
| created_at | DATETIME | When added |

#### `agent_logs`
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| iteration | INTEGER | Cycle number |
| action_type | TEXT | SEARCH / RESEARCH / SEND_EMAIL / REFLECT / WAIT |
| action_detail | TEXT | Full action JSON |
| result_summary | TEXT | Result JSON |
| created_at | DATETIME | Timestamp |

#### `agent_memory`
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| key | TEXT UNIQUE | Memory key |
| value | TEXT | JSON value |
| updated_at | DATETIME | Last updated |

### Agent Loop

```
Every 4 hours, agent runs one cycle:

1. BUILD CONTEXT
   - Active strategies with priorities and yields
   - Recent agent actions
   - DB stats (total jobs, new jobs)
   - Persistent memory

2. DECIDE (LLM call)
   Agent reviews context and picks one action:
   
   SEARCH <keyword> <source>
     → Scrape source with keyword, filter, score with AI, store
   
   RESEARCH <company> <job_id>
     → Web research company info + skill gap analysis
   
   SEND_EMAIL
     → Build HTML digest of top jobs since last email, send via SMTP
   
   REFLECT
     → Analyze yield rates, promote successful strategies, demote weak ones
   
   WAIT
     → Nothing valuable right now

3. EXECUTE
   Run the chosen action

4. LEARN
   Update strategy scores based on results
   Log action to DB
   Update persistent memory
```

---

## Phase 2: Autonomous Search Strategy (Building)

- First agent cycle seeds one `SearchStrategy` per keyword per source (7 keywords × 20 sources)
- After each SEARCH: agent compares `good_yield / total_yield` ratio
  - Ratio > 30% → boost priority
  - Ratio < 5% → demote priority
  - Priority ≤ 1 with zero yield after 10+ runs → deactivate
- Agent can spot companies that appear repeatedly with good scores → generates company-specific strategies
- Agent rotates through strategies by priority, ensuring variety

---

## Phase 3: Tools (Building)

### New Files

| File | Purpose |
|---|---|
| `app/agent/tools/__init__.py` | Tool registry |
| `app/agent/tools/skill_analysis.py` | Resume vs JD gap analysis |
| `app/agent/tools/email_notifier.py` | SMTP-based email sending |
| `app/agent/tools/web_research.py` | Company research via web fetch |

### Skill Analysis Tool
- Takes job title + description + resume text
- Extracts required skills from job description
- Extracts user's skills from resume
- Returns: matched skills, missing skills, gap severity

### Email Notifier Tool
- Uses stdlib `smtplib` — zero extra dependencies
- Configured via `.env`: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, NOTIFY_EMAIL
- Agent autonomously calls `SEND_EMAIL` when it finds high-scored jobs
- Email digest includes top jobs with scores, recommendations, and links

### Web Research Tool
- Uses httpx to fetch company info (LinkedIn, Crunchbase, careers page)
- Returns: company description, size, funding, culture signals

---

## Phase 4: Proactive Outreach (Future)

- New `applications` table (job_id, status, cover_letter, applied_at, notes)
- Agent generates tailored cover letters for 8+/10 jobs using LLM
- Dashboard shows application pipeline: saved → drafting → applied → interview → offer / rejected
- Agent tracks follow-up timing and can suggest next steps

## Phase 5: Learning from Behavior (Future)

- New `interactions` table (job_id, action: view/save/dismiss/apply)
- Dashboard gets save/dismiss buttons on each job row
- Agent reflects weekly: "you dismissed N data scientist roles → deprioritize those keywords"
- Scoring prompt gets dynamically updated with implicit preferences

---

## Google Sheets Columns (optional export)
1. Job Title
2. Company
3. Location
4. Remote Status
5. Posted Date
6. Source
7. Job URL
8. Description
9. AI Priority Score (1-10)
10. AI Recommendation

## Setup Requirements
1. **Groq API key** — free at https://console.groq.com
2. **Google service account** (optional) — for Sheets export
3. **SMTP credentials** (optional) — for email digests (set SMTP_* in .env)
4. **Resume text** — paste in Settings for AI prioritization & skill gap analysis
