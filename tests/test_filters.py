from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from filters import evaluate_job
from models import CompanyConfig, JobResult, RawJob
from search_jobs import _dedupe_jobs


def raw_job(title: str, location: str, company: str = "Test Company", description: str = "", url: str = "https://jobs.example.com/job/1") -> RawJob:
    return RawJob(
        company=company,
        title=title,
        location=location,
        url=url,
        source="test",
        endpoint="test",
        snippet=description,
        source_type="test",
        source_quality="direct_api",
    )


def assert_accepts(title: str, company: str, location: str, description: str = "") -> None:
    decision = evaluate_job(raw_job(title, location, company, description))
    assert decision.accepted, f"{title} rejected: {decision.reason}, score={decision.score}"
    assert decision.score >= 10


def assert_rejects(title: str, company: str, location: str, description: str = "") -> None:
    decision = evaluate_job(raw_job(title, location, company, description))
    assert not decision.accepted, f"{title} unexpectedly accepted with score={decision.score}"


def test_accepts_required_good_matches() -> None:
    examples = [
        ("Senior Test Automation Engineer", "Cubic Telecom", "Dublin"),
        ("Test Automation Engineer", "Cubic Telecom", "Dublin"),
        ("Test Support Engineer (Maternity Cover)", "Cubic Telecom", "Dublin"),
        ("Sr. Quality Assurance Engineer", "Amazon", "Dublin"),
        ("Technical Support Engineer", "Intercom", "Dublin"),
        ("AI Support Engineer", "OpenAI", "Dublin"),
        ("Senior Support Engineer", "OpenAI", "Dublin"),
        ("Onsite Support Engineer", "Version 1", "Dublin"),
        ("Incident Management Engineer", "Amazon", "Dublin"),
        ("Validation Engineer", "Test Company", "Galway"),
        ("CSV Tester", "Test Company", "Cork"),
        ("API Test Engineer", "Test Company", "Dublin"),
        ("Performance Test Engineer", "Test Company", "Ireland"),
    ]
    for title, company, location in examples:
        assert_accepts(title, company, location)


def test_rejects_required_false_positives() -> None:
    examples = [
        ("Engagement Manager", "Stripe", "Dublin"),
        ("Manager, Global Sanctions", "Stripe", "Ireland"),
        ("Senior GTM Product Enablement Manager", "Intercom", "Dublin"),
        ("Senior Security Engineering Manager", "Intercom", "Dublin"),
        ("EMEA Cabling Quality Manager", "Amazon", "Dublin"),
        ("Network Cabling Quality Technician", "Amazon", "Dublin"),
        ("Network Infrastructure Construction Quality Program Manager", "Amazon", "Dublin"),
        ("Senior Supplier Quality Engineer", "Amazon", "Dublin"),
        ("Customer Success Associate", "Datadog", "Dublin"),
        ("Technical Account Manager", "Stripe", "Dublin"),
        ("Sales Manager", "Test Company", "Dublin"),
        ("Marketing Executive", "Test Company", "Ireland"),
        ("Product Manager", "Test Company", "Dublin"),
        ("Backend Engineer", "Test Company", "Dublin", "no testing, no QA, no support"),
    ]
    for item in examples:
        assert_rejects(*item)


def test_rejects_application_support_outside_ireland() -> None:
    decision = evaluate_job(raw_job("Application Support Engineer", "Manila", "Cubic Telecom"))
    assert not decision.accepted
    assert decision.reason == "location_mismatch"


def test_accepts_application_support_dublin_remote() -> None:
    assert_accepts("Application Support Engineer", "Cubic Telecom", "Dublin / Remote")


def test_deduplicates_incident_title_hyphen_variants() -> None:
    jobs = [
        JobResult(
            title="Incident Management Engineer II - bilingual (Mandarin & English)",
            company="Amazon",
            location="Dublin",
            url="https://amazon.jobs/job/1",
            matching_keyword="incident management engineer",
            source="Amazon Jobs",
            date_found="2026-06-09",
            category="Production/Application Support roles",
            score=15,
        ),
        JobResult(
            title="Incident Management Engineer II- bilingual (Mandarin & English)",
            company="Amazon",
            location="Dublin",
            url="https://amazon.jobs/job/2",
            matching_keyword="incident management engineer",
            source="Amazon Jobs",
            date_found="2026-06-09",
            category="Production/Application Support roles",
            score=15,
        ),
    ]
    unique, duplicates = _dedupe_jobs(jobs)
    assert len(unique) == 1
    assert len(duplicates) == 1
