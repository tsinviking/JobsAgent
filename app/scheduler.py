import re
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler

from app.database import get_session, Job, ScrapeLog
from app.scrapers import get_scraper
from app.config import SEARCH_KEYWORDS, VC_BOARDS, SCRAPE_INTERVAL_HOURS, AGENT_CYCLE_HOURS
from app.ai.engine import AIEngine
from app.sheets.export import GoogleSheetsExporter

AI_TITLE_KEYWORDS = re.compile(
    r'\b('
    r'ai\s*(engineer|intern|product|builder|developer|platform|architect|scientist|research|ml|developer)'
    r'|machine\s*learning|deep\s*learning|artificial\s*intelligence'
    r'|nlp|llm|gpt|neural\s*network|computer\s*vision|openai|langchain|rag'
    r'|vector\s*database|generative\s*ai|genai|mlops|ai/ml'
    r'|data\s*(scientist|engineer|analyst|architect)'
    r'|ml\s*engineer|prompt\s*engineer'
    r'|applied\s*(scientist|ai|ml|research)'
    r'|research\s*scientist|robotics)',
    re.IGNORECASE,
)

SENIOR_TITLE_PATTERNS = re.compile(
    r'\b(VP\b|Vice\s*President|Senior|Sr\.|Lead|Principal|Director|Staff|Head\s+of|Managing\s+Director|CXO|CEO|CTO|COO|CFO)',
    re.IGNORECASE,
)

EXPLICIT_REMOTE_PATTERNS = re.compile(
    r'^(remote|anywhere|worldwide|various|multiple\s+locations|united\s+states|us\s+remote|remote\s*[-–]\s*\w+)$',
    re.IGNORECASE,
)

scheduler = BackgroundScheduler()
ai_engine = AIEngine()
sheets_exporter = GoogleSheetsExporter()


def has_ai_title(title: str) -> bool:
    return bool(AI_TITLE_KEYWORDS.search(title))


def is_senior_title(title: str) -> bool:
    return bool(SENIOR_TITLE_PATTERNS.search(title))


def is_remote_location(location: str) -> bool:
    return bool(EXPLICIT_REMOTE_PATTERNS.match(location.strip()))


def filter_job(job) -> bool:
    if not job or not job.title:
        return False
    if is_senior_title(job.title):
        return False
    if not has_ai_title(job.title):
        return False
    if job.remote_status == "Hybrid":
        return False
    if job.remote_status == "Remote" and not is_remote_location(job.location):
        if job.source == "linkedin":
            return False
    return True


def run_full_scrape():
    session = get_session()
    log = ScrapeLog(
        started_at=datetime.now(timezone.utc),
        status="running",
        jobs_found=0,
        jobs_new=0,
    )
    session.add(log)
    session.commit()

    all_jobs = []
    source_counts = {}

    try:
        linkedin_scraper = get_scraper("linkedin", "linkedin", "")
        print("Scraping LinkedIn...")
        linkedin_jobs = linkedin_scraper.scrape()
        all_jobs.extend(linkedin_jobs)
        source_counts["linkedin"] = len(linkedin_jobs)
        print(f"  Found {len(linkedin_jobs)} LinkedIn jobs")

        for slug, config in VC_BOARDS.items():
            print(f"Scraping {slug} ({config['type']})...")
            scraper = get_scraper(config["type"], slug, config["url"])
            try:
                jobs = scraper.scrape()
                all_jobs.extend(jobs)
                source_counts[slug] = len(jobs)
                print(f"  Found {len(jobs)} jobs from {slug}")
            except Exception as e:
                print(f"  Error scraping {slug}: {e}")
                source_counts[slug] = 0

        before_filter = len(all_jobs)
        all_jobs = [job for job in all_jobs if filter_job(job)]
        filtered_out = before_filter - len(all_jobs)
        if filtered_out:
            print(f"  Filtered out {filtered_out} jobs (senior titles / hybrid / not truly remote)")

        existing_urls = set(
            row[0] for row in session.query(Job.url).all()
        )

        new_jobs_batch = []
        for job in all_jobs:
            if job.url in existing_urls:
                continue

            score, recommendation = ai_engine.prioritize_job(
                job.title, job.company, job.description
            )

            new_jobs_batch.append(Job(
                title=job.title,
                company=job.company,
                location=job.location,
                remote_status=job.remote_status,
                posted_date=job.posted_date,
                description=job.description,
                url=job.url,
                source=job.source,
                ai_score=score,
                ai_recommendation=recommendation,
            ))

        jobs_new = len(new_jobs_batch)
        if new_jobs_batch:
            session.add_all(new_jobs_batch)
            session.commit()

            sheets_exporter.export_jobs([
                {
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "remote_status": j.remote_status,
                    "posted_date": j.posted_date,
                    "source": j.source,
                    "url": j.url,
                    "description": j.description,
                    "ai_score": j.ai_score,
                    "ai_recommendation": j.ai_recommendation,
                }
                for j in new_jobs_batch
            ])

        log.status = "success"
        log.jobs_found = len(all_jobs)
        log.jobs_new = jobs_new
        log.details = source_counts
        log.finished_at = datetime.now(timezone.utc)
        session.commit()

        print(f"Scrape complete: {jobs_new} new out of {len(all_jobs)} total")

    except Exception as e:
        log.status = "error"
        log.details = {"error": str(e), **source_counts}
        log.finished_at = datetime.now(timezone.utc)
        session.commit()
        print(f"Scrape failed: {e}")
    finally:
        session.close()


def start_scheduler():
    scheduler.add_job(
        run_full_scrape,
        "interval",
        hours=SCRAPE_INTERVAL_HOURS,
        id="job_scrape",
        replace_existing=True,
    )
    scheduler.start()
    print(f"Scheduler started: every {SCRAPE_INTERVAL_HOURS} hours")


agent_scheduler = BackgroundScheduler()


def start_agent_scheduler():
    from app.agent.engine import JobAgent
    agent = JobAgent()

    def agent_cycle_wrapper():
        agent.cycle()

    agent_scheduler.add_job(
        agent_cycle_wrapper,
        "interval",
        hours=AGENT_CYCLE_HOURS,
        id="agent_cycle",
        replace_existing=True,
    )
    agent_scheduler.start()
    print(f"Agent scheduler started: every {AGENT_CYCLE_HOURS} hours")
