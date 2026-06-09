from __future__ import annotations

import logging
import re
import time
import base64
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
            company_results = _search_company(session, company, keywords, generated_at)
            LOGGER.info("Accepted %s candidate jobs for %s.", len(company_results), company)
            results.extend(company_results)
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
    company_names = _company_search_names(company)
    queries = []
    for company_name in company_names[:2]:
        queries.extend(
            [
                f'"{company_name}" ({broad_terms}) Ireland jobs',
                f'"{company_name}" ("Cypress" OR "Playwright" OR "Selenium" OR "Postman" OR "JMeter") Ireland careers',
            ]
        )

    found: list[JobResult] = []
    for query in queries:
        items = _bing_search(session, query)
        if not items:
            items = _duckduckgo_search(session, query)
        LOGGER.debug("Query returned %s raw items: %s", len(items), query)
        for item in items:
            job = _candidate_to_job(item, company, keywords, generated_at)
            if job:
                found.append(job)
        time.sleep(0.8)

    return found


def _bing_search(session: requests.Session, query: str) -> list[dict[str, str]]:
    response = session.get("https://www.bing.com/search", params={"q": query}, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    items: list[dict[str, str]] = []
    for result in soup.select("li.b_algo"):
        link = result.find("a")
        if not link or not link.get("href"):
            continue

        snippet = result.find("p")
        items.append(
            {
                "title": _clean_text(link.get_text(" ")),
                "url": _clean_bing_url(link["href"]),
                "snippet": _clean_text(snippet.get_text(" ")) if snippet else "",
            }
        )

    return items[:10]


def _duckduckgo_search(session: requests.Session, query: str) -> list[dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    response = session.get(url, timeout=20)
    response.raise_for_status()
    if response.status_code == 202:
        LOGGER.warning("DuckDuckGo returned HTTP 202 for query: %s", query)
        return []

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


def _company_search_names(company: str) -> list[str]:
    aliases = {
        "Amazon Web Services EMEA SARL": ["Amazon Web Services", "AWS"],
        "Amazon Development Centre Ireland Limited": ["Amazon"],
        "Amazon Data Services Ireland Limited": ["Amazon"],
        "Amazon Ireland Support Services Limited": ["Amazon"],
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
        r"\b(Limited|Unlimited Company|Ireland Limited|Ireland|Research|Operations|DAC|LLP|PLC|Public Limited Company|Designated Activity Company|UC|GmbH|B\.V|Ltd|Co Ltd|SARL)\b",
        "",
        company,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,-")
    names = aliases.get(company, []) + [cleaned, company]
    return [name for index, name in enumerate(names) if name and name not in names[:index]]


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


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()
