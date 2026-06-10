import random
import time
import re
from urllib.parse import quote
from bs4 import BeautifulSoup
import httpx

from app.config import SEARCH_KEYWORDS
from app.scrapers.base import BaseScraper, JobData

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:132.0) Gecko/20100101 Firefox/132.0",
]

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


class LinkedInScraper(BaseScraper):
    def __init__(self, name="linkedin", url=""):
        super().__init__(name, url)
        self.keywords = SEARCH_KEYWORDS
        self._client = httpx.Client(timeout=15, follow_redirects=True)

    def _get_headers(self):
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    def _search_jobs(self, keyword: str, start: int = 0) -> list[dict]:
        params = {"keywords": keyword, "f_WT": "2", "start": start}
        try:
            resp = self._client.get(SEARCH_URL, params=params, headers=self._get_headers())
            resp.raise_for_status()
        except Exception as e:
            print(f"  LinkedIn search error for '{keyword}' at start={start}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for card in soup.find_all("li"):
            try:
                link_tag = card.select_one("a.base-card__full-link")
                if not link_tag:
                    continue
                href = link_tag.get("href", "")

                match = re.search(r"[-/](\d{6,})(?:\?|/|$)", href)
                if not match:
                    continue
                job_id = match.group(1)

                title_tag = card.select_one("h3.base-search-card__title")
                company_tag = card.select_one("h4.base-search-card__subtitle")
                location_tag = card.select_one(".job-search-card__location")
                date_tag = card.select_one("time.job-search-card__listdate")

                title = title_tag.get_text(strip=True) if title_tag else ""
                company = company_tag.get_text(strip=True) if company_tag else ""
                location = location_tag.get_text(strip=True) if location_tag else ""
                posted_date = date_tag.get("datetime", "") if date_tag else ""
                if not posted_date and date_tag:
                    posted_date = date_tag.get_text(strip=True)

                if not title:
                    continue

                results.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "posted_date": posted_date,
                    "keyword": keyword,
                })
            except Exception:
                continue

        return results

    def _fetch_details(self, job_id: str) -> dict:
        url = DETAIL_URL.format(job_id=job_id)
        try:
            resp = self._client.get(url, headers=self._get_headers())
            resp.raise_for_status()
        except Exception as e:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")

        desc_tag = soup.select_one(
            ".description__text, .show-more-less-html__markup, "
            "div[class*='description'], article"
        )
        description = desc_tag.decode_contents() if desc_tag else ""
        description = self.clean_html(description)

        criteria = {}
        for li in soup.select(".job-criteria__item"):
            label = li.select_one(".job-criteria__subtitle")
            value = li.select_one(".job-criteria__text")
            if label and value:
                criteria[label.get_text(strip=True).lower()] = value.get_text(strip=True)

        return {"description": description, "criteria": criteria}

    def scrape(self) -> list[JobData]:
        all_jobs = []
        seen_ids = set()

        for keyword in self.keywords:
            print(f"  LinkedIn: searching '{keyword}'...")
            for start in range(0, 50, 25):
                results = self._search_jobs(keyword, start)
                if not results:
                    break
                for r in results:
                    if r["job_id"] not in seen_ids:
                        seen_ids.add(r["job_id"])
                        all_jobs.append(r)
                time.sleep(random.uniform(2.0, 3.5))
            time.sleep(random.uniform(1.0, 2.0))

        final_jobs = []
        for i, job in enumerate(all_jobs):
            print(f"  LinkedIn: fetching details {i+1}/{len(all_jobs)}...")
            details = self._fetch_details(job["job_id"])
            description = details.get("description", "")
            criteria = details.get("criteria", {})

            remote_status = "Remote"
            location_text = job.get("location", "")
            if "hybrid" in location_text.lower():
                remote_status = "Hybrid"
            elif "on-site" in location_text.lower() or "onsite" in location_text.lower():
                remote_status = "On-site"

            final_jobs.append(JobData(
                title=job["title"],
                company=job["company"],
                location=location_text,
                remote_status=remote_status,
                posted_date=job.get("posted_date", ""),
                description=description,
                url=f"https://www.linkedin.com/jobs/view/{job['job_id']}/",
                source=self.name,
            ))

            time.sleep(random.uniform(1.0, 2.0))

        return final_jobs
