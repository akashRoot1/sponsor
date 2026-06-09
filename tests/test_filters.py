from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from filters import evaluate_job
from models import RawJob


def raw_job(title: str, location: str, company: str = "Test Company", description: str = "") -> RawJob:
    return RawJob(
        company=company,
        title=title,
        location=location,
        url="https://jobs.example.com/job/1",
        source="test",
        endpoint="test",
        snippet=description,
    )


def test_accepts_cubic_test_support_engineer_maternity_cover() -> None:
    decision = evaluate_job(raw_job("Test Support Engineer (Maternity Cover)", "Dublin", "Cubic Telecom"))
    assert decision.accepted


def test_rejects_cubic_application_support_engineer_manila() -> None:
    decision = evaluate_job(raw_job("Application Support Engineer", "Manila", "Cubic Telecom"))
    assert not decision.accepted
    assert decision.reason == "location_mismatch"


def test_accepts_cubic_application_support_engineer_dublin_remote() -> None:
    decision = evaluate_job(raw_job("Application Support Engineer", "Dublin / Remote", "Cubic Telecom"))
    assert decision.accepted


def test_accepts_qa_automation_engineer_dublin() -> None:
    decision = evaluate_job(raw_job("QA Automation Engineer", "Dublin"))
    assert decision.accepted


def test_accepts_sdet_ireland() -> None:
    decision = evaluate_job(raw_job("Software Development Engineer in Test", "Ireland"))
    assert decision.accepted


def test_accepts_performance_test_engineer_cork() -> None:
    decision = evaluate_job(raw_job("Performance Test Engineer", "Cork"))
    assert decision.accepted


def test_accepts_validation_engineer_galway() -> None:
    decision = evaluate_job(raw_job("Validation Engineer", "Galway"))
    assert decision.accepted


def test_rejects_sales_manager_dublin() -> None:
    decision = evaluate_job(raw_job("Sales Manager", "Dublin"))
    assert not decision.accepted
    assert decision.reason.startswith("excluded_unrelated_role")


def test_rejects_marketing_executive_ireland() -> None:
    decision = evaluate_job(raw_job("Marketing Executive", "Ireland"))
    assert not decision.accepted
    assert decision.reason.startswith("excluded_unrelated_role")


def test_rejects_backend_engineer_without_testing_or_support() -> None:
    decision = evaluate_job(raw_job("Backend Engineer", "Dublin", description="no testing, no QA, no support"))
    assert not decision.accepted
    assert decision.reason == "pure_developer_without_testing_support_relevance"
