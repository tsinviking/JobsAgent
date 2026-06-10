import json
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import httpx

from app.scrapers.base import BaseScraper, JobData

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"


class CustomScraper(BaseScraper):
    def scrape(self) -> list[JobData]:
        jobs = []

        try:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            resp = httpx.get(self.url, headers=headers, timeout=15, follow_redirects=True)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            jsonld_jobs = self._parse_jsonld_items(soup, self.name)
            jobs.extend(jsonld_jobs)

            selectors = [
                "a[href*='job']", "a[href*='career']", "a[href*='position']",
                "div[class*='job']", "div[class*='Job']", "div[class*='card']",
                "tr[class*='job']", "li[class*='job']",
            ]
            for selector in selectors:
                elements = soup.select(selector)
                if elements:
                    break
            else:
                elements = []

            seen_urls = set(j.url for j in jobs)
            for el in elements:
                try:
                    link = el if el.name == "a" else el.find("a", href=True)
                    if not link:
                        continue
                    href = link.get("href", "")
                    if not href or any(skip in href for skip in ["#", "javascript:", "mailto:"]):
                        continue
                    if href.startswith("/"):
                        href = urljoin(self.url, href)

                    if href in seen_urls:
                        continue
                    seen_urls.add(href)

                    title_el = el.select_one("h2, h3, h4, [class*='title'], [class*='Title'], strong")
                    company_el = el.select_one("[class*='company'], [class*='Company']")
                    location_el = el.select_one("[class*='location'], [class*='Location']")
                    desc_el = el.select_one("p, [class*='desc'], [class*='Desc']")

                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    location = location_el.get_text(strip=True) if location_el else ""
                    description = desc_el.get_text(strip=True) if desc_el else ""

                    if not title:
                        title = el.get_text(strip=True).split("\n")[0][:200]

                    title_text = title + " " + el.get_text(" ", strip=True)
                    remote_status = "Remote" if self.is_remote(title_text) else "Unknown"

                    jobs.append(JobData(
                        title=title,
                        company=company if company else self.name.replace("_", " ").title(),
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
            print(f"  Custom[{self.name}] error: {e}")

        for job in jobs:
            job.source = self.name

        return jobs
