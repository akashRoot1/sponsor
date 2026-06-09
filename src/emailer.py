from __future__ import annotations

import html
import smtplib
from collections import Counter, defaultdict
from datetime import datetime
from email.message import EmailMessage

from config import EmailConfig
from models import JobResult, SearchReport


SUBJECT = "Daily Sponsor-Friendly QA/SDET Job Links - Ireland"
CATEGORY_ORDER = [
    "QA / SDET / Test Automation roles",
    "Production/Application Support roles relevant to QA profile",
    "Performance / API Testing roles",
    "Validation / CSV roles",
    "Other relevant Quality/Test roles",
]


def send_job_email(config: EmailConfig, jobs: list[JobResult], report: SearchReport, generated_at: datetime, test_mode: bool) -> None:
    message = EmailMessage()
    message["Subject"] = f"[TEST] {SUBJECT}" if test_mode else SUBJECT
    message["From"] = config.email_from
    message["To"] = config.email_to
    message.set_content(render_plain_text(jobs, report, generated_at, test_mode))
    message.add_alternative(render_html(jobs, report, generated_at, test_mode), subtype="html")

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(message)


def render_plain_text(jobs: list[JobResult], report: SearchReport, generated_at: datetime, test_mode: bool) -> str:
    lines = _summary_lines(jobs, report, generated_at, test_mode)
    if report.failures:
        lines.extend(["", "Search completed with failures, so results may be incomplete."])

    if jobs:
        for category, category_jobs in _group_by_category(jobs).items():
            lines.extend(["", category])
            for job in category_jobs:
                lines.extend(
                    [
                        f"- {job.title}",
                        f"  Company: {job.company}",
                        f"  Location: {job.location}",
                        f"  Work type: {job.work_type or 'Not listed'}",
                        f"  Matching keyword: {job.matching_keyword}",
                        f"  Source: {job.source}",
                        f"  Date found: {job.date_found}",
                        f"  Link: {job.url}",
                    ]
                )
    else:
        lines.extend(["", "No new matching sponsor-friendly QA/SDET jobs were emailed today."])
        lines.append(f"Raw jobs checked: {len(report.raw_jobs)}")
        lines.append(f"Rejected jobs/pages: {len(report.rejected_jobs)}")
        lines.append(f"Failed companies: {report.failed_company_count}")
        if report.failures:
            lines.append("Because some sources failed, this does not prove there are no matching jobs.")

    lines.extend(_failure_lines(report))
    lines.extend(_rejected_lines(report))
    return "\n".join(lines).strip() + "\n"


def render_html(jobs: list[JobResult], report: SearchReport, generated_at: datetime, test_mode: bool) -> str:
    warning = "<p><strong>Search completed with failures, so results may be incomplete.</strong></p>" if report.failures else ""
    if jobs:
        body = []
        for category, category_jobs in _group_by_category(jobs).items():
            items = []
            for job in category_jobs:
                items.append(
                    f"""
                    <li>
                      <a href="{html.escape(job.url)}">{html.escape(job.title)}</a><br>
                      <strong>Company:</strong> {html.escape(job.company)}<br>
                      <strong>Location:</strong> {html.escape(job.location)}<br>
                      <strong>Work type:</strong> {html.escape(job.work_type or 'Not listed')}<br>
                      <strong>Matching keyword:</strong> {html.escape(job.matching_keyword)}<br>
                      <strong>Source:</strong> {html.escape(job.source)}<br>
                      <strong>Date found:</strong> {html.escape(job.date_found)}
                    </li>
                    """
                )
            body.append(f"<h2>{html.escape(category)}</h2><ul>{''.join(items)}</ul>")
        jobs_html = "".join(body)
    else:
        extra = " Because some sources failed, this does not prove there are no matching jobs." if report.failures else ""
        jobs_html = f"<p>No new matching sponsor-friendly QA/SDET jobs were emailed today.{html.escape(extra)}</p>"

    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5; color: #222;">
        <h1>{'[TEST] ' if test_mode else ''}Daily Sponsor-Friendly QA/SDET Job Links - Ireland</h1>
        {_summary_html(jobs, report, generated_at)}
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
        f"Total new matching jobs: {len(jobs)}",
        f"Companies searched successfully: {report.successful_company_count}",
        f"Companies failed: {report.failed_company_count}",
        f"Raw jobs found: {len(report.raw_jobs)}",
        f"Accepted jobs: {len(report.jobs)}",
        f"Rejected jobs: {len(report.rejected_jobs)}",
        f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M %Z')} Europe/Dublin",
    ]


