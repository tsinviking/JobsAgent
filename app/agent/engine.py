import json
from datetime import datetime, timezone

from sqlalchemy import or_, func

from app.database import get_session, SearchStrategy, AgentLog, AgentMemory, Job, Setting
from app.ai.engine import AIEngine
from app.scrapers import get_scraper
from app.config import SEARCH_KEYWORDS, VC_BOARDS, RESUME_TEXT, AGENT_CYCLE_HOURS
from app.scheduler import filter_job
from app.agent.tools import ToolRegistry


class JobAgent:
    def __init__(self):
        self.llm = AIEngine()
        self.tools = ToolRegistry()
        self._initialized = False

    def initialize_strategies(self):
        session = get_session()
        try:
            if session.query(SearchStrategy).count() > 0:
                return

            print("Agent: seeding initial search strategies...")
            strategies = []
            for keyword in SEARCH_KEYWORDS:
                for source_name, source_config in VC_BOARDS.items():
                    strategies.append(SearchStrategy(
                        keyword=keyword,
                        source_type=source_config["type"],
                        source_name=source_name,
                        priority=5,
                    ))
                strategies.append(SearchStrategy(
                    keyword=keyword,
                    source_type="linkedin",
                    source_name="linkedin",
                    priority=5,
                ))

            session.add_all(strategies)
            session.commit()
            print(f"Agent: seeded {len(strategies)} strategies")
        finally:
            session.close()

    def cycle(self):
        if not self.llm.is_available():
            print("Agent: AI not configured, skipping cycle")
            return

        if not self._initialized:
            self.initialize_strategies()
            self._initialized = True

        print("Agent: starting cycle...")
        session = get_session()

        try:
            context = self._build_context(session)
            action = self._decide_action(context)
            result = self._execute(action, session)
            self._log_action(session, action, result)
            session.commit()
            print(f"Agent: cycle complete — {action.get('type', '?')}")
        except Exception as e:
            print(f"Agent: cycle error — {e}")
            session.rollback()
        finally:
            session.close()

    def _build_context(self, session) -> dict:
        active = session.query(SearchStrategy).filter(
            SearchStrategy.active == True
        ).order_by(SearchStrategy.priority.desc()).limit(15).all()

        recent = session.query(AgentLog).order_by(
            AgentLog.id.desc()
        ).limit(5).all()

        memory_rows = session.query(AgentMemory).all()
        memory = {}
        for m in memory_rows:
            try:
                memory[m.key] = json.loads(m.value)
            except (json.JSONDecodeError, TypeError):
                memory[m.key] = m.value

        total_jobs = session.query(Job).count()
        high_score = session.query(Job).filter(Job.ai_score >= 7).count()

        return {
            "active_strategies": [
                {
                    "keyword": s.keyword,
                    "source": s.source_name,
                    "priority": s.priority,
                    "yield": s.good_yield,
                    "total": s.total_yield,
                }
                for s in active
            ],
            "recent_actions": [
                {
                    "type": l.action_type,
                    "result": l.result_summary[:100] if l.result_summary else "",
                    "at": l.created_at.isoformat() if l.created_at else "",
                }
                for l in recent
            ],
            "total_jobs": total_jobs,
            "high_score_jobs": high_score,
            "memory": memory,
            "cycle_hours": AGENT_CYCLE_HOURS,
        }

    def _decide_action(self, context: dict) -> dict:
        strategies_str = json.dumps(context["active_strategies"], indent=2)
        recent_str = json.dumps(context["recent_actions"], indent=2)
        memory_str = json.dumps(context["memory"], indent=2)
        source_names = list(VC_BOARDS.keys()) + ["linkedin"]
        source_list = ", ".join(source_names[:10])

        prompt = f"""You are an autonomous job search agent. Your objective is to find the best-matched AI Engineer or AI Product Manager roles for the user.

Current state:
- Active search strategies: {strategies_str}
- Total jobs in database: {context['total_jobs']}
- High-scored jobs (>=7/10): {context['high_score_jobs']}
- Recent actions: {recent_str}
- Memory: {memory_str}

Available actions:

1. SEARCH <keyword> <source>
   Scrape a job source with a specific keyword.
   Available sources: {source_list}
   Available keywords: {', '.join(SEARCH_KEYWORDS)}
   Use this when a strategy has untapped potential or hasn't been tried recently.

2. RESEARCH <company_name> <job_id>
   Research a company that has a high-scored job. Fetches company info and skill gaps.
   Use this after finding a promising job to evaluate fit.

3. SEND_EMAIL
   Send email digest to the user with top job matches.
   Use when you've found new high-scored jobs (>=7/10) or haven't emailed in 3+ days.

4. REFLECT
   Analyze recent search yields, promote successful strategies, demote weak ones.
   Use this after several SEARCH actions without reviewing.

5. WAIT
   Do nothing — everything is up to date.

Pick the single most valuable next action.
Respond in this exact format:
ACTION: <SEARCH|RESEARCH|SEND_EMAIL|REFLECT|WAIT>
PARAMS: <JSON object with action parameters>
REASON: <one sentence explaining why>"""

        try:
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            text = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Agent: LLM decision error — {e}")
            return {"type": "REFLECT", "params": {}, "reason": "LLM error, defaulting to reflect"}

        return self._parse_action(text)

    def _parse_action(self, text: str) -> dict:
        action = {"type": "WAIT", "params": {}, "reason": ""}
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("ACTION:"):
                action["type"] = line.replace("ACTION:", "").strip().upper()
            elif line.startswith("PARAMS:"):
                raw = line.replace("PARAMS:", "").strip()
                try:
                    action["params"] = json.loads(raw)
                except json.JSONDecodeError:
                    action["params"] = {}
            elif line.startswith("REASON:"):
                action["reason"] = line.replace("REASON:", "").strip()
        return action

    def _execute(self, action: dict, session) -> dict:
        t = action.get("type", "WAIT")
        p = action.get("params", {})

        if t == "SEARCH":
            return self._exec_search(
                p.get("keyword", SEARCH_KEYWORDS[0]),
                p.get("source", "linkedin"),
                session,
            )
        elif t == "RESEARCH":
            return self._exec_research(
                p.get("company", ""),
                p.get("job_id"),
                session,
            )
        elif t == "SEND_EMAIL":
            return self._exec_email(session)
        elif t == "REFLECT":
            return self._exec_reflect(session)
        else:
            return {"status": "skipped", "detail": "WAIT"}

    def _exec_search(self, keyword: str, source_name: str, session) -> dict:
        print(f"Agent: SEARCH '{keyword}' on '{source_name}'")

        if source_name == "linkedin":
            source_type = "linkedin"
            source_url = ""
        elif source_name in VC_BOARDS:
            source_type = VC_BOARDS[source_name]["type"]
            source_url = VC_BOARDS[source_name]["url"]
        else:
            return {"status": "error", "detail": f"Unknown source: {source_name}"}

        scraper = get_scraper(source_type, source_name, source_url)
        try:
            jobs = scraper.scrape()
        except Exception as e:
            print(f"  Scrape error: {e}")
            return {"status": "error", "detail": str(e)}

        before = len(jobs)
        jobs = [j for j in jobs if filter_job(j)]
        print(f"  Found {before}, filtered to {len(jobs)}")

        jobs_new = 0
        for job in jobs:
            existing = session.query(Job).filter(Job.url == job.url).first()
            if existing:
                continue

            score, recommendation = self.llm.prioritize_job(
                job.title, job.company, job.description
            )

            session.add(Job(
                title=job.title, company=job.company,
                location=job.location, remote_status=job.remote_status,
                posted_date=job.posted_date, description=job.description,
                url=job.url, source=job.source,
                ai_score=score, ai_recommendation=recommendation,
            ))
            jobs_new += 1

        session.commit()

        strat = session.query(SearchStrategy).filter(
            SearchStrategy.keyword == keyword,
            SearchStrategy.source_name == source_name,
        ).first()

        if strat:
            strat.total_yield = (strat.total_yield or 0) + len(jobs)
            strat.good_yield = (strat.good_yield or 0) + jobs_new
            strat.last_run_at = datetime.now(timezone.utc)

            if len(jobs) > 0:
                ratio = jobs_new / len(jobs)
                if ratio > 0.3:
                    strat.priority = min(10, (strat.priority or 5) + 1)
                elif ratio < 0.05:
                    strat.priority = max(1, (strat.priority or 5) - 1)
        else:
            session.add(SearchStrategy(
                keyword=keyword, source_type=source_type,
                source_name=source_name, total_yield=len(jobs),
                good_yield=jobs_new, last_run_at=datetime.now(timezone.utc),
            ))

        session.commit()

        return {"status": "success", "jobs_found": len(jobs), "jobs_new": jobs_new}

    def _exec_research(self, company: str, job_id, session) -> dict:
        print(f"Agent: RESEARCH '{company}'")

        company_info = self.tools.web_research.run(company)

        job = None
        if job_id:
            job = session.query(Job).filter(Job.id == job_id).first()

        skill_gap = None
        if job and RESUME_TEXT:
            skill_gap = self.tools.skill_analysis.run(
                job.title, job.description, RESUME_TEXT
            )

        self._set_memory(
            session,
            f"company:{company.lower().replace(' ', '_')}",
            {
                "info": company_info,
                "skill_gap": skill_gap,
                "researched_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        return {
            "status": "success",
            "company": company,
            "has_skill_gap": skill_gap is not None,
        }

    def _exec_email(self, session) -> dict:
        print("Agent: SEND_EMAIL")

        last = session.query(AgentLog).filter(
            AgentLog.action_type == "SEND_EMAIL"
        ).order_by(AgentLog.id.desc()).first()

        q = session.query(Job).filter(Job.ai_score >= 7).order_by(Job.ai_score.desc())
        if last:
            q = q.filter(Job.created_at > last.created_at)

        top_jobs = q.limit(10).all()

        if not top_jobs:
            return {"status": "skipped", "detail": "No new high-score jobs"}

        ok = self.tools.email.send_digest(top_jobs)
        self._set_memory(session, "last_email_sent", {
            "at": datetime.now(timezone.utc).isoformat(),
            "count": len(top_jobs),
        })

        return {"status": "sent" if ok else "error", "count": len(top_jobs)}

    def _exec_reflect(self, session) -> dict:
        print("Agent: REFLECT")

        strategies = session.query(SearchStrategy).all()
        updated = 0
        deactivated = 0

        for s in strategies:
            if not s.total_yield or s.total_yield == 0:
                continue

            ratio = (s.good_yield or 0) / s.total_yield
            if ratio > 0.3:
                s.priority = min(10, (s.priority or 5) + 1)
                updated += 1
            elif ratio < 0.05:
                s.priority = max(1, (s.priority or 5) - 1)
                updated += 1

            if (s.priority or 5) <= 1 and (s.total_yield or 0) > 20 and (s.good_yield or 0) == 0:
                s.active = False
                deactivated += 1

        session.commit()
        print(f"  Updated {updated} priorities, deactivated {deactivated}")

        return {
            "status": "success",
            "reviewed": len(strategies),
            "adjusted": updated,
            "deactivated": deactivated,
        }

    def _log_action(self, session, action: dict, result: dict):
        last = session.query(AgentLog).order_by(AgentLog.id.desc()).first()
        iteration = (last.iteration + 1) if last else 1

        session.add(AgentLog(
            iteration=iteration,
            action_type=action.get("type", "?"),
            action_detail=json.dumps(action),
            result_summary=json.dumps(result),
        ))

    def _set_memory(self, session, key: str, value):
        existing = session.query(AgentMemory).filter(AgentMemory.key == key).first()
        if existing:
            existing.value = json.dumps(value)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            session.add(AgentMemory(key=key, value=json.dumps(value)))

    def _chat_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_jobs",
                    "description": "Search job titles and companies in the database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "search term to match against title or company"}
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_stats",
                    "description": "Get full job database statistics (totals, sources, scores, agent status)",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_agent_cycle",
                    "description": "Trigger the autonomous agent to find new jobs",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def _run_chat_tool(self, name: str, args: dict) -> str:
        session = get_session()
        try:
            if name == "search_jobs":
                q = args.get("query", "")
                jobs = session.query(Job).filter(
                    or_(Job.title.ilike(f"%{q}%"), Job.company.ilike(f"%{q}%"))
                ).order_by(Job.created_at.desc()).limit(10).all()
                if not jobs:
                    return f"No jobs matching '{q}'."
                lines = [f"Found {len(jobs)} jobs:"]
                for j in jobs:
                    score = f"{j.ai_score}/10" if j.ai_score else "N/A"
                    lines.append(f"- {j.title} @ {j.company} | {j.location} | Score: {score}")
                return "\n".join(lines)

            elif name == "get_stats":
                total = session.query(Job).count()
                high = session.query(Job).filter(Job.ai_score >= 7).count()
                sources = session.query(Job.source, func.count(Job.id)).group_by(Job.source).all()
                src = "\n".join(f"  {s}: {c}" for s, c in sources)
                from app.database import ScrapeLog
                last = session.query(ScrapeLog).order_by(ScrapeLog.id.desc()).first()
                llog = f"Last scrape: {last.status} ({last.jobs_found} found)" if last else "No scrapes yet"
                return f"Total: {total}\nHigh-score (>=7): {high}\nBy source:\n{src}\n{llog}"

            elif name == "run_agent_cycle":
                self.cycle()
                return "Agent cycle completed."

            return f"Unknown tool: {name}"
        except Exception as e:
            return f"Tool {name} error: {e}"
        finally:
            session.close()

    def chat_respond(self, message: str) -> str:
        if not self.llm.is_available():
            return "AI not configured. Set GROQ_API_KEY in Settings."

        session = get_session()
        try:
            resume_row = session.query(Setting).filter(Setting.key == "resume_text").first()
            resume_text = resume_row.value if resume_row and resume_row.value else ""

            total = session.query(Job).count()
            high = session.query(Job).filter(Job.ai_score >= 7).count()
            recent = session.query(Job).order_by(Job.created_at.desc()).limit(5).all()
            recent_list = "\n".join(
                f"- {j.title} @ {j.company} | {j.location} | Score: {j.ai_score or 'N/A'}"
                for j in recent
            )
        finally:
            session.close()

        resume_section = ""
        if resume_text:
            resume_section = f"\nUser's Resume ({len(resume_text)} chars):\n{resume_text[:3000]}\n"

        system = f"""You are Jobs Agent — an autonomous job search assistant.

Current database stats:
- Total jobs: {total}
- High-score jobs (>=7): {high}
- Recent listings:\n{recent_list}
{resume_section}
You have tools available (search_jobs, get_stats, run_agent_cycle).
Use them when you need data. Be concise and direct."""

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ]

        for _ in range(3):
            resp = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=messages,
                tools=self._chat_tools(),
                tool_choice="auto",
                temperature=0.3,
                max_tokens=600,
            )
            msg = resp.choices[0].message

            if not msg.tool_calls:
                return msg.content or ""

            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                result = self._run_chat_tool(name, args)
                messages.append(msg)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        return messages[-1]["content"] if messages else ""

    def get_status(self) -> dict:
        session = get_session()
        try:
            last_log = session.query(AgentLog).order_by(AgentLog.id.desc()).first()
            active_count = session.query(SearchStrategy).filter(
                SearchStrategy.active == True
            ).count()
            top_strats = session.query(SearchStrategy).filter(
                SearchStrategy.active == True
            ).order_by(SearchStrategy.priority.desc()).limit(5).all()

            mem = {}
            for m in session.query(AgentMemory).all():
                try:
                    mem[m.key] = json.loads(m.value)
                except Exception:
                    mem[m.key] = m.value

            return {
                "last_action": {
                    "type": last_log.action_type if last_log else None,
                    "iteration": last_log.iteration if last_log else 0,
                    "at": last_log.created_at.isoformat() if last_log and last_log.created_at else None,
                } if last_log else None,
                "active_strategies": active_count,
                "top_strategies": [
                    {"keyword": s.keyword, "source": s.source_name, "priority": s.priority}
                    for s in top_strats
                ],
                "last_email": mem.get("last_email_sent"),
            }
        finally:
            session.close()
