import httpx
from bs4 import BeautifulSoup


class WebResearchTool:
    def run(self, company_name: str) -> dict:
        info = {
            "company": company_name,
            "description": "",
            "source": "web",
        }

        try:
            query = company_name.replace(" ", "+")
            url = f"https://www.google.com/search?q={query}+company+crunchbase"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            }
            resp = httpx.get(url, headers=headers, timeout=10, follow_redirects=False)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                snippets = soup.select("span.aCOpRe, div[data-sncf], .VwiC3b")
                if snippets:
                    info["description"] = snippets[0].get_text(strip=True)[:500]

        except Exception as e:
            print(f"  Web research error: {e}")

        return info
