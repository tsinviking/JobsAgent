import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app.scrapers.base import BaseScraper, JobData


class ConsiderScraper(BaseScraper):
    def scrape(self) -> list[JobData]:
        jobs = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                    )
                    page = context.new_page()

                    try:
                        page.goto(self.url, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(3)

                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(2)

                        content = page.content()
                        soup = BeautifulSoup(content, "html.parser")

                        job_cards = soup.select(
                            "a[class*='job'], div[class*='job'], "
                            "div[class*='JobCard'], div[class*='job-card'], "
                            "div[class*='result'], li[class*='job']"
                        )

                        if not job_cards:
                            links = page.evaluate("""
                                () => {
                                    const cards = document.querySelectorAll('a[href*="/jobs/"]');
                                    return Array.from(cards).slice(0, 50).map(a => ({
                                        href: a.href,
                                        text: a.innerText.substring(0, 100),
                                    }));
                                }
                            """)
                            for link in links:
                                href = link.get("href", "")
                                if href and "/jobs/" in href:
                                    try:
                                        page.goto(href, wait_until="domcontentloaded", timeout=15000)
                                        time.sleep(2)
                                        detail_content = page.content()
                                        detail_soup = BeautifulSoup(detail_content, "html.parser")
                                        job = self._extract_from_detail(detail_soup, href)
                                        if job:
                                            jobs.append(job)
                                        time.sleep(1)
                                    except Exception:
                                        continue

                        for card in job_cards:
                            try:
                                job = self._extract_from_card(card)
                                if job:
                                    jobs.append(job)
                            except Exception:
                                continue

                    except Exception as e:
                        print(f"  Consider[{self.name}] page error: {e}")
                    finally:
                        context.close()
                finally:
                    browser.close()
        except Exception as e:
            print(f"  Consider[{self.name}] error: {e}")

        for job in jobs:
            job.source = self.name

        return jobs

    def _extract_from_card(self, card) -> JobData | None:
        link = card if card.name == "a" else card.find("a", href=True)
        if not link:
            return None
        href = link.get("href", "")
        if not href or "job" not in href.lower():
            return None
        if not href.startswith("http"):
            href = urljoin(self.url, href)

        title_el = card.select_one("[class*='title'], [class*='Title'], h2, h3, h4")
        company_el = card.select_one("[class*='company'], [class*='Company'], [class*='organization']")
        location_el = card.select_one("[class*='location'], [class*='Location']")

        title = title_el.get_text(strip=True) if title_el else ""
        company = company_el.get_text(strip=True) if company_el else ""
        location = location_el.get_text(strip=True) if location_el else ""

        remote_status = "Remote" if self.is_remote(title + " " + location) else "Unknown"
        description_full = card.get_text(" ", strip=True)

        if not title:
            return None

        return JobData(
            title=title,
            company=company,
            location=location,
            remote_status=remote_status,
            posted_date="",
            description=description_full,
            url=href,
            source=self.name,
        )

    def _extract_from_detail(self, soup, url: str) -> JobData | None:
        title_el = soup.select_one("h1, [class*='title'], [class*='Title']")
        company_el = soup.select_one("[class*='company'], [class*='Company']")
        desc_el = soup.select_one("[class*='description'], [class*='Description'], [class*='content'], article")
        location_el = soup.select_one("[class*='location'], [class*='Location']")

        title = title_el.get_text(strip=True) if title_el else ""
        company = company_el.get_text(strip=True) if company_el else ""
        description = desc_el.get_text(" ", strip=True) if desc_el else ""
        location = location_el.get_text(strip=True) if location_el else ""

        if not title:
            return None

        remote_status = "Remote" if self.is_remote(title + " " + location + " " + description[:200]) else "Unknown"

        return JobData(
            title=title,
            company=company,
            location=location,
            remote_status=remote_status,
            posted_date="",
            description=description,
            url=url,
            source=self.name,
        )
