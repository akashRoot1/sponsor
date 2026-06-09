from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pytest
import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import search_jobs
from models import CompanyConfig, RawJob, SourceConfig
from sources import SourceError, _json_response, request_with_retries


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: object | None = None, json_error: bool = False) -> None:
        self.status_code = status_code
        self.payload = payload if payload is not None else {}
        self.json_error = json_error
        self.text = "<html></html>"
        self.retry_count = 0

    def json(self) -> object:
        if self.json_error:
            raise ValueError("bad json")
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def request(self, method: str, url: str, **kwargs) -> FakeResponse:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


def test_retries_on_http_429() -> None:
    session = FakeSession([FakeResponse(429), FakeResponse(429), FakeResponse(200)])
    response = request_with_retries(session, "GET", "https://example.com/jobs")
    assert response.status_code == 200
    assert session.calls == 3
    assert response.retry_count == 2


def test_retries_on_http_503() -> None:
    session = FakeSession([FakeResponse(503), FakeResponse(200)])
    response = request_with_retries(session, "GET", "https://example.com/jobs")
    assert response.status_code == 200
    assert session.calls == 2
    assert response.retry_count == 1


def test_malformed_json_raises_parsing_failure() -> None:
    response = FakeResponse(200, json_error=True)
    response.retry_count = 2
    with pytest.raises(SourceError) as exc:
        _json_response(response, "https://example.com/jobs")
    assert exc.value.error_type == "parsing_failure"
    assert exc.value.retry_count == 2


def test_workflow_continues_after_one_company_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    companies = [
        CompanyConfig("Bad Company Limited", "Bad Company", ["Bad Company"], sources=[SourceConfig("greenhouse", slug="bad")]),
        CompanyConfig("Good Company Limited", "Good Company", ["Good Company"], sources=[SourceConfig("greenhouse", slug="good")]),
    ]

    def fake_fetch_jobs(session, company, source):
        if company.brand_name == "Bad Company":
            raise SourceError("api_failure: temporary issue", 503, "api_failure", 2)
        return [RawJob(company.brand_name, "QA Analyst", "Dublin", "https://example.com/good", "Greenhouse", "endpoint", source_type=source.source_type, source_quality="job_board_api")]

    monkeypatch.setattr(search_jobs, "fetch_jobs", fake_fetch_jobs)
    report = search_jobs.find_jobs(companies, datetime(2026, 6, 9, 5, 0, tzinfo=ZoneInfo("Europe/Dublin")))
    assert report.failed_company_count == 1
    assert report.successful_company_count == 1
    assert len(report.jobs) == 1
    assert report.failures[0].retry_count == 2


def test_fallback_fetch_logic_is_triggered_when_primary_source_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    company = CompanyConfig(
        "Fallback Company Limited",
        "Fallback Company",
        ["Fallback Company"],
        careers_url="https://example.com/careers",
        sources=[SourceConfig("greenhouse", slug="fallback")],
    )
    called_sources: list[str] = []

    def fake_fetch_jobs(session, company_config, source):
        called_sources.append(source.source_type)
        if source.source_type == "greenhouse":
            raise SourceError("api_failure: temporary issue", 503, "api_failure", 2)
        return [RawJob(company_config.brand_name, "QA Analyst", "Dublin", "https://example.com/job", "Company Careers", source.endpoint, source_type=source.source_type, source_quality="direct_career_page")]

    monkeypatch.setattr(search_jobs, "fetch_jobs", fake_fetch_jobs)
    report = search_jobs.find_jobs([company], datetime(2026, 6, 9, 5, 0, tzinfo=ZoneInfo("Europe/Dublin")))
    assert called_sources == ["greenhouse", "company_careers"]
    assert len(report.jobs) == 1
    assert report.fallback_fetch_count == 1
    assert report.partially_successful_company_count == 1
