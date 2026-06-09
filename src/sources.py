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
    def __init__(self, message: str, http_status: int | None = None, error_type: str = "api_failure", retry_count: int = 0) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.error_type = error_type
        self.retry_count = retry_count


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; akashRoot1-sponsor-job-alert/2.0)",
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    })
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
    if source.source_type == "teamtailor":
        return teamtailor_jobs(session, company, source)
    if source.source_type == "bamboohr":
        return bamboohr_jobs(session, company, source)
    if source.source_type == "personio":
        return personio_jobs(session, company, source)
    if source.source_type == "attrax":
        return attrax_jobs(session, company, source)
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
    if source.source_type == "teamtailor":
        return source.endpoint or f"https://{source.slug}.teamtailor.com/jobs"
    if source.source_type == "bamboohr":
        return source.endpoint or f"https://{source.slug}.bamboohr.com/careers/list"
    if source.source_type == "personio":
        return source.endpoint or f"https://{source.slug}.jobs.personio.com"
    if source.source_type == "attrax":
        return source.endpoint
    return source.source_type


def source_quality(source_type: str) -> str:
    if source_type in {"greenhouse", "lever", "ashby", "smartrecruiters", "workday", "amazon_jobs", "teamtailor", "bamboohr", "personio", "attrax"}:
        return "direct_api" if source_type in {"workday", "amazon_jobs"} else "job_board_api"
    if source_type == "company_careers":
        return "direct_career_page"
    if source_type == "fallback_search":
        return "search_engine_fallback"
    return "failed"


def request_with_retries(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    retry_statuses = {429, 500, 502, 503, 504}
    delays = [1, 2, 4]
    retries = 0
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = session.request(method, url, **kwargs)
            response.retry_count = retries
            if response.status_code in retry_statuses:
                last_error = SourceError(f"http_{response.status_code}: temporary HTTP failure for endpoint {url}", response.status_code, "api_failure", retries)
                if attempt < 3:
                    time.sleep(delays[attempt - 1])
                    retries += 1
                    continue
            if _empty_response(response) and attempt < 3:
                last_error = SourceError(f"empty_response: empty response body for endpoint {url}", response.status_code, "api_failure", retries)
                time.sleep(delays[attempt - 1])
                retries += 1
                continue
            return response
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(delays[attempt - 1])
                retries += 1
                continue
            error_type = "timeout_failure" if isinstance(exc, requests.Timeout) else "network_failure"
            raise SourceError(f"{error_type}: {exc} for endpoint {url}", None, error_type, retries) from exc
    if isinstance(last_error, SourceError):
        last_error.retry_count = retries
        raise last_error
    raise SourceError(f"api_failure: request failed for endpoint {url}", None, "api_failure", retries)


def greenhouse_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = request_with_retries(session, "GET", endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    data = _json_response(response, endpoint)
    return [
        RawJob(
            company=company.brand_name,
            title=job.get("title", ""),
            location=(job.get("location") or {}).get("name", ""),
            url=job.get("absolute_url", ""),
            source="Greenhouse",
            endpoint=endpoint,
            snippet=_html_to_text(job.get("content", "")),
            source_type=source.source_type,
            source_quality=source_quality(source.source_type),
        )
        for job in data.get("jobs", [])
    ]


def lever_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = request_with_retries(session, "GET", endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    data = _json_response(response, endpoint)
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
            source_type=source.source_type,
            source_quality=source_quality(source.source_type),
        )
        for job in data
    ]


def ashby_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = request_with_retries(session, "GET", endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    data = _json_response(response, endpoint)
    jobs = []
    for job in data.get("jobs", []):
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
                source_type=source.source_type,
                source_quality=source_quality(source.source_type),
            )
        )
    return jobs


def smartrecruiters_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = request_with_retries(session, "GET", endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    data = _json_response(response, endpoint)
    jobs = []
    for job in data.get("content", []):
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
                source_type=source.source_type,
                source_quality=source_quality(source.source_type),
            )
        )
    return jobs


def workday_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    jobs: list[RawJob] = []
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    limit = 20
    offset = 0
    while True:
        response = request_with_retries(
            session,
            "POST",
            endpoint,
            json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
            headers=headers,
            timeout=30,
        )
        _raise_for_status(response, endpoint)
        data = _json_response(response, endpoint)
        postings = data.get("jobPostings", [])
        for job in postings:
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
                    source_type=source.source_type,
                    source_quality=source_quality(source.source_type),
                )
            )
        offset += limit
        if not postings or offset >= int(data.get("total", len(jobs))):
            break
        time.sleep(0.2)
    return jobs


