from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from companies import COMPANIES, TEST_MODE_COMPANIES
from config import (
    DUBLIN_TIMEZONE,
    ACCEPTED_RESULTS_PATH,
    DUPLICATES_REMOVED_PATH,
    FILTERED_RESULTS_PATH,
    KNOWN_MISSED_JOBS_FIXTURE_PATH,
    KNOWN_MISSED_JOBS_CHECK_PATH,
    MISSING_SOURCE_MAPPINGS_PATH,
    PROVIDER_AUDIT_PATH,
    PROVIDER_DETECTION_RESULTS_PATH,
    RAW_RESULTS_PATH,
    REJECTED_RESULTS_PATH,
    SEARCH_FAILURES_PATH,
    SEEN_JOBS_PATH,
    SOURCE_COVERAGE_PATH,
    SOURCE_HEALTH_PATH,
    company_filter,
    force_run_enabled,
    get_email_config,
    keyword_filter,
    max_companies,
    provider_filter,
    send_email_enabled,
    test_mode_enabled,
    update_seen_enabled,
)
from emailer import send_job_email
from reporting import known_missed_jobs_check, missing_source_mappings, provider_detection_results, save_provider_audit, source_coverage
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
    target_companies = _apply_manual_filters(target_companies)
    limit = max_companies()
    if limit:
        target_companies = target_companies[:limit]

    LOGGER.info(
        "Starting job search generated_at=%s test_mode=%s send_email=%s update_seen=%s companies=%s company_filter=%s provider_filter=%s keyword=%s",
        generated_at.isoformat(),
        test_mode,
        should_send_email,
        should_update_seen,
        len(target_companies),
        company_filter(),
        provider_filter(),
        keyword_filter(),
    )

    seen_ids = load_seen_jobs(SEEN_JOBS_PATH)
    report = find_jobs(target_companies, generated_at)
    all_jobs = report.jobs
    new_jobs = [job for job in all_jobs if job.unique_id not in seen_ids]
    duplicate_jobs = [job for job in all_jobs if job.unique_id in seen_ids]

    raw_results, filtered_results, rejected_results, search_failures, accepted_results, duplicates_removed, source_health = report.artifacts()
    save_json(RAW_RESULTS_PATH, raw_results)
    save_json(FILTERED_RESULTS_PATH, filtered_results)
    save_json(REJECTED_RESULTS_PATH, rejected_results)
    save_json(SEARCH_FAILURES_PATH, search_failures)
    save_json(ACCEPTED_RESULTS_PATH, accepted_results)
    save_json(DUPLICATES_REMOVED_PATH, duplicates_removed)
    save_json(SOURCE_HEALTH_PATH, source_health)
    detections = provider_detection_results(COMPANIES)
    missing_mappings = missing_source_mappings(COMPANIES)
    coverage = source_coverage(COMPANIES, report, generated_at)
    save_json(PROVIDER_DETECTION_RESULTS_PATH, detections)
    save_json(MISSING_SOURCE_MAPPINGS_PATH, missing_mappings)
    save_json(SOURCE_COVERAGE_PATH, coverage)
    save_json(KNOWN_MISSED_JOBS_CHECK_PATH, known_missed_jobs_check(KNOWN_MISSED_JOBS_FIXTURE_PATH, generated_at))
    save_provider_audit(PROVIDER_AUDIT_PATH, coverage, missing_mappings)

    LOGGER.info(
        "Search totals successful_companies=%s failed_companies=%s raw=%s accepted=%s rejected=%s new=%s duplicates=%s",
        report.successful_company_count,
        report.failed_company_count,
        len(report.raw_jobs),
        len(all_jobs),
        len(report.rejected_jobs),
        len(new_jobs),
        len(duplicate_jobs) + len(report.duplicates_removed),
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


def _apply_manual_filters(companies):
    selected = list(companies)
    company_name = company_filter().lower()
    provider = provider_filter().lower()
    if company_name:
        selected = [
            company
            for company in selected
            if company_name in company.brand_name.lower()
            or company_name in company.legal_name.lower()
            or any(company_name in alias.lower() for alias in company.aliases)
        ]
    if provider:
        selected = [
            company
            for company in selected
            if any(provider == source.source_type.lower() for source in company.sources)
        ]
    return selected


if __name__ == "__main__":
    main()
