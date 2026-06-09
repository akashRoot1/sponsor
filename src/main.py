from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from companies import COMPANIES, ROLE_KEYWORDS
from config import DUBLIN_TIMEZONE, SEEN_JOBS_PATH, force_run_enabled, get_email_config
from emailer import send_job_email
from search_jobs import find_jobs
from storage import load_seen_jobs, save_seen_jobs


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)


def main() -> None:
    generated_at = datetime.now(ZoneInfo(DUBLIN_TIMEZONE))

    if not _should_run_now(generated_at):
        LOGGER.info("Skipping run because local Europe/Dublin time is %s.", generated_at.strftime("%H:%M"))
        return

    LOGGER.info("Starting job search at %s.", generated_at.isoformat())
    seen_urls = load_seen_jobs(SEEN_JOBS_PATH)
    all_jobs = find_jobs(COMPANIES, ROLE_KEYWORDS, generated_at)
    new_jobs = [job for job in all_jobs if job.url not in seen_urls]

    LOGGER.info("Found %s matching jobs, %s new.", len(all_jobs), len(new_jobs))

    email_config = get_email_config()
    send_job_email(email_config, new_jobs, generated_at)
    LOGGER.info("Email sent to %s.", email_config.email_to)

    save_seen_jobs(SEEN_JOBS_PATH, seen_urls | {job.url for job in all_jobs})
    LOGGER.info("Saved %s seen job URLs.", len(seen_urls | {job.url for job in all_jobs}))


def _should_run_now(now_dublin: datetime) -> bool:
    if force_run_enabled():
        return True
    return now_dublin.hour == 5


if __name__ == "__main__":
    main()
