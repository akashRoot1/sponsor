from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
SEEN_JOBS_PATH = DATA_DIR / "seen_jobs.json"
RAW_RESULTS_PATH = DATA_DIR / "raw_results.json"
FILTERED_RESULTS_PATH = DATA_DIR / "filtered_results.json"
SEARCH_FAILURES_PATH = DATA_DIR / "search_failures.json"
REJECTED_RESULTS_PATH = DATA_DIR / "rejected_results.json"
ACCEPTED_RESULTS_PATH = DATA_DIR / "accepted_results.json"
DUPLICATES_REMOVED_PATH = DATA_DIR / "duplicates_removed.json"
SOURCE_HEALTH_PATH = DATA_DIR / "source_health.json"
DUBLIN_TIMEZONE = "Europe/Dublin"
DEFAULT_EMAIL_TO = "akashvikram98@gmail.com"


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    email_to: str


def get_email_config() -> EmailConfig:
    missing = [
        name
        for name in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"]
        if not os.getenv(name)
    ]
    if missing:
        raise RuntimeError(f"Missing required email environment variables: {', '.join(missing)}")

    return EmailConfig(
        smtp_host=os.environ["SMTP_HOST"],
        smtp_port=int(os.environ["SMTP_PORT"]),
        smtp_user=os.environ["SMTP_USER"],
        smtp_password=os.environ["SMTP_PASSWORD"],
        email_from=os.environ["EMAIL_FROM"],
        email_to=os.getenv("EMAIL_TO") or DEFAULT_EMAIL_TO,
    )


def force_run_enabled() -> bool:
    return os.getenv("FORCE_RUN", "").strip().lower() in {"1", "true", "yes", "y"}


def test_mode_enabled() -> bool:
    return os.getenv("TEST_MODE", "").strip().lower() in {"1", "true", "yes", "y"}


def send_email_enabled() -> bool:
    return os.getenv("SEND_EMAIL", "true").strip().lower() in {"1", "true", "yes", "y"}


def update_seen_enabled() -> bool:
    return os.getenv("UPDATE_SEEN", "true").strip().lower() in {"1", "true", "yes", "y"}


def max_companies() -> int | None:
    raw_value = os.getenv("MAX_COMPANIES", "").strip()
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("MAX_COMPANIES must be a number if provided.") from exc
    return value if value > 0 else None
