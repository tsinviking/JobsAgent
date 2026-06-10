import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, NOTIFY_EMAIL

DIGEST_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;background:#f8fafc;padding:24px;">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;">
<div style="background:#1e293b;color:white;padding:20px 24px;">
    <h2 style="margin:0;">Jobs Agent</h2>
    <p style="margin:4px 0 0;opacity:0.8;">New high-match roles found</p>
</div>
<div style="padding:24px;">
    <table style="width:100%;border-collapse:collapse;">
        {rows}
    </table>
</div>
<div style="background:#f1f5f9;padding:12px 24px;text-align:center;font-size:12px;color:#94a3b8;">
    <a href="{dashboard_url}" style="color:#2563eb;">View full dashboard</a>
</div>
</div>
</body>
</html>"""

ROW_TEMPLATE = """<tr style="border-bottom:1px solid #e2e8f0;">
    <td style="padding:12px 8px;font-weight:600;">{i}.</td>
    <td style="padding:12px 8px;">
        <strong>{title}</strong><br>
        <span style="color:#64748b;">@{company}</span>
    </td>
    <td style="padding:12px 8px;">
        <span style="display:inline-block;background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:4px;font-weight:600;">{score}/10</span>
    </td>
</tr>
<tr style="border-bottom:2px solid #e2e8f0;">
    <td colspan="3" style="padding:0 8px 12px 32px;color:#64748b;font-size:14px;">
        {rec}<br>
        <a href="{url}" style="color:#2563eb;">View job</a>
    </td>
</tr>"""


class EmailNotifier:
    def is_configured(self) -> bool:
        return bool(SMTP_HOST and SMTP_USER and SMTP_PASS and NOTIFY_EMAIL)

    def send_digest(self, jobs: list) -> bool:
        if not self.is_configured():
            print("  Email not configured, skipping")
            return False

        html_rows = ""
        for idx, job in enumerate(jobs[:10], 1):
            score = job.ai_score or "?"
            rec = job.ai_recommendation or ""
            html_rows += ROW_TEMPLATE.format(
                i=idx,
                title=job.title,
                company=job.company,
                score=score,
                rec=rec,
                url=job.url,
            )

        html = DIGEST_TEMPLATE.format(rows=html_rows, dashboard_url="http://localhost:8000")
        subject = f"Jobs Agent — {len(jobs)} new high-match role{'s' if len(jobs) > 1 else ''}"

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = SMTP_USER
            msg["To"] = NOTIFY_EMAIL
            msg.attach(MIMEText(html, "html"))

            context = ssl.create_default_context()
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls(context=context)
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_USER, NOTIFY_EMAIL, msg.as_string())

            print(f"  Email sent: {subject}")
            return True

        except Exception as e:
            print(f"  Email error: {e}")
            return False
