from __future__ import annotations

import html
import smtplib
from collections import Counter, defaultdict
from datetime import datetime
from email.message import EmailMessage

from config import EmailConfig
from search_jobs import JobResult, SearchReport


SUBJECT = "Daily Sponsor-Friendly QA/SDET Job Links - Ireland"


def send_job_email(config: EmailConfig, jobs: list[JobResult], report: SearchReport, generated_at: datetime, test_mode: bool) -> None:
    message = EmailMessage()
    message["Subject"] = f"[TEST] {SUBJECT}" if test_mode else SUBJECT
    message["From"] = config.email_from
    message["To"] = config.email_to

    plain_text = render_plain_text(jobs, report, generated_at, test_mode)
    html_body = render_html(jobs, report, generated_at, test_mode)
    message.set_content(plain_text)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(message)


def render_plain_text(jobs: list[JobResult], report: SearchReport, generated_at: datetime, test_mode: bool) -> str:
    lines = _summary_lines(jobs, report, generated_at, test_mode)

    if report.failures:
        lines.extend(["", "Search completed with failures, so results may be incomplete.", ""])

    if jobs:
        lines.append("New matching jobs")
        for company, company_jobs in _group_by_company(jobs).items():
            lines.append("")
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
    else:
        lines.extend(["", "No new matching sponsor-friendly QA/SDET jobs found today."])
        if report.failures:
            lines.append("Because some sources failed, this does not prove there are no matching jobs.")

    lines.extend(_failure_lines(report))
    lines.extend(_rejected_lines(report))
    return "\n".join(lines).strip() + "\n"


def render_html(jobs: list[JobResult], report: SearchReport, generated_at: datetime, test_mode: bool) -> str:
    summary = _summary_html(jobs, report, generated_at, test_mode)
    warning = ""
    if report.failures:
        warning = "<p><strong>Search completed with failures, so results may be incomplete.</strong></p>"

    if jobs:
        job_sections = []
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
            job_sections.append(f"<h2>{html.escape(company)}</h2><ul>{''.join(items)}</ul>")
        jobs_html = "".join(job_sections)
    else:
        extra = " Because some sources failed, this does not prove there are no matching jobs." if report.failures else ""
        jobs_html = f"<p>No new matching sponsor-friendly QA/SDET jobs found today.{html.escape(extra)}</p>"

    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5; color: #222;">
        <h1>{'[TEST] ' if test_mode else ''}Daily Sponsor-Friendly QA/SDET Job Links - Ireland</h1>
        {summary}
        {warning}
        {jobs_html}
        {_failures_html(report)}
        {_rejected_html(report)}
      </body>
    </html>
    """


def _summary_lines(jobs: list[JobResult], report: SearchReport, generated_at: datetime, test_mode: bool) -> list[str]:
    return [
        f"{'[TEST] ' if test_mode else ''}Daily Sponsor-Friendly QA/SDET Job Links - Ireland",
        "",
        f"New matching jobs found: {len(jobs)}",
        f"Companies searched successfully: {report.successful_company_count}",
        f"Companies failed: {report.failed_company_count}",
        f"Companies with no jobs: {report.no_job_company_count}",
        f"Raw jobs/pages found: {len(report.raw_jobs)}",
        f"Rejected jobs/pages: {len(report.rejected_jobs)}",
        f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M %Z')} Europe/Dublin",
    ]


def _summary_html(jobs: list[JobResult], report: SearchReport, generated_at: datetime, test_mode: bool) -> str:
    rows = [
        ("New matching jobs found", len(jobs)),
        ("Companies searched successfully", report.successful_company_count),
        ("Companies failed", report.failed_company_count),
        ("Companies with no jobs", report.no_job_company_count),
        ("Raw jobs/pages found", len(report.raw_jobs)),
        ("Rejected jobs/pages", len(report.rejected_jobs)),
        ("Generated", f"{generated_at.strftime('%Y-%m-%d %H:%M %Z')} Europe/Dublin"),
    ]
    return "<ul>" + "".join(f"<li><strong>{html.escape(str(label))}:</strong> {html.escape(str(value))}</li>" for label, value in rows) + "</ul>"


def _failure_lines(report: SearchReport) -> list[str]:
    if not report.failures:
        return []
    lines = ["", "Failed sources"]
    for failure in report.failures[:25]:
        lines.append(f"- {failure.company} | {failure.source} | {failure.error} | {failure.endpoint}")
    if len(report.failures) > 25:
        lines.append(f"...and {len(report.failures) - 25} more failures. See data/search_failures.json artifact.")
    return lines


def _failures_html(report: SearchReport) -> str:
    if not report.failures:
        return ""
    items = [
        f"<li>{html.escape(failure.company)} | {html.escape(failure.source)} | {html.escape(failure.error)}<br><small>{html.escape(failure.endpoint)}</small></li>"
        for failure in report.failures[:25]
    ]
    if len(report.failures) > 25:
        items.append(f"<li>...and {len(report.failures) - 25} more failures. See the search_failures artifact.</li>")
    return f"<h2>Failed sources</h2><ul>{''.join(items)}</ul>"


def _rejected_lines(report: SearchReport) -> list[str]:
    if not report.rejected_jobs:
        return []
    reason_counts = Counter(job.reason for job in report.rejected_jobs)
    lines = ["", "Top rejected job/page titles found"]
    lines.append("Rejected reason counts: " + ", ".join(f"{reason}={count}" for reason, count in reason_counts.most_common()))
    for rejected in report.rejected_jobs[:20]:
        lines.append(f"- {rejected.title or '(untitled)'} | {rejected.company} | {rejected.source} | {rejected.reason}")
    if len(report.rejected_jobs) > 20:
        lines.append(f"...and {len(report.rejected_jobs) - 20} more rejected items. See data/raw_results.json and data/filtered_results.json artifacts.")
    return lines


def _rejected_html(report: SearchReport) -> str:
    if not report.rejected_jobs:
        return ""
    reason_counts = Counter(job.reason for job in report.rejected_jobs)
    counts = ", ".join(f"{html.escape(reason)}={count}" for reason, count in reason_counts.most_common())
    items = [
        f"<li>{html.escape(rejected.title or '(untitled)')} | {html.escape(rejected.company)} | {html.escape(rejected.source)} | {html.escape(rejected.reason)}</li>"
        for rejected in report.rejected_jobs[:20]
    ]
    if len(report.rejected_jobs) > 20:
        items.append(f"<li>...and {len(report.rejected_jobs) - 20} more rejected items. See the artifacts.</li>")
    return f"<h2>Top rejected job/page titles found</h2><p>{counts}</p><ul>{''.join(items)}</ul>"


def _group_by_company(jobs: list[JobResult]) -> dict[str, list[JobResult]]:
    grouped: dict[str, list[JobResult]] = defaultdict(list)
    for job in sorted(jobs, key=lambda item: (item.company, item.title)):
        grouped[job.company].append(job)
    return dict(grouped)
