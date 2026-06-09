from __future__ import annotations

import html
import smtplib
from collections import defaultdict
from datetime import datetime
from email.message import EmailMessage

from config import EmailConfig
from search_jobs import JobResult


SUBJECT = "Daily Sponsor-Friendly QA/SDET Job Links - Ireland"


def send_job_email(config: EmailConfig, jobs: list[JobResult], generated_at: datetime) -> None:
    message = EmailMessage()
    message["Subject"] = SUBJECT
    message["From"] = config.email_from
    message["To"] = config.email_to

    plain_text = render_plain_text(jobs, generated_at)
    html_body = render_html(jobs, generated_at)
    message.set_content(plain_text)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(message)


def render_plain_text(jobs: list[JobResult], generated_at: datetime) -> str:
    if not jobs:
        return "No new matching sponsor-friendly QA/SDET jobs found today."

    lines = [
        "Daily Sponsor-Friendly QA/SDET Job Links - Ireland",
        "",
        f"Total new jobs found: {len(jobs)}",
        f"Companies with matches: {len({job.company for job in jobs})}",
        f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M %Z')} Europe/Dublin",
        "",
    ]

    for company, company_jobs in _group_by_company(jobs).items():
        lines.append(company)
        for job in company_jobs:
            lines.extend(
                [
                    f"- {job.title}",
                    f"  Location: {job.location}",
                    f"  Matching keyword: {job.matching_keyword}",
                    f"  Source: {job.source}",
                    f"  Link: {job.url}",
                ]
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_html(jobs: list[JobResult], generated_at: datetime) -> str:
    if not jobs:
        return """
        <html>
          <body>
            <p>No new matching sponsor-friendly QA/SDET jobs found today.</p>
          </body>
        </html>
        """

    company_count = len({job.company for job in jobs})
    sections = []
    for company, company_jobs in _group_by_company(jobs).items():
        items = []
        for job in company_jobs:
            items.append(
                f"""
                <li>
                  <a href="{html.escape(job.url)}">{html.escape(job.title)}</a><br>
                  <strong>Location:</strong> {html.escape(job.location)}<br>
                  <strong>Matching keyword:</strong> {html.escape(job.matching_keyword)}<br>
                  <strong>Source:</strong> {html.escape(job.source)}
                </li>
                """
            )

        sections.append(
            f"""
            <h2>{html.escape(company)}</h2>
            <ul>
              {''.join(items)}
            </ul>
            """
        )

    generated = generated_at.strftime("%Y-%m-%d %H:%M %Z")
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5; color: #222;">
        <h1>Daily Sponsor-Friendly QA/SDET Job Links - Ireland</h1>
        <p>
          <strong>Total new jobs found:</strong> {len(jobs)}<br>
          <strong>Companies with matches:</strong> {company_count}<br>
          <strong>Generated:</strong> {html.escape(generated)} Europe/Dublin
        </p>
        {''.join(sections)}
      </body>
    </html>
    """


def _group_by_company(jobs: list[JobResult]) -> dict[str, list[JobResult]]:
    grouped: dict[str, list[JobResult]] = defaultdict(list)
    for job in sorted(jobs, key=lambda item: (item.company, item.title)):
        grouped[job.company].append(job)
    return dict(grouped)
