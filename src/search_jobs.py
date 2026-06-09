from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Iterable
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
]

INCLUDE_TERMS = [
    "qa",
    "quality assurance",
    "sdet",
    "software test",
    "test automation",
    "automation test",
    "api test",
    "performance test",
    "software engineer in test",
    "test engineer",
    "automation tester",
    "validation engineer",
    "csv",
    "cypress",
    "playwright",
    "selenium",
    "postman",
    "rest assured",
    "jmeter",
    "ci/cd qa",
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


@dataclass(frozen=True)
class JobResult:
    title: str
    company: str
    location: str
    url: str
    matching_keyword: str
    source: str
    date_found: str


def find_jobs(companies: Iterable[str], keywords: list[str], generated_at: datetime) -> list[JobResult]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    results: list[JobResult] = []
    for index, company in enumerate(companies, start=1):
        LOGGER.info("Searching %s (%s)", company, index)
        try:
            results.extend(_search_company(session, company, keywords, generated_at))
        except Exception:
            LOGGER.exception("Search failed for %s", company)
        time.sleep(1.2)

    return _dedupe_results(results)


def _search_company(
    session: requests.Session,
    company: str,
    keywords: list[str],
    generated_at: datetime,
) -> list[JobResult]:
    broad_terms = '"QA" OR "SDET" OR "test automation" OR "software test" OR "validation engineer"'
    queries = [
        f'"{company}" ({broad_terms}) Ireland jobs',
        f'"{company}" ("Cypress" OR "Playwright" OR "Selenium" OR "Postman" OR "JMeter") Ireland careers',
    ]

    found: list[JobResult] = []
    for query in queries:
        for item in _duckduckgo_search(session, query):
            job = _candidate_to_job(item, company, keywords, generated_at)
            if job:
                found.append(job)
        time.sleep(1.0)

    return found


def _duckduckgo_search(session: requests.Session, query: str) -> list[dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    response = session.get(url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    items: list[dict[str, str]] = []
    for result in soup.select(".result"):
        link = result.select_one(".result__a")
        if not link or not link.get("href"):
            continue

        snippet = result.select_one(".result__snippet")
        href = _clean_duckduckgo_url(link["href"])
        items.append(
            {
                "title": _clean_text(link.get_text(" ")),
                "url": href,
                "snippet": _clean_text(snippet.get_text(" ")) if snippet else "",
            }
        )

    return items[:8]


def _candidate_to_job(
    item: dict[str, str],
    company: str,
    keywords: list[str],
    generated_at: datetime,
) -> JobResult | None:
    url = item["url"]
    text = f"{item['title']} {item['snippet']} {url}".lower()

    if not _is_allowed_direct_source(url):
        return None
    if not _contains_any(text, IRELAND_TERMS):
        return None
    if _contains_any(text, EXCLUDE_TERMS):
        return None

    keyword = _matching_keyword(text, keywords)
    if not keyword and not _contains_any(text, INCLUDE_TERMS):
        return None

    title = _normalize_title(item["title"], company)
    location = _extract_location(item["snippet"])

    return JobResult(
        title=title,
        company=company,
        location=location,
        url=url,
        matching_keyword=keyword or "Related QA/testing role",
        source=_source_name(url),
        date_found=generated_at.strftime("%Y-%m-%d"),
    )


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


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)


def _matching_keyword(text: str, keywords: Iterable[str]) -> str | None:
    for keyword in keywords:
        if keyword.lower() in text:
            return keyword
    return None


def _normalize_title(raw_title: str, company: str) -> str:
    title = re.sub(r"\s*[-|]\s*(Careers|Jobs|LinkedIn|Greenhouse|Lever).*$", "", raw_title, flags=re.I)
    title = title.replace(company, "").strip(" -|")
    return title or raw_title or "Job posting"


def _extract_location(snippet: str) -> str:
    lower = snippet.lower()
    for term in IRELAND_TERMS:
        if term in lower:
            return term.title()
    return "Ireland"


def _source_name(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    if "greenhouse.io" in host:
        return "Greenhouse"
    if "lever.co" in host:
        return "Lever"
    if "workday" in host:
        return "Workday"
    if "smartrecruiters" in host:
        return "SmartRecruiters"
    if "ashbyhq" in host:
        return "Ashby"
    if "linkedin.com" in host:
        return "LinkedIn Jobs"
    return host or "Company careers"


def _dedupe_results(results: Iterable[JobResult]) -> list[JobResult]:
    seen_urls: set[str] = set()
    unique: list[JobResult] = []
    for result in results:
        if result.url in seen_urls:
            continue
        seen_urls.add(result.url)
        unique.append(result)
    return unique