def amazon_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    jobs: list[RawJob] = []
    for term in ["QA", "SDET", "Software Test", "Test Automation", "Support Engineer", "Performance Test", "Validation Engineer"]:
        response = request_with_retries(session, "GET", endpoint, params={"base_query": term, "country": "IRL", "result_limit": 50}, timeout=30)
        _raise_for_status(response, endpoint)
        data = _json_response(response, endpoint)
        for job in data.get("jobs", []):
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
                    source_type=source.source_type,
                    source_quality=source_quality(source.source_type),
                )
            )
        time.sleep(0.2)
    return _dedupe_raw(jobs)


def company_careers_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source.endpoint
    response = request_with_retries(session, "GET", endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    soup = BeautifulSoup(response.text, "html.parser")
    jobs = []
    for link in soup.find_all("a", href=True):
        text = _clean_text(link.get_text(" "))
        href = link["href"]
        if not text or not _looks_like_job_link(text, href):
            continue
        url = requests.compat.urljoin(endpoint, href)
        jobs.append(RawJob(company=company.brand_name, title=text, location="", url=url, source="Company Careers", endpoint=endpoint, snippet=text, source_type=source.source_type, source_quality=source_quality(source.source_type)))
    return _dedupe_raw(jobs)


def teamtailor_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    return _html_careers_jobs(session, company, source, endpoint, "Teamtailor")


def bamboohr_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = request_with_retries(session, "GET", endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    try:
        data = _json_response(response, endpoint)
    except SourceError:
        return _html_jobs_from_text(company, source, endpoint, response.text, "BambooHR")
    postings = data.get("result", data) if isinstance(data, dict) else data
    jobs = []
    for job in postings if isinstance(postings, list) else []:
        jobs.append(
            RawJob(
                company=company.brand_name,
                title=job.get("jobOpeningName", "") or job.get("title", ""),
                location=job.get("location", {}).get("name", "") if isinstance(job.get("location"), dict) else job.get("location", ""),
                url=job.get("url", "") or endpoint,
                source="BambooHR",
                endpoint=endpoint,
                snippet=job.get("description", "") or job.get("title", ""),
                source_type=source.source_type,
                source_quality=source_quality(source.source_type),
            )
        )
    return _dedupe_raw(jobs)


def personio_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    endpoint = source_endpoint(source)
    response = request_with_retries(session, "GET", endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    try:
        data = _json_response(response, endpoint)
    except SourceError:
        return _html_jobs_from_text(company, source, endpoint, response.text, "Personio")
    postings = data.get("data", data) if isinstance(data, dict) else data
    jobs = []
    for job in postings if isinstance(postings, list) else []:
        attributes = job.get("attributes", job)
        jobs.append(
            RawJob(
                company=company.brand_name,
                title=attributes.get("name", "") or attributes.get("title", ""),
                location=attributes.get("office", "") or attributes.get("location", ""),
                url=attributes.get("url", "") or endpoint,
                source="Personio",
                endpoint=endpoint,
                snippet=attributes.get("description", "") or attributes.get("name", ""),
                source_type=source.source_type,
                source_quality=source_quality(source.source_type),
            )
        )
    return _dedupe_raw(jobs)


def attrax_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    base_endpoint = source_endpoint(source)
    terms = ["qa", "quality", "test", "testing", "validation", "csv", "support"]
    jobs: list[RawJob] = []
    for term in terms:
        response = request_with_retries(session, "GET", base_endpoint, params={"q": term}, timeout=30)
        endpoint = response.url if getattr(response, "url", "") else f"{base_endpoint}?q={quote_plus(term)}"
        _raise_for_status(response, endpoint)
        soup = BeautifulSoup(response.text, "html.parser")
        for tile in soup.select(".attrax-vacancy-tile"):
            title_link = tile.select_one(".attrax-vacancy-tile__title[href]")
            if not title_link:
                continue
            title = _clean_text(title_link.get_text(" "))
            url = requests.compat.urljoin(base_endpoint, title_link["href"])
            location = _select_text(tile, ".attrax-vacancy-tile__location-freetext .attrax-vacancy-tile__item-value")
            work_type = " / ".join(
                part
                for part in [
                    _select_text(tile, ".attrax-vacancy-tile__option-work-location-type .attrax-vacancy-tile__item-value"),
                    _select_text(tile, ".attrax-vacancy-tile__option-job-type .attrax-vacancy-tile__item-value"),
                ]
                if part
            )
            category = _select_text(tile, ".attrax-vacancy-tile__option-function .attrax-vacancy-tile__item-value")
            snippet = _select_text(tile, ".attrax-vacancy-tile__description") or _clean_text(tile.get_text(" "))
            jobs.append(
                RawJob(
                    company=company.brand_name,
                    title=title,
                    location=location,
                    url=url,
                    source="Attrax Careers",
                    endpoint=endpoint,
                    snippet=snippet,
                    work_type=work_type,
                    category=category,
                    source_type=source.source_type,
                    source_quality=source_quality(source.source_type),
                )
            )
        time.sleep(0.2)
    return _dedupe_raw(jobs)


def fallback_search_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig) -> list[RawJob]:
    query = f'"{company.brand_name}" ("QA" OR "SDET" OR "test automation" OR "support engineer" OR "validation engineer") Ireland jobs'
    endpoint = f"https://www.bing.com/search?q={quote_plus(query)}"
    response = request_with_retries(session, "GET", "https://www.bing.com/search", params={"q": query}, timeout=30)
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
        jobs.append(RawJob(company=company.brand_name, title=title, location=_extract_location(snippet_text), url=url, source="Bing fallback", endpoint=endpoint, snippet=snippet_text, source_type=source.source_type, source_quality=source_quality(source.source_type)))
    return jobs[:10]


def duckduckgo_failure(company: CompanyConfig) -> SearchFailure:
    query = f'"{company.brand_name}" QA SDET Ireland jobs'
    return SearchFailure(company=company.brand_name, source_type="duckduckgo", endpoint=f"https://duckduckgo.com/html/?q={quote_plus(query)}", error="DuckDuckGo is fallback only and often returns HTTP 202; skipped unless explicitly added.")


def _raise_for_status(response: requests.Response, endpoint: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        retry_count = getattr(response, "retry_count", 0)
        if response.status_code == 403:
            raise SourceError(f"blocked_by_site: {exc} for endpoint {endpoint}", response.status_code, "blocked_by_site", retry_count) from exc
        if response.status_code == 404:
            raise SourceError(f"invalid_source_url: {exc} for endpoint {endpoint}", response.status_code, "invalid_source_url", retry_count) from exc
        raise SourceError(f"api_failure: {exc} for endpoint {endpoint}", response.status_code, "api_failure", retry_count) from exc


def _empty_response(response: requests.Response) -> bool:
    return response.status_code == 200 and not (response.text or "").strip()


def _json_response(response: requests.Response, endpoint: str) -> object:
    try:
        return response.json()
    except ValueError as exc:
        retry_count = getattr(response, "retry_count", 0)
        raise SourceError(f"parsing_error: malformed JSON from endpoint {endpoint}", response.status_code, "parsing_failure", retry_count) from exc


def _html_careers_jobs(session: requests.Session, company: CompanyConfig, source: SourceConfig, endpoint: str, source_name: str) -> list[RawJob]:
    response = request_with_retries(session, "GET", endpoint, timeout=30)
    _raise_for_status(response, endpoint)
    return _html_jobs_from_text(company, source, endpoint, response.text, source_name)


def _html_jobs_from_text(company: CompanyConfig, source: SourceConfig, endpoint: str, html_text: str, source_name: str) -> list[RawJob]:
    soup = BeautifulSoup(html_text, "html.parser")
    jobs = []
    for link in soup.find_all("a", href=True):
        text = _clean_text(link.get_text(" "))
        href = link["href"]
        if not text or not _looks_like_job_link(text, href):
            continue
        url = requests.compat.urljoin(endpoint, href)
        location = _extract_location(" ".join([text, href]))
        jobs.append(
            RawJob(
                company=company.brand_name,
                title=text,
                location=location,
                url=url,
                source=source_name,
                endpoint=endpoint,
                snippet=text,
                source_type=source.source_type,
                source_quality=source_quality(source.source_type),
            )
        )
    return _dedupe_raw(jobs)


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


def _select_text(node, selector: str) -> str:
    element = node.select_one(selector)
    return _clean_text(element.get_text(" ")) if element else ""


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
