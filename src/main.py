from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from companies import COMPANIES, ROLE_KEYWORDS
from config import (
    DUBLIN_TIMEZONE,
    FILTERED_RESULTS_PATH,
    RAW_RESULTS_PATH,
    SEARCH_FAILURES_PATH,
    SEEN_JOBS_PATH,
    force_run_enabled,
    get_email_config,
    test_mode_enabled,
)
from emailer import send_job_email
from search_jobs import TEST_MODE_COMPANIES, find_jobs
from storage import load_seen_jobs, save_json, save_seen_jobs


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)


def main() -> None:
    generated_at = datetime.now(ZoneInfo(DUBLIN_TIMEZONE))
    test_mode = test_mode_enabled()

    if not _should_run_now(generated_at):
        LOGGER.info("Skipping run because local Europe/Dublin time is %s.", generated_at.strftime("%H:%M"))
        return

    target_companies = [company for company in COMPANIES if company in TEST_MODE_COMPANIES] if test_mode else COMPANIES
    LOGGER.info("Starting job search at %s. test_mode=%s companies=%s", generated_at.isoformat(), test_mode, len(target_companies))

    seen_urls = load_seen_jobs(SEEN_JOBS_PATH)
    report = find_jobs(target_companies, ROLE_KEYWORDS, generated_at)
    all_jobs = report.jobs
    new_jobs = [job for job in all_jobs if job.url not in seen_urls]

    raw_results, filtered_results, search_failures = report.to_artifacts()
    save_json(RAW_RESULTS_PATH, raw_results)
    save_json(FILTERED_RESULTS_PATH, filtered_results)
    save_json(SEARCH_FAILURES_PATH, search_failures)

    LOGGER.info(
        "Found %s matching jobs, %s new. successful_companies=%s failed_companies=%s no_job_companies=%s",
        len(all_jobs),
        len(new_jobs),
        report.successful_company_count,
        report.failed_company_count,
        report.no_job_company_count,
    )

    email_config = get_email_config()
    send_job_email(email_config, new_jobs, report, generated_at, test_mode)
    LOGGER.info("Email sent to %s.", email_config.email_to)

    if test_mode:
        LOGGER.info("Test mode is enabled; not updating seen_jobs.json.")
        return

    updated_seen_urls = seen_urls | {job.url for job in new_jobs}
    save_seen_jobs(SEEN_JOBS_PATH, updated_seen_urls)
    LOGGER.info("Saved %s seen job URLs.", len(updated_seen_urls))


def _should_run_now(now_dublin: datetime) -> bool:
    if force_run_enabled():
        return True
    return now_dublin.hour == 5


if __name__ == "__main__":
    main()
