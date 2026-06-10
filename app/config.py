import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "data" / "jobs.db"
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")

SCRAPE_INTERVAL_HOURS = int(os.getenv("SCRAPE_INTERVAL_HOURS", "24"))

SEARCH_KEYWORDS = [
    "AI Engineer",
    "AI Engineer Intern",
    "AI Builder",
    "AI Product Manager",
    "AI Intern", 
    "AI Fellowship", 
    "AI Fellow"
]

GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "")
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL", "")

RESUME_TEXT = os.getenv("RESUME_TEXT", "")

AGENT_CYCLE_HOURS = int(os.getenv("AGENT_CYCLE_HOURS", "4"))

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")

VC_BOARDS = {
    "a16z": {"url": "https://portfoliojobs.a16z.com/jobs", "type": "consider"},
    "accel": {"url": "https://jobs.accel.com/jobs", "type": "consider"},
    "bain_capital": {"url": "https://jobs.baincapitalventures.com/jobs", "type": "consider"},
    "battery": {"url": "https://jobs.battery.com/jobs", "type": "consider"},
    "bbg_ventures": {"url": "https://jobs.bbgventures.com/jobs", "type": "getro"},
    "canvas": {"url": "https://jobs.canvas.vc/", "type": "getro"},
    "conversion_capital": {"url": "https://jobs.conversioncapital.com/jobs", "type": "consider"},
    "craft_ventures": {"url": "https://jobs.craftventures.com/jobs", "type": "consider"},
    "female_founders": {"url": "https://jobs.femalefoundersfund.com/jobs", "type": "consider"},
    "forerunner": {"url": "https://jobs.forerunnerventures.com/jobs", "type": "consider"},
    "gaingels": {"url": "https://jobs.gaingels.com/jobs", "type": "consider"},
    "generation_she": {"url": "https://jobs.generationshe.co/", "type": "custom"},
    "general_catalyst": {"url": "https://jobs.generalcatalyst.com/companies", "type": "getro"},
    "headline": {"url": "https://talent.headline.com/jobs", "type": "consider"},
    "january_ventures": {"url": "https://www.january.ventures/", "type": "custom"},
    "lsvp": {"url": "https://jobs.lsvp.com/jobs", "type": "consider"},
    "serena": {"url": "https://svcareers.serenaventures.com/jobs", "type": "consider"},
    "sequoia": {"url": "https://jobs.sequoiacap.com/jobs/", "type": "consider"},
    "sogal": {"url": "https://jobs.sogalventures.com/jobs", "type": "consider"},
}
