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
from sources import SourceError, _json_response, attrax_jobs, company_careers_jobs, eightfold_jobs, oracle_hcm_jobs, phenom_jobs, request_with_retries, successfactors_jobs


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: object | None = None, json_error: bool = False, text: str = "", url: str = "https://example.com/jobs") -> None:
        self.status_code = status_code
        self.payload = payload if payload is not None else {}
        self.json_error = json_error
        self.text = text or "<html>ok</html>"
        self.url = url
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


def test_attrax_parser_captures_abbvie_quality_engineer_card() -> None:
    html = """
    <div class="attrax-vacancy-tile" data-jobid="24893">
      <a class="attrax-vacancy-tile__title" href="/en/job/quality-engineer-in-sligo-so-jid-24893">Quality Engineer</a>
      <div class="attrax-vacancy-tile__location-freetext">
        <p class="attrax-vacancy-tile__item-value">Sligo, SO</p>
      </div>
      <div class="attrax-vacancy-tile__option-work-location-type">
        <p class="attrax-vacancy-tile__item-value">Hybrid</p>
      </div>
      <div class="attrax-vacancy-tile__option-job-type">
        <p class="attrax-vacancy-tile__item-value">Full-time</p>
      </div>
      <div class="attrax-vacancy-tile__option-function">
        <p class="attrax-vacancy-tile__item-value">Operations</p>
      </div>
      <div class="attrax-vacancy-tile__description">The role of the Quality Engineer at AbbVie Ballytivnan.</div>
    </div>
    """
    session = FakeSession([FakeResponse(200, text=html, url="https://careers.abbvie.com/en/jobs?q=quality")])
    company = CompanyConfig("AbbVie Ireland NL B.V.", "AbbVie", ["AbbVie"], sources=[SourceConfig("attrax", endpoint="https://careers.abbvie.com/en/jobs")])
    jobs = attrax_jobs(session, company, company.sources[0])
    assert jobs[0].title == "Quality Engineer"
    assert jobs[0].location == "Sligo, SO"
    assert jobs[0].url == "https://careers.abbvie.com/en/job/quality-engineer-in-sligo-so-jid-24893"


def test_successfactors_parser_captures_ireland_support_role() -> None:
    html = """
    <table>
      <tr class="data-row">
        <td><a class="jobTitle-link" href="/job/Dublin-24-Senior-Technical-Support-Engineer-D24WA02/1285411901/">Senior Technical Support Engineer</a></td>
        <td>Dublin 24, IE, D24WA02</td>
        <td>Customer Support</td>
      </tr>
    </table>
    """
    session = FakeSession([FakeResponse(200, text=html, url="https://jobs.sap.com/search/?q=support&locationsearch=Ireland")])
    company = CompanyConfig("SAP Ireland Limited", "SAP", ["SAP"], sources=[SourceConfig("successfactors", endpoint="https://jobs.sap.com/search/")])
    jobs = successfactors_jobs(session, company, company.sources[0])
    assert jobs[0].title == "Senior Technical Support Engineer"
    assert jobs[0].location == "Dublin"
    assert jobs[0].url == "https://jobs.sap.com/job/Dublin-24-Senior-Technical-Support-Engineer-D24WA02/1285411901/"


def test_generic_company_careers_derives_title_from_job_slug_when_link_text_is_generic() -> None:
    html = """
    <article>
      <h3>Quality Engineer</h3>
      <p>Sligo, Ireland Hybrid</p>
      <a href="/en/job/quality-engineer-in-sligo-so-jid-24893">Learn more</a>
    </article>
    """
    session = FakeSession([FakeResponse(200, text=html, url="https://example.com/careers")])
    company = CompanyConfig("Example Limited", "Example", ["Example"], sources=[SourceConfig("company_careers", endpoint="https://example.com/careers")])
    jobs = company_careers_jobs(session, company, company.sources[0])
    assert jobs[0].title == "Quality Engineer"
    assert jobs[0].location == "Sligo"


def test_phenom_parser_captures_ireland_quality_role() -> None:
    payload = {
        "refineSearch": {
            "status": 200,
            "data": {
                "jobs": [
                    {
                        "title": "QA Specialist",
                        "location": "Cork, Ireland",
                        "applyUrl": "https://example.wd5.myworkdayjobs.com/job/Cork/QA-Specialist_R-1/apply",
                        "descriptionTeaser": "GMP quality assurance and batch release support.",
                        "type": "Full Time",
                        "category": "Manufacturing/Quality",
                    }
                ]
            },
        }
    }
    session = FakeSession([FakeResponse(200, payload=payload, url="https://careers.example.com/widgets")])
    company = CompanyConfig("Example Limited", "Example", ["Example"], sources=[SourceConfig("phenom", endpoint="https://careers.example.com/widgets")])
    jobs = phenom_jobs(session, company, company.sources[0])
    assert jobs[0].title == "QA Specialist"
    assert jobs[0].location == "Cork, Ireland"
    assert jobs[0].url == "https://example.wd5.myworkdayjobs.com/job/Cork/QA-Specialist_R-1/apply"


def test_oracle_hcm_parser_captures_expanded_requisition_list() -> None:
    payload = {
        "items": [
            {
                "requisitionList": [
                    {
                        "Id": "210754522",
                        "Title": "Application Support Engineer",
                        "PrimaryLocation": "Dublin, Ireland",
                        "ShortDescriptionStr": "Production support, incident management, and application support.",
                        "JobFunction": "Technology",
                        "WorkplaceType": "Hybrid",
                        "workLocation": [{"TownOrCity": "Dublin", "Country": "IE"}],
                    }
                ]
            }
        ]
    }
    session = FakeSession([FakeResponse(200, payload=payload, url="https://oracle.example/hcmRestApi/resources/latest/recruitingCEJobRequisitions")])
    company = CompanyConfig("Oracle EMEA Ltd", "Oracle", ["Oracle"], sources=[SourceConfig("oracle_hcm", host="oracle.example", site="CX_45001")])
    jobs = oracle_hcm_jobs(session, company, company.sources[0])
    assert jobs[0].title == "Application Support Engineer"
    assert jobs[0].location == "Dublin, Ireland, Dublin"
    assert jobs[0].url == "https://oracle.example/hcmUI/CandidateExperience/en/sites/CX_45001/job/210754522"


def test_eightfold_parser_uses_generic_job_card_extraction() -> None:
    html = """
    <div class="position">
      <h2>Technical Support Engineer</h2>
      <span>Dublin, Ireland</span>
      <a href="/careers/job/technical-support-engineer-123">View job</a>
    </div>
    """
    session = FakeSession([FakeResponse(200, text=html, url="https://example.eightfold.ai/careers")])
    company = CompanyConfig("Example Limited", "Example", ["Example"], sources=[SourceConfig("eightfold", endpoint="https://example.eightfold.ai/careers")])
    jobs = eightfold_jobs(session, company, company.sources[0])
    assert jobs[0].title == "Technical Support Engineer"
    assert jobs[0].location == "Dublin"
