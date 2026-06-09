from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html import unescape
from typing import Any, Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup


LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "akashRoot1-sponsor-job-alert/1.0 "
    "(public job link search; contact: akashvikram98@gmail.com)"
)

ALLOWED_SOURCE_HINTS = [
    "greenhouse.io",
    "lever.co",
    "myworkdayjobs.com",
    "workdayjobs.com",
    "smartrecruiters.com",
    "ashbyhq.com",
    "jobs.ashbyhq.com",
    "amazon.jobs",
    "linkedin.com/jobs",
    "careers.",
    "/careers",
    "/jobs",
    "/job/",
]

IRELAND_TERMS = [
    "ireland",
    "dublin",
    "galway",
    "cork",
    "limerick",
    "remote ireland",
    "hybrid ireland",
    "irl",
]

INCLUDE_TERMS = [
    "qa",
    "quality engineer",
    "quality assurance",
    "sdet",
    "software development engineer in test",
    "software engineer in test",
    "test engineer",
    "software test engineer",
    "automation engineer",
    "test automation",
    "qa automation",
    "api testing",
    "api test",
    "performance testing",
    "performance test",
    "jmeter",
    "cypress",
    "playwright",
    "selenium",
    "postman",
    "rest assured",
    "validation engineer",
    "csv",
    "computer system validation",
    "production support",
    "application support",
    "release qa",
    "test analyst",
]

EXCLUDE_TERMS = [
    "sales",
    "account executive",
    "marketing",
    "recruiter",
    "talent acquisition",
    "human resources",
    "warehouse",
    "finance manager",
    "financial analyst",
    "legal counsel",
    "customer success",
]

TEST_MODE_COMPANIES = {
    "Stripe Technology Company Limited",
    "Workday Limited",
    "Amazon Web Services EMEA SARL",
    "MasterCard Ireland Limited",
    "Version 1 Software Limited",
}


@dataclass(frozen=True)
class JobResult:
    title: str
    company: str
    location: str
    url: str
    matching_keyword: str
    source: str
    date_found: str


@dataclass
class RawJob:
    company: str
    title: str
    location: str
    url: str
    source: str
    endpoint: str
    snippet: str = ""


@dataclass
class RejectedJob:
    company: str
    title: str
    location: str
    url: str
    source: str
    reason: str


@dataclass
class SearchFailure:
    company: str
    source: str
    endpoint: str
    error: str


@dataclass
class SourceStats:
    company: str
    source: str
    endpoint: str
    raw_jobs_found: int = 0
    after_keyword_filtering: int = 0
    after_location_filtering: int = 0
    failed: bool = False
    error: str = ""


@dataclass
class CompanySearchReport:
    company: str
    searched_successfully: bool = False
    had_failure: bool = False
    matched_jobs: list[JobResult] = field(default_factory=list)
    raw_jobs: list[RawJob] = field(default_factory=list)
    rejected_jobs: list[RejectedJob] = field(default_factory=list)
    failures: list[SearchFailure] = field(default_factory=list)
    source_stats: list[SourceStats] = field(default_factory=list)


