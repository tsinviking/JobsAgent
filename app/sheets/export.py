from app.config import GOOGLE_SHEETS_CREDENTIALS_FILE, GOOGLE_SHEET_URL


class GoogleSheetsExporter:
    def __init__(self):
        self.client = None
        self.sheet = None

    def is_configured(self) -> bool:
        if not GOOGLE_SHEETS_CREDENTIALS_FILE or not GOOGLE_SHEET_URL:
            return False
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            creds = Credentials.from_service_account_file(
                GOOGLE_SHEETS_CREDENTIALS_FILE,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ],
            )
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_url(GOOGLE_SHEET_URL).sheet1
            return True
        except Exception as e:
            print(f"  Google Sheets auth error: {e}")
            return False

    def export_jobs(self, jobs: list[dict]) -> int:
        if not self.is_configured():
            return 0

        try:
            if not self.sheet.get_all_values():
                headers = [
                    "Job Title", "Company", "Location", "Remote Status",
                    "Posted Date", "Source", "Job URL", "Description",
                    "AI Score", "AI Recommendation",
                ]
                self.sheet.append_row(headers)

            rows = []
            for job in jobs:
                rows.append([
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job.get("remote_status", ""),
                    job.get("posted_date", ""),
                    job.get("source", ""),
                    job.get("url", ""),
                    job.get("description", "")[:500] if job.get("description") else "",
                    job.get("ai_score", ""),
                    job.get("ai_recommendation", ""),
                ])

            if rows:
                self.sheet.append_rows(rows)

            return len(rows)

        except Exception as e:
            print(f"  Google Sheets export error: {e}")
            return 0
