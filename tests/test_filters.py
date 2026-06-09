from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from filters import evaluate_job
from models import JobResult, RawJob
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


def assert_accepts(title: str, location: str, company: str = "Test Company", description: str = "") -> None:
    decision = evaluate_job(raw_job(title, location, company, description))
    assert decision.accepted, f"{title} rejected: {decision.reason}, score={decision.score}"
    assert decision.score >= 12


def assert_rejects(title: str, location: str, company: str = "Test Company", description: str = "") -> None:
    decision = evaluate_job(raw_job(title, location, company, description))
    assert not decision.accepted, f"{title} unexpectedly accepted with score={decision.score}, reason={decision.reason}"


def test_accepts_broad_qa_test_quality_and_support_matches() -> None:
    examples = [
        ("QA Analyst", "Dublin"),
        ("Quality Analyst", "Dublin"),
        ("Test Analyst", "Dublin"),
        ("Manual Test Analyst", "Ireland"),
        ("QA Engineer", "Dublin"),
        ("Quality Engineer", "Ireland"),
        ("Quality Engineer", "Sligo, SO", "AbbVie"),
        ("Quality Assurance Engineer", "Dublin"),
        ("Software Test Engineer", "Cork"),
        ("Test Automation Engineer", "Dublin"),
        ("QA Automation Engineer", "Dublin"),
        ("SDET", "Ireland"),
        ("UAT Tester", "Dublin"),
        ("Test Support Engineer", "Dublin", "Cubic Telecom"),
        ("Application Support Engineer", "Dublin", "Cubic Telecom"),
        ("Production Support Engineer", "Ireland"),
        ("Technical Support Engineer", "Dublin"),
        ("Performance Test Engineer", "Ireland"),
        ("API Test Engineer", "Dublin"),
        ("Validation Engineer", "Galway"),
        ("Validation Engineer", "Sligo, SO", "AbbVie"),
        ("CSV Tester", "Cork"),
    ]
    for title, location, *company in examples:
        assert_accepts(title, location, company[0] if company else "Test Company")


def test_rejects_false_positives_even_with_single_tool_or_testing_mentions() -> None:
    examples = [
        ("Senior Full Stack Engineer", "Dublin", "Build product UI. Cypress experience is a plus."),
        ("Backend Engineer", "Dublin", "Build APIs and mention testing once."),
        ("Technical Account Manager", "Dublin", "Use Postman with customers occasionally."),
        ("Customer Success Associate", "Dublin", ""),
        ("Engagement Manager", "Dublin", ""),
        ("Product Manager", "Dublin", ""),
        ("Project Manager", "Dublin", ""),
        ("Security Engineer", "Dublin", ""),
        ("Network Cabling Quality Technician", "Dublin", ""),
        ("Data Center Construction Quality Manager", "Dublin", ""),
        ("Food Quality Inspector", "Dublin", ""),
        ("Supplier Quality Engineer", "Dublin", "Hardware supplier audits and manufacturing quality only."),
        ("Sales Manager", "Dublin", ""),
        ("Marketing Executive", "Ireland", ""),
        ("Finance Analyst", "Dublin", ""),
        ("HR Business Partner", "Dublin", ""),
    ]
    for title, location, description in examples:
        assert_rejects(title, location, description=description)


def test_rejects_application_support_outside_ireland() -> None:
    decision = evaluate_job(raw_job("Application Support Engineer", "Manila", "Cubic Telecom"))
    assert not decision.accepted
    assert decision.reason == "location_mismatch"


def test_accepts_application_support_dublin_remote() -> None:
    assert_accepts("Application Support Engineer", "Dublin / Remote", "Cubic Telecom")


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
            category="Production/Application Support Roles",
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
            category="Production/Application Support Roles",
            score=15,
        ),
    ]
    unique, duplicates = _dedupe_jobs(jobs)
    assert len(unique) == 1
    assert len(duplicates) == 1
