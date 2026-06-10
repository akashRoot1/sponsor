from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from provider_detection import detect_provider


def test_detects_workday_from_public_board_link() -> None:
    html = '<a href="https://zendesk.wd1.myworkdayjobs.com/en-US/zendesk">Open roles</a>'
    detection = detect_provider("https://jobs.zendesk.com", html)
    assert detection.detected_provider == "workday"
    assert detection.recommended_mapping["host"] == "zendesk.wd1.myworkdayjobs.com"
    assert detection.recommended_mapping["site"] == "zendesk"


def test_does_not_treat_random_domain_allowlist_as_workday_source() -> None:
    html = '["booking.com","myworkdayjobs.com","example.com"]'
    detection = detect_provider("https://www.metacareers.com/jobsearch/", html)
    assert detection.detected_provider == "unknown"


def test_detects_new_provider_families() -> None:
    examples = {
        "icims": "https://example.icims.com/jobs/search",
        "teamtailor": "https://example.teamtailor.com/jobs",
        "bamboohr": "https://example.bamboohr.com/careers/list",
        "jobvite": "https://jobs.jobvite.com/example",
        "taleo": "https://example.taleo.net/careersection/ex/jobsearch.ftl",
        "personio": "https://example.jobs.personio.com",
        "recruitee": "https://example.recruitee.com/api/offers/",
        "pinpoint": "https://example.pinpointhq.com/jobs",
    }
    for provider, url in examples.items():
        assert detect_provider(url).detected_provider == provider
