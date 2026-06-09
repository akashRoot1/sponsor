from __future__ import annotations

import base64
import logging
import re
import time
from html import unescape
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from models import CompanyConfig, RawJob, SearchFailure, SourceConfig


LOGGER = logging.getLogger(__name__)
USER_AGENT = "akashRoot1-sponsor-job-alert/2.0 (public job links only; contact: akashvikram98@gmail.com)"

LOW_QUALITY_SEARCH_HOSTS = [
    "wikipedia.org",
    "google.com",
    "play.google.com",
    "apps.apple.com",
    "support.",
    "login.",
    "accounts.",
    "youtube.com",
    "facebook.com",
    "instagram.com",
]


class SourceError(RuntimeError):
    def __init__(self, message: str, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"})
    return session


def fetch_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    if source.source_type == "greenhouse":
        return greenhouse_jobs(session, company, source)
    if source.source_type == "lever":
        return lever_jobs(session, company, source)
    if source.source_type == "ashby":
        return ashby_jobs(session, company, source)
    if source.source_type == "smartrecruiters":
        return smartrecruiters_jobs(session, company, source)
    if source.source_type == "workday":
        return workday_jobs(session, company, source)
    if source.source_type == "amazon_jobs":
        return amazon_jobs(session, company, source)
    if source.source_type == "company_careers":
        return company_careers_jobs(session, company, source)
    if source.source_type == "fallback_search":
        return fallback_search_jobs(session, company, source)
    raise SourceError(f"Unsupported source type: {source.source_type}")


def source_endpoint(source: SourceConfig) -> str:
    if source.endpoint:
        return source.endpoint
    if source.source_type == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{source.slug}/jobs?content=true"
    if source.source_type == "lever":
        return f"https://api.lever.co/v0/postings/{source.slug}?mode=json"
    if source.source_type == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{source.slug}?includeCompensation=true"
    if source.source_type == "smartrecruiters":
        return f"https://api.smartrecruiters.com/v1/companies/{source.slug}/postings?limit=100"
    if source.source_type == "workday":
        return f"https://{source.host}/wday/cxs/{source.tenant}/{source.site}/jobs"
    if source.source_type == "amazon_jobs":
        return "https://www.amazon.jobs/en/search.json"
    return source.source_type


def greenhouse_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = session.get(endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    return [
        RawJob(
            company=company.brand_name,
            title=job.get("title", ""),
            location=(job.get("location") or {}).get("name", ""),
            url=job.get("absolute_url", ""),
            source="Greenhouse",
            endpoint=endpoint,
            snippet=_html_to_text(job.get("content", "")),
        )
        for job in response.json().get("jobs", [])
    ]


def lever_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = session.get(endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    return [
        RawJob(
            company=company.brand_name,
            title=job.get("text", ""),
            location=(job.get("categories") or {}).get("location", ""),
            url=job.get("hostedUrl", ""),
            source="Lever",
            endpoint=endpoint,
            snippet=job.get("descriptionPlain", ""),
            work_type=(job.get("categories") or {}).get("commitment", ""),
            category=(job.get("categories") or {}).get("team", ""),
        )
        for job in response.json()
    ]


def ashby_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = session.get(endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    jobs = []
    for job in response.json().get("jobs", []):
        location = _ashby_location(job)
        jobs.append(
            RawJob(
                company=company.brand_name,
                title=job.get("title", ""),
                location=location,
                url=job.get("jobUrl", ""),
                source="Ashby",
                endpoint=endpoint,
                snippet=_html_to_text(job.get("descriptionHtml", "")),
                work_type=" / ".join(part for part in [job.get("employmentType", ""), job.get("workplaceType", "")] if part),
                category=job.get("department", "") or job.get("team", ""),
            )
        )
    return jobs


def smartrecruiters_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = session.get(endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    jobs = []
    for job in response.json().get("content", []):
        location = job.get("location") or {}
        jobs.append(
            RawJob(
                company=company.brand_name,
                title=job.get("name", ""),
                location=", ".join(part for part in [location.get("city", ""), location.get("country", "")] if part),
                url=job.get("ref", "") or job.get("applyUrl", ""),
                source="SmartRecruiters",
                endpoint=endpoint,
                snippet=job.get("name", ""),
                work_type=job.get("typeOfEmployment", {}).get("label", "") if isinstance(job.get("typeOfEmployment"), dict) else "",
            )
        )
    return jobs


def workday_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    jobs: list[RawJob] = []
    response = session.post(endpoint, json={"appliedFacets": {}, "limit": 100, "offset": 0, "searchText": ""}, timeout=30)
    _raise_for_status(response, endpoint)
    for job in response.json().get("jobPostings", []):
        path = job.get("externalPath", "")
        jobs.append(
            RawJob(
                company=company.brand_name,
                title=job.get("title", ""),
                location=job.get("locationsText", ""),
                url=f"https://{source.host}/{source.site}{path}",
                source="Workday",
                endpoint=endpoint,
                snippet=" ".join(str(value) for value in job.get("bulletFields", [])),
                work_type=job.get("remoteType", ""),
            )
        )
    return jobs


def amazon_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    jobs: list[RawJob] = []
    for term in ["QA", "SDET", "Software Test", "Test Automation", "Support Engineer", "Performance Test", "Validation Engineer"]:
        response = session.get(endpoint, params={"base_query": term, "country": "IRL", "result_limit": 50}, timeout=30)
        _raise_for_status(response, endpoint)
        for job in response.json().get("jobs", []):
            path = job.get("job_path", "")
            jobs.append(
                RawJob(
                    company=company.brand_name,
                    title=job.get("title", ""),
                    location=job.get("location", ""),
                    url=f"https://www.amazon.jobs{path}" if path.startswith("/") else path,
                    source="Amazon Jobs",
                    endpoint=endpoint,
                    snippet=_html_to_text(job.get("description", "")),
                )
            )
        time.sleep(0.2)
    return _dedupe_raw(jobs)


def company_careers_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source.endpoint
    response = session.get(endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    soup = BeautifulSoup(response.text, "html.parser")
    jobs = []
    for link in soup.find_all("a", href=True):
        text = _clean_text(link.get_text(" "))
        href = link["href"]
        if not text or not _looks_like_job_link(text, href):
            continue
        url = requests.compat.urljoin(endpoint, href)
        jobs.append(RawJob(company=company.brand_name, title=text, location="", url=url, source="Company Careers", endpoint=endpoint, snippet=text))
    return _dedupe_raw(jobs)


def fallback_search_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    query = f'"{company.brand_name}" ("QA" OR "SDET" OR "test automation" OR "support engineer" OR "validation engineer") Ireland jobs'
    endpoint = f"https://www.bing.com/search?q={quote_plus(query)}"
    response = session.get("https://www.bing.com/search", params={"q": query}, timeout=30)
    _raise_for_status(response, endpoint)
    soup = BeautifulSoup(response.text, "html.parser")
    jobs = []
    for result in soup.select("li.b_algo"):
        link = result.find("a")
        snippet = result.find("p")
        if not link or not link.get("href"):
            continue
        url = _clean_bing_url(link["href"])
        if _is_low_quality_search_result(url):
            continue
        title = _clean_text(link.get_text(" "))
        snippet_text = _clean_text(snippet.get_text(" ")) if snippet else ""
        jobs.append(RawJob(company=company.brand_name, title=title, location=_extract_location(snippet_text), url=url, source="Bing fallback", endpoint=endpoint, snippet=snippet_text))
    return jobs[:10]


def duckduckgo_failure(company: CompanyConfig) -> SearchFailure:
    query = f'"{company.brand_name}" QA SDET Ireland jobs'
    return SearchFailure(company=company.brand_name, source_type="duckduckgo", endpoint=f"https://duckduckgo.com/html/?q={quote_plus(query)}", error="DuckDuckGo is fallback only and often returns HTTP 202; skipped unless explicitly added.")


def _raise_for_status(response: requests.Response, endpoint: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise SourceError(f"{exc} for endpoint {endpoint}", response.status_code) from exc


def _ashby_location(job: dict) -> str:
    parts = [job.get("location", "")]
    address = ((job.get("address") or {}).get("postalAddress") or {})
    parts.extend([address.get("addressLocality", ""), address.get("addressCountry", "")])
    for location in job.get("secondaryLocations", []) or []:
        if isinstance(location, dict):
            parts.append(location.get("location", "") or location.get("name", ""))
    return ", ".join(_clean_text(part) for part in parts if _clean_text(str(part)))


def _looks_like_job_link(text: str, href: str) -> bool:
    lower = f"{text} {href}".lower()
    return any(term in lower for term in ["job", "career", "qa", "test", "support", "validation", "sdet", "engineer", "analyst"])


def _is_low_quality_search_result(url: str) -> bool:
    lower = url.lower()
    parsed = urlparse(lower)
    if any(host in parsed.netloc for host in LOW_QUALITY_SEARCH_HOSTS):
        return True
    if any(path in lower for path in ["/login", "/signin", "/support", "/account", "/wiki/", "/images"]):
        return True
    return False


def _clean_bing_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/"):
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1"):
            payload = encoded[2:]
            padding = "=" * (-len(payload) % 4)
            try:
                return base64.urlsafe_b64decode(payload + padding).decode("utf-8")
            except UnicodeDecodeError:
                return url
    return unescape(url)


def _extract_location(text: str) -> str:
    lower = text.lower()
    for term in ["dublin", "ireland", "cork", "galway", "limerick", "waterford", "remote", "hybrid"]:
        if term in lower:
            return term.title()
    return ""


def _html_to_text(html: str) -> str:
    return _clean_text(BeautifulSoup(html or "", "html.parser").get_text(" "))


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _dedupe_raw(jobs: list[RawJob]) -> list[RawJob]:
    seen = set()
    unique = []
    for job in jobs:
        key = job.url or f"{job.title}|{job.location}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique
