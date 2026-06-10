from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional
import re


@dataclass
class JobData:
    title: str
    company: str
    location: str
    remote_status: str
    posted_date: str
    description: str
    url: str
    source: str

    def to_dict(self):
        return asdict(self)


def parse_jsonld_job(item: dict) -> dict | None:
    """Extract job fields from a JSON-LD JobPosting object."""
    title = item.get("title", "") or ""
    if not title:
        return None

    company = ""
    hiring_org = item.get("hiringOrganization", {})
    if isinstance(hiring_org, dict):
        company = hiring_org.get("name", "") or ""

    location = ""
    location_obj = item.get("jobLocation", {})
    if isinstance(location_obj, dict):
        loc = location_obj.get("address", {})
        if isinstance(loc, dict):
            location = loc.get("addressLocality", "") or ""
    elif isinstance(location_obj, str):
        location = location_obj

    description_raw = item.get("description", "") or ""
    description = re.sub(r"<[^>]+>", " ", description_raw)
    description = re.sub(r"\s+", " ", description).strip()

    url = item.get("url", "") or ""
    date_posted = item.get("datePosted", "") or ""

    return {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "url": url,
        "date_posted": date_posted,
    }


class BaseScraper(ABC):
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url

    @abstractmethod
    def scrape(self) -> list[JobData]:
        ...

    def is_ai_related(self, text: str) -> bool:
        if not text:
            return False
        text_lower = text.lower()
        ai_keywords = [
            "ai engineer", "machine learning", "deep learning", "artificial intelligence",
            "nlp", "llm", "gpt", "neural network", "computer vision",
            "ai product", "ai builder", "data scientist", "ml engineer",
            "ai intern", "ai developer", "prompt engineer", "ai platform",
            "ai architect", "openai", "langchain", "rag", "vector database",
            "generative ai", "genai", "mlops", "ai/ml",
        ]
        return any(kw in text_lower for kw in ai_keywords)

    def is_remote(self, text: str) -> bool:
        if not text:
            return False
        text_lower = text.lower()
        remote_indicators = [
            "remote", "work from home", "wfh", "fully remote",
            "100% remote", "anywhere", "virtual",
        ]
        return any(kw in text_lower for kw in remote_indicators)

    def clean_html(self, html_text: str) -> str:
        clean = re.sub(r"<[^>]+>", " ", html_text)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    def _parse_jsonld_items(self, soup, source_name: str) -> list[JobData]:
        """Parse JSON-LD script tags into JobData objects."""
        import json
        jobs = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "JobPosting" or item.get("title"):
                        parsed = parse_jsonld_job(item)
                        if parsed:
                            jobs.append(JobData(
                                title=parsed["title"],
                                company=parsed["company"],
                                location=parsed["location"],
                                remote_status="Remote" if self.is_remote(parsed["title"] + " " + parsed["location"] + " " + parsed["description"][:200]) else "Unknown",
                                posted_date=parsed["date_posted"],
                                description=parsed["description"],
                                url=parsed["url"],
                                source=source_name,
                            ))
            except Exception:
                continue
        return jobs
