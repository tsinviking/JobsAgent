from app.scrapers.linkedin import LinkedInScraper
from app.scrapers.consider import ConsiderScraper
from app.scrapers.getro import GetroScraper
from app.scrapers.custom import CustomScraper


def get_scraper(source_type, source_name, source_url):
    scrapers = {
        "linkedin": LinkedInScraper,
        "consider": ConsiderScraper,
        "getro": GetroScraper,
        "custom": CustomScraper,
    }
    cls = scrapers.get(source_type)
    if not cls:
        raise ValueError(f"Unknown scraper type: {source_type}")
    return cls(source_name, source_url)