@dataclass
class SearchReport:
    companies: list[CompanySearchReport]
    jobs: list[JobResult]

    @property
    def failures(self) -> list[SearchFailure]:
        return [failure for company in self.companies for failure in company.failures]

    @property
    def rejected_jobs(self) -> list[RejectedJob]:
        return [job for company in self.companies for job in company.rejected_jobs]

    @property
    def raw_jobs(self) -> list[RawJob]:
        return [job for company in self.companies for job in company.raw_jobs]

    @property
    def successful_company_count(self) -> int:
        return sum(1 for company in self.companies if company.searched_successfully)

    @property
    def failed_company_count(self) -> int:
        return sum(1 for company in self.companies if company.had_failure)

    @property
    def no_job_company_count(self) -> int:
        return sum(
            1
            for company in self.companies
            if company.searched_successfully and not company.had_failure and not company.matched_jobs
        )

    def to_artifacts(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        raw = [asdict(job) for job in self.raw_jobs]
        filtered = [asdict(job) for job in self.jobs]
        failures = [asdict(failure) for failure in self.failures]
        return raw, filtered, failures


DIRECT_SOURCE_CONFIG: dict[str, list[dict[str, str]]] = {
    "Stripe Technology Company Limited": [{"type": "greenhouse", "slug": "stripe"}],
    "Datadog Ireland Limited": [{"type": "greenhouse", "slug": "datadog"}],
    "MongoDB Limited": [{"type": "lever", "slug": "mongodb"}],
    "Intercom R&D Unlimited Company": [{"type": "greenhouse", "slug": "intercom"}],
    "Workday Limited": [{"type": "workday", "tenant": "workday", "site": "Workday", "host": "workday.wd5.myworkdayjobs.com"}],
    "Amazon Web Services EMEA SARL": [{"type": "amazon"}],
    "Amazon Development Centre Ireland Limited": [{"type": "amazon"}],
    "Amazon Data Services Ireland Limited": [{"type": "amazon"}],
    "Amazon Ireland Support Services Limited": [{"type": "amazon"}],
    "MasterCard Ireland Limited": [{"type": "workday", "tenant": "mastercard", "site": "mastercard", "host": "mastercard.wd1.myworkdayjobs.com"}],
    "Version 1 Software Limited": [{"type": "smartrecruiters", "slug": "Version1"}],
}


def find_jobs(companies: Iterable[str], keywords: list[str], generated_at: datetime) -> SearchReport:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    company_reports: list[CompanySearchReport] = []
    all_jobs: list[JobResult] = []

    for index, company in enumerate(companies, start=1):
        LOGGER.info("Searching company=%s index=%s", company, index)
        report = _search_company(session, company, keywords, generated_at)
        report.matched_jobs = _dedupe_results(report.matched_jobs)
        company_reports.append(report)
        all_jobs.extend(report.matched_jobs)
        LOGGER.info(
            "Company summary company=%s success=%s failures=%s raw=%s matched=%s rejected=%s",
            company,
            report.searched_successfully,
            len(report.failures),
            len(report.raw_jobs),
            len(report.matched_jobs),
            len(report.rejected_jobs),
        )
        time.sleep(1.0)

    return SearchReport(companies=company_reports, jobs=_dedupe_results(all_jobs))


def _search_company(
    session: requests.Session,
    company: str,
    keywords: list[str],
    generated_at: datetime,
) -> CompanySearchReport:
    report = CompanySearchReport(company=company)
    direct_sources = DIRECT_SOURCE_CONFIG.get(company, [])

    for source_config in direct_sources:
        _run_source(report, session, company, source_config, keywords, generated_at)
        time.sleep(0.5)

    if not report.matched_jobs:
        for source_config in _search_engine_sources(company):
            _run_source(report, session, company, source_config, keywords, generated_at)
            time.sleep(0.5)
            if report.matched_jobs:
                break

    return report


def _run_source(
    report: CompanySearchReport,
    session: requests.Session,
    company: str,
    source_config: dict[str, str],
    keywords: list[str],
    generated_at: datetime,
) -> None:
    source = source_config["type"]
    endpoint = _source_endpoint(source_config)
    stats = SourceStats(company=company, source=source, endpoint=endpoint)

    try:
        raw_jobs = _fetch_source(session, source_config)
        stats.raw_jobs_found = len(raw_jobs)
        report.raw_jobs.extend(raw_jobs)

        keyword_passed: list[RawJob] = []
        location_passed: list[RawJob] = []
        for raw_job in raw_jobs:
            keyword = _matching_keyword(_job_text(raw_job), keywords)
            if not keyword and not _contains_any(_job_text(raw_job), INCLUDE_TERMS):
                _reject(report, raw_job, "keyword_mismatch")
                continue
            keyword_passed.append(raw_job)

            if not _is_ireland_job(raw_job):
                _reject(report, raw_job, "location_mismatch")
                continue
            location_passed.append(raw_job)

            rejected_reason = _rejection_reason(raw_job)
            if rejected_reason:
                _reject(report, raw_job, rejected_reason)
                continue

            report.matched_jobs.append(
                JobResult(
                    title=raw_job.title or "Job posting",
                    company=company,
                    location=raw_job.location or "Ireland",
                    url=raw_job.url,
                    matching_keyword=keyword or "Related QA/testing role",
                    source=raw_job.source,
                    date_found=generated_at.strftime("%Y-%m-%d"),
                )
            )

        stats.after_keyword_filtering = len(keyword_passed)
        stats.after_location_filtering = len(location_passed)
        report.searched_successfully = True
        LOGGER.info(
            "Search source company=%s source=%s endpoint=%s raw=%s after_keyword=%s after_location=%s accepted=%s",
            company,
            source,
            endpoint,
            stats.raw_jobs_found,
            stats.after_keyword_filtering,
            stats.after_location_filtering,
            len(report.matched_jobs),
        )
    except Exception as exc:
        stats.failed = True
        stats.error = str(exc)
        report.had_failure = True
        failure = SearchFailure(company=company, source=source, endpoint=endpoint, error=str(exc))
        report.failures.append(failure)
        LOGGER.warning("Search failure company=%s source=%s endpoint=%s error=%s", company, source, endpoint, exc)
    finally:
        report.source_stats.append(stats)


def _fetch_source(session: requests.Session, source_config: dict[str, str]) -> list[RawJob]:
    source_type = source_config["type"]
    if source_type == "greenhouse":
        return _greenhouse_jobs(session, source_config["slug"])
    if source_type == "lever":
        return _lever_jobs(session, source_config["slug"])
    if source_type == "ashby":
        return _ashby_jobs(session, source_config["slug"])
    if source_type == "smartrecruiters":
        return _smartrecruiters_jobs(session, source_config["slug"])
    if source_type == "workday":
        return _workday_jobs(session, source_config["host"], source_config["tenant"], source_config["site"])
    if source_type == "amazon":
        return _amazon_jobs(session)
    if source_type == "bing":
        return _bing_search(session, source_config["company"], source_config["query"])
    if source_type == "duckduckgo":
        return _duckduckgo_search(session, source_config["company"], source_config["query"])
    raise ValueError(f"Unknown source type: {source_type}")


def _greenhouse_jobs(session: requests.Session, slug: str) -> list[RawJob]:
    endpoint = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    response = session.get(endpoint, timeout=25)
    response.raise_for_status()
    jobs = response.json().get("jobs", [])
    return [
        RawJob(
            company=slug,
            title=job.get("title", ""),
            location=(job.get("location") or {}).get("name", ""),
            url=job.get("absolute_url", ""),
            source="Greenhouse",
            endpoint=endpoint,
            snippet=_clean_text(BeautifulSoup(job.get("content", ""), "html.parser").get_text(" ")),
        )
        for job in jobs
    ]


def _lever_jobs(session: requests.Session, slug: str) -> list[RawJob]:
    endpoint = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    response = session.get(endpoint, timeout=25)
    response.raise_for_status()
    jobs = response.json()
    return [
        RawJob(
            company=slug,
            title=job.get("text", ""),
            location=(job.get("categories") or {}).get("location", ""),
            url=job.get("hostedUrl", ""),
            source="Lever",
            endpoint=endpoint,
            snippet=_clean_text(job.get("descriptionPlain", "")),
        )
        for job in jobs
    ]


def _ashby_jobs(session: requests.Session, slug: str) -> list[RawJob]:
    endpoint = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    response = session.get(endpoint, timeout=25)
    response.raise_for_status()
    jobs = response.json().get("jobs", [])
    return [
        RawJob(
            company=slug,
            title=job.get("title", ""),
            location=", ".join(location.get("name", "") for location in job.get("location", []) if isinstance(location, dict)),
            url=job.get("jobUrl", ""),
            source="Ashby",
            endpoint=endpoint,
            snippet=_clean_text(job.get("descriptionPlain", "")),
        )
        for job in jobs
    ]


def _smartrecruiters_jobs(session: requests.Session, slug: str) -> list[RawJob]:
    endpoint = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
    response = session.get(endpoint, timeout=25)
    response.raise_for_status()
    jobs = response.json().get("content", [])
    return [
        RawJob(
            company=slug,
            title=job.get("name", ""),
            location=((job.get("location") or {}).get("city", "") + ", " + (job.get("location") or {}).get("country", "")).strip(", "),
            url=job.get("ref", "") or job.get("applyUrl", ""),
            source="SmartRecruiters",
            endpoint=endpoint,
            snippet=job.get("name", ""),
        )
        for job in jobs
    ]


def _workday_jobs(session: requests.Session, host: str, tenant: str, site: str) -> list[RawJob]:
    endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    jobs: list[RawJob] = []
    for term in ["QA", "SDET", "Software Test", "Test Automation", "Quality Engineer", "Validation Engineer", "Production Support"]:
        response = session.post(
            endpoint,
            json={"appliedFacets": {}, "limit": 50, "offset": 0, "searchText": f"{term} Ireland"},
            timeout=25,
        )
        response.raise_for_status()
        for job in response.json().get("jobPostings", []):
            path = job.get("externalPath", "")
            jobs.append(
                RawJob(
                    company=tenant,
                    title=job.get("title", ""),
                    location=job.get("locationsText", ""),
                    url=f"https://{host}/{site}{path}",
                    source="Workday",
                    endpoint=endpoint,
                    snippet=" ".join(str(value) for value in job.get("bulletFields", [])),
                )
            )
        time.sleep(0.2)
    return _dedupe_raw_jobs(jobs)


def _amazon_jobs(session: requests.Session) -> list[RawJob]:
    endpoint = "https://www.amazon.jobs/en/search.json"
    jobs: list[RawJob] = []
    for term in ["QA", "SDET", "Software Test", "Test Automation", "Quality Engineer", "Validation Engineer"]:
        response = session.get(
            endpoint,
            params={"base_query": term, "country": "IRL", "result_limit": 50},
            timeout=25,
        )
        response.raise_for_status()
        for job in response.json().get("jobs", []):
            location = job.get("location", "")
            path = job.get("job_path", "")
            jobs.append(
                RawJob(
                    company="Amazon",
                    title=job.get("title", ""),
                    location=location,
                    url=f"https://www.amazon.jobs{path}" if path.startswith("/") else path,
                    source="Amazon Jobs",
                    endpoint=endpoint,
                    snippet=job.get("description", ""),
                )
            )
        time.sleep(0.2)
    return _dedupe_raw_jobs(jobs)


def _bing_search(session: requests.Session, company: str, query: str) -> list[RawJob]:
    endpoint = f"https://www.bing.com/search?q={quote_plus(query)}"
    response = session.get("https://www.bing.com/search", params={"q": query}, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    items: list[RawJob] = []
    for result in soup.select("li.b_algo"):
        link = result.find("a")
        if not link or not link.get("href"):
            continue
        snippet = result.find("p")
        url = _clean_bing_url(link["href"])
        items.append(
            RawJob(
                company=company,
                title=_clean_text(link.get_text(" ")),
                location=_extract_location(_clean_text(snippet.get_text(" ")) if snippet else ""),
                url=url,
                source="Bing",
                endpoint=endpoint,
                snippet=_clean_text(snippet.get_text(" ")) if snippet else "",
            )
        )
    return items[:10]


def _duckduckgo_search(session: requests.Session, company: str, query: str) -> list[RawJob]:
    endpoint = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    response = session.get(endpoint, timeout=20)
    response.raise_for_status()
    if response.status_code == 202:
        raise RuntimeError("DuckDuckGo returned HTTP 202 challenge/queued response")

    soup = BeautifulSoup(response.text, "html.parser")
    items: list[RawJob] = []
    for result in soup.select(".result"):
        link = result.select_one(".result__a")
        if not link or not link.get("href"):
            continue
        snippet = result.select_one(".result__snippet")
        snippet_text = _clean_text(snippet.get_text(" ")) if snippet else ""
        items.append(
            RawJob(
                company=company,
                title=_clean_text(link.get_text(" ")),
                location=_extract_location(snippet_text),
                url=_clean_duckduckgo_url(link["href"]),
                source="DuckDuckGo",
                endpoint=endpoint,
                snippet=snippet_text,
            )
        )
    return items[:8]


def _search_engine_sources(company: str) -> list[dict[str, str]]:
    company_names = _company_search_names(company)
    broad_terms = '"QA" OR "SDET" OR "test automation" OR "software test" OR "validation engineer" OR "production support"'
    query = f'"{company_names[0]}" ({broad_terms}) Ireland jobs careers'
    return [
        {"type": "bing", "company": company, "query": query},
        {"type": "duckduckgo", "company": company, "query": query},
    ]


def _source_endpoint(source_config: dict[str, str]) -> str:
    source_type = source_config["type"]
    if source_type == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{source_config['slug']}/jobs?content=true"
    if source_type == "lever":
        return f"https://api.lever.co/v0/postings/{source_config['slug']}?mode=json"
    if source_type == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{source_config['slug']}?includeCompensation=true"
    if source_type == "smartrecruiters":
        return f"https://api.smartrecruiters.com/v1/companies/{source_config['slug']}/postings?limit=100"
    if source_type == "workday":
        return f"https://{source_config['host']}/wday/cxs/{source_config['tenant']}/{source_config['site']}/jobs"
    if source_type == "amazon":
        return "https://www.amazon.jobs/en/search.json"
    if source_type == "bing":
        return f"https://www.bing.com/search?q={quote_plus(source_config['query'])}"
    if source_type == "duckduckgo":
        return f"https://duckduckgo.com/html/?q={quote_plus(source_config['query'])}"
    return source_type


def _rejection_reason(raw_job: RawJob) -> str | None:
    text = _job_text(raw_job)
    if not raw_job.url:
        return "missing_url"
    if not _is_allowed_direct_source(raw_job.url):
        return "not_direct_job_source"
    if _contains_any(text, EXCLUDE_TERMS):
        return "excluded_unrelated_role"
    return None


def _reject(report: CompanySearchReport, raw_job: RawJob, reason: str) -> None:
    LOGGER.info("Rejected job company=%s source=%s title=%s reason=%s", report.company, raw_job.source, raw_job.title, reason)
    report.rejected_jobs.append(
        RejectedJob(
            company=report.company,
            title=raw_job.title,
            location=raw_job.location,
            url=raw_job.url,
            source=raw_job.source,
            reason=reason,
        )
    )


def _company_search_names(company: str) -> list[str]:
    aliases = {
        "Gilead Sciences Ireland UC": ["Gilead"],
        "Amazon Web Services EMEA SARL": ["Amazon", "AWS"],
        "Amazon Development Centre Ireland Limited": ["Amazon", "AWS"],
        "Amazon Data Services Ireland Limited": ["Amazon", "AWS"],
        "Amazon Ireland Support Services Limited": ["Amazon", "AWS"],
        "Microsoft Ireland Operations Limited": ["Microsoft"],
        "Microsoft Ireland Research Unlimited Company": ["Microsoft"],
        "Google Ireland Limited": ["Google"],
        "Stripe Technology Company Limited": ["Stripe"],
        "Apple Distribution International Limited": ["Apple"],
        "Apple Operations International Limited": ["Apple"],
        "Meta Platforms Ireland Limited": ["Meta"],
        "Toasttab Ireland Limited": ["Toast"],
        "2K Games Dublin Limited": ["2K Games"],
        "Tata Consultancy Services Ireland Limited": ["Tata Consultancy Services", "TCS"],
        "Tata Consultancy Services Limited": ["Tata Consultancy Services", "TCS"],
        "Cognizant Technology Solutions Ireland Limited": ["Cognizant"],
        "HCL Ireland Information Systems Limited": ["HCLTech", "HCL"],
        "HCL Technologies Limited": ["HCLTech", "HCL"],
        "Ernst & Young": ["EY"],
        "PricewaterhouseCoopers Services": ["PwC"],
        "MasterCard Ireland Limited": ["Mastercard"],
        "J.P. Morgan SE": ["JPMorgan Chase", "J.P. Morgan"],
        "Citibank Europe Public Limited Company": ["Citi", "Citibank"],
        "Citibank N.A.": ["Citi", "Citibank"],
        "Bank of Ireland Group PLC": ["Bank of Ireland"],
        "Allied Irish Banks PLC": ["AIB"],
        "Permanent TSB Public Limited Company": ["Permanent TSB"],
        "Dell Products Unlimited Company": ["Dell"],
        "EMC Information Systems International Unlimited Company": ["Dell EMC", "Dell"],
        "Oracle EMEA Ltd": ["Oracle"],
        "Oracle Financial Services Software B.V": ["Oracle Financial Services"],
        "MSD International GmbH": ["MSD Ireland", "Merck"],
        "Johnson & Johnson Vision Care Ireland Unlimited Company": ["Johnson & Johnson"],
        "Boston Scientific Cork": ["Boston Scientific"],
        "Abbott Diagnostics": ["Abbott"],
    }
    cleaned = re.sub(
        r"\b(Limited|Unlimited Company|Ireland Limited|Ireland|Research|Operations|Technology Company|DAC|LLP|PLC|Public Limited Company|Designated Activity Company|UC|GmbH|B\.V|Ltd|Co Ltd|SARL)\b",
        "",
        company,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,-")
    names = aliases.get(company, []) + [cleaned, company]
    return [name for index, name in enumerate(names) if name and name not in names[:index]]


def _job_text(job: RawJob) -> str:
    return f"{job.title} {job.location} {job.snippet} {job.url}".lower()


def _is_ireland_job(job: RawJob) -> bool:
    text = _job_text(job)
    return _contains_any(text, IRELAND_TERMS)


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)


def _matching_keyword(text: str, keywords: Iterable[str]) -> str | None:
    lower_text = text.lower()
    for keyword in keywords:
        if keyword.lower() in lower_text:
            return keyword
    for term in INCLUDE_TERMS:
        if term in lower_text:
            return term
    return None


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


def _clean_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return unescape(url)


def _is_allowed_direct_source(url: str) -> bool:
    lower = url.lower()
    return any(hint in lower for hint in ALLOWED_SOURCE_HINTS)


def _extract_location(text: str) -> str:
    lower = text.lower()
    for term in IRELAND_TERMS:
        if term in lower:
            return term.title()
    return ""


def _dedupe_results(results: Iterable[JobResult]) -> list[JobResult]:
    seen_urls: set[str] = set()
    unique: list[JobResult] = []
    for result in results:
        if result.url in seen_urls:
            continue
        seen_urls.add(result.url)
        unique.append(result)
    return unique


def _dedupe_raw_jobs(results: Iterable[RawJob]) -> list[RawJob]:
    seen_urls: set[str] = set()
    unique: list[RawJob] = []
    for result in results:
        key = result.url or f"{result.title}|{result.location}"
        if key in seen_urls:
            continue
        seen_urls.add(key)
        unique.append(result)
    return unique


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text or "")).strip()
