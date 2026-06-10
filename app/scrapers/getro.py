import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import httpx

from app.scrapers.base import BaseScraper, JobData


class GetroScraper(BaseScraper):
    def scrape(self) -> list[JobData]:
        jobs = []

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                "Accept": "application/json, text/html",
            }
            resp = httpx.get(self.url, headers=headers, timeout=15, follow_redirects=True)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            jsonld_jobs = self._parse_jsonld_items(soup, self.name)
            jobs.extend(jsonld_jobs)

            job_cards = soup.select(
                "a[href*='job'], div[class*='job'], div[class*='Job'], "
                "a[class*='job'], div[class*='card'], [class*='job-card']"
            )
            if not job_cards:
                job_cards = soup.find_all(["a", "div"], class_=re.compile(r"job", re.I))

            seen_urls = set(j.url for j in jobs)
            for card in job_cards:
                try:
                    link = card if card.name == "a" else card.find("a", href=True)
                    if not link:
                        continue
                    href = link.get("href", "")
                    if not href or "job" not in href.lower():
                        continue
                    if href.startswith("/"):
                        href = urljoin(self.url, href)

                    if href in seen_urls:
                        continue
                    seen_urls.add(href)

                    title_el = card.select_one("h2, h3, h4, [class*='title'], [class*='Title']")
                    company_el = card.select_one("[class*='company'], [class*='Company'], [class*='name']")
                    location_el = card.select_one("[class*='location'], [class*='Location']")
                    desc_el = card.select_one("[class*='desc'], [class*='Desc'], p")

                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    location = location_el.get_text(strip=True) if location_el else ""
                    description = desc_el.get_text(strip=True) if desc_el else ""

                    if not title:
                        continue

                    remote_status = "Remote" if self.is_remote(title + " " + location + " " + description) else "Unknown"

                    jobs.append(JobData(
                        title=title,
                        company=company,
                        location=location,
                        remote_status=remote_status,
                        posted_date="",
                        description=description,
                        url=href,
                        source=self.name,
                    ))
                except Exception:
                    continue

        except Exception as e:
            print(f"  Getro[{self.name}] error: {e}")

        for job in jobs:
            job.source = self.name

        return jobs
