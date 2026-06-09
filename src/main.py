from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from companies import COMPANIES, TEST_MODE_COMPANIES
from config import (
    DUBLIN_TIMEZONE,
    FILTERED_RESULTS_PATH,
    RAW_RESULTS_PATH,
    REJECTED_RESULTS_PATH,
    SEARCH_FAILURES_PATH,
    SEEN_JOBS_PATH,
    force_run_enabled,
    get_email_config,
    max_companies,
    send_email_enabled,
    test_mode_enabled,
    update_seen_enabled,
)
from emailer import send_job_email
from search_jobs import find_jobs
from storage import load_seen_jobs, save_json, save_seen_jobs


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)


def main() -> None:
    generated_at = datetime.now(ZoneInfo(DUBLIN_TIMEZONE))
    test_mode = test_mode_enabled()
    should_send_email = send_email_enabled()
    should_update_seen = update_seen_enabled()

    if not _should_run_now(generated_at):
        LOGGER.info("Skipping run because local Europe/Dublin time is %s.", generated_at.strftime("%H:%M"))
        return

    target_companies = list(TEST_MODE_COMPANIES if test_mode else COMPANIES)
    limit = max_companies()
    if limit:
        target_companies = target_companies[:limit]

    LOGGER.info(
        "Starting job search generated_at=%s test_mode=%s send_email=%s update_seen=%s companies=%s",
        generated_at.isoformat(),
        test_mode,
        should_send_email,
        should_update_seen,
        len(target_companies),
    )

    seen_ids = load_seen_jobs(SEEN_JOBS_PATH)
    report = find_jobs(target_companies, generated_at)
    all_jobs = report.jobs
    new_jobs = [job for job in all_jobs if job.unique_id not in seen_ids]
    duplicate_jobs = [job for job in all_jobs if job.unique_id in seen_ids]

    raw_results, filtered_results, rejected_results, search_failures = report.artifacts()
    save_json(RAW_RESULTS_PATH, raw_results)
    save_json(FILTERED_RESULTS_PATH, filtered_results)
    save_json(REJECTED_RESULTS_PATH, rejected_results)
    save_json(SEARCH_FAILURES_PATH, search_failures)

    LOGGER.info(
        "Search totals successful_companies=%s failed_companies=%s raw=%s accepted=%s rejected=%s new=%s duplicates=%s",
        report.successful_company_count,
        report.failed_company_count,
        len(report.raw_jobs),
        len(all_jobs),
        len(report.rejected_jobs),
        len(new_jobs),
        len(duplicate_jobs),
    )

    email_sent = False
    if should_send_email:
        email_config = get_email_config()
        send_job_email(email_config, new_jobs, report, generated_at, test_mode)
        email_sent = True
        LOGGER.info("Email sent to %s.", email_config.email_to)
    else:
        LOGGER.info("Email skipped because SEND_EMAIL=false.")

    if should_update_seen and email_sent:
        updated_seen_ids = seen_ids | {job.unique_id for job in new_jobs}
        save_seen_jobs(SEEN_JOBS_PATH, updated_seen_ids)
        LOGGER.info("Saved %s seen job IDs.", len(updated_seen_ids))
    else:
        LOGGER.info("Seen jobs not updated. update_seen=%s email_sent=%s", should_update_seen, email_sent)


def _should_run_now(now_dublin: datetime) -> bool:
    if force_run_enabled():
        return True
    return now_dublin.hour == 5


if __name__ == "__main__":
    main()