def _summary_html(jobs: list[JobResult], report: SearchReport, generated_at: datetime) -> str:
    rows = [
        ("Total new matching jobs", len(jobs)),
        ("Companies searched successfully", report.successful_company_count),
        ("Companies failed", report.failed_company_count),
        ("Raw jobs found", len(report.raw_jobs)),
        ("Accepted jobs", len(report.jobs)),
        ("Rejected jobs", len(report.rejected_jobs)),
        ("Generated", f"{generated_at.strftime('%Y-%m-%d %H:%M %Z')} Europe/Dublin"),
    ]
    return "<ul>" + "".join(f"<li><strong>{html.escape(str(label))}:</strong> {html.escape(str(value))}</li>" for label, value in rows) + "</ul>"


def _failure_lines(report: SearchReport) -> list[str]:
    if not report.failures:
        return []
    lines = ["", "Failed sources"]
    for failure in report.failures[:25]:
        status = f" status={failure.http_status}" if failure.http_status else ""
        lines.append(f"- {failure.company} | {failure.source_type}{status} | {failure.error} | {failure.endpoint}")
    if len(report.failures) > 25:
        lines.append(f"...and {len(report.failures) - 25} more failures. See data/search_failures.json.")
    return lines


def _failures_html(report: SearchReport) -> str:
    if not report.failures:
        return ""
    items = []
    for failure in report.failures[:25]:
        status = f" status={failure.http_status}" if failure.http_status else ""
        items.append(f"<li>{html.escape(failure.company)} | {html.escape(failure.source_type)}{html.escape(status)} | {html.escape(failure.error)}<br><small>{html.escape(failure.endpoint)}</small></li>")
    if len(report.failures) > 25:
        items.append(f"<li>...and {len(report.failures) - 25} more failures. See artifacts.</li>")
    return f"<h2>Failed sources</h2><ul>{''.join(items)}</ul>"


def _rejected_lines(report: SearchReport) -> list[str]:
    if not report.rejected_jobs:
        return []
    reason_counts = Counter(job.reason for job in report.rejected_jobs)
    lines = ["", "Main rejection reasons"]
    lines.append(", ".join(f"{reason}={count}" for reason, count in reason_counts.most_common()))
    lines.append("")
    lines.append("Top 10 rejected relevant-looking titles")
    for rejected in report.rejected_jobs[:10]:
        lines.append(f"- {rejected.title or '(untitled)'} | {rejected.company} | {rejected.location} | {rejected.reason}")
    return lines


def _rejected_html(report: SearchReport) -> str:
    if not report.rejected_jobs:
        return ""
    reason_counts = Counter(job.reason for job in report.rejected_jobs)
    counts = ", ".join(f"{html.escape(reason)}={count}" for reason, count in reason_counts.most_common())
    items = [
        f"<li>{html.escape(rejected.title or '(untitled)')} | {html.escape(rejected.company)} | {html.escape(rejected.location)} | {html.escape(rejected.reason)}</li>"
        for rejected in report.rejected_jobs[:10]
    ]
    return f"<h2>Main rejection reasons</h2><p>{counts}</p><h2>Top 10 rejected relevant-looking titles</h2><ul>{''.join(items)}</ul>"


def _group_by_category(jobs: list[JobResult]) -> dict[str, list[JobResult]]:
    grouped: dict[str, list[JobResult]] = defaultdict(list)
    for job in sorted(jobs, key=lambda item: (CATEGORY_ORDER.index(item.category) if item.category in CATEGORY_ORDER else 99, item.company, item.title)):
        grouped[job.category].append(job)
    return {category: grouped[category] for category in CATEGORY_ORDER if grouped.get(category)}
