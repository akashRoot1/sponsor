from __future__ import annotations

import re
from dataclasses import dataclass

from models import RawJob


ROLE_KEYWORDS = [
    "qa automation engineer",
    "qa engineer",
    "quality engineer",
    "quality assurance",
    "sdet",
    "software development engineer in test",
    "software engineer in test",
    "test engineer",
    "software test engineer",
    "test analyst",
    "automation tester",
    "test automation",
    "api test engineer",
    "api testing",
    "performance test engineer",
    "performance testing",
    "jmeter",
    "cypress",
    "playwright",
    "selenium",
    "postman",
    "rest assured",
    "ci/cd qa",
    "release qa",
    "production support qa",
    "application support engineer",
    "production support engineer",
    "test support engineer",
    "support engineer",
    "technical support engineer",
    "operations support engineer",
    "l2 support",
    "l3 support",
    "incident management",
    "application analyst",
    "support analyst",
    "validation engineer",
    "computer system validation",
    "csv tester",
    "csv engineer",
]

GENERAL_RELEVANT_TERMS = [
    "test",
    "qa",
    "quality",
    "automation",
    "sdet",
    "software test",
    "application support",
    "production support",
    "support engineer",
    "technical support",
    "validation",
    "csv",
    "incident",
    "release",
]

IRELAND_LOCATION_TERMS = [
    "ireland",
    "dublin",
    "cork",
    "galway",
    "limerick",
    "waterford",
    "remote ireland",
    "hybrid ireland",
    "dublin / remote",
    "dublin/remote",
    "irl",
]

REMOTE_TERMS = ["remote", "hybrid"]

EXCLUDED_TERMS = [
    "sales",
    "marketing",
    "hr",
    "human resources",
    "finance",
    "legal",
    "warehouse",
    "chef",
    "nurse",
    "driver",
    "accountant",
    "product manager",
    "business development",
]

PURE_DEVELOPER_TERMS = [
    "backend engineer",
    "front end engineer",
    "frontend engineer",
    "software developer",
    "software engineer",
    "full stack engineer",
]

CATEGORY_KEYWORDS = [
    ("Production/Application Support roles relevant to QA profile", ["application support", "production support", "test support", "support engineer", "technical support", "operations support", "l2 support", "l3 support", "incident", "application analyst", "support analyst"]),
    ("Performance / API Testing roles", ["performance", "api testing", "api test", "jmeter", "postman", "rest assured"]),
    ("QA / SDET / Test Automation roles", ["qa", "sdet", "test automation", "automation tester", "software development engineer in test", "software engineer in test", "software test", "cypress", "playwright", "selenium"]),
    ("Validation / CSV roles", ["validation", "computer system validation", "csv"]),
]

IRRELEVANT_TECH_TITLE_TERMS = [
    "security engineer",
    "network engineer",
    "core network engineer",
    "director of software engineering",
    "vp of software engineering",
    "technical project manager",
    "project manager",
    "product manager",
    "revenue operations",
    "corporate development",
]


@dataclass(frozen=True)
class FilterDecision:
    accepted: bool
    reason: str
    matched_keyword: str = ""
    category: str = "Other relevant Quality/Test roles"


def evaluate_job(job: RawJob) -> FilterDecision:
    title_text = _normalize(job.title)
    searchable_text = _normalize(" ".join([job.title, job.location, job.work_type, job.category, _strip_negative_phrases(job.snippet)]))

    excluded = _first_match(title_text, EXCLUDED_TERMS)
    if excluded:
        return FilterDecision(False, f"excluded_unrelated_role:{excluded}")

    title_keyword = _first_match(title_text, ROLE_KEYWORDS + GENERAL_RELEVANT_TERMS)
    text_keyword = title_keyword or _first_match(searchable_text, ROLE_KEYWORDS + GENERAL_RELEVANT_TERMS)

    irrelevant_tech_title = _first_match(title_text, IRRELEVANT_TECH_TITLE_TERMS)
    if irrelevant_tech_title and not title_keyword:
        return FilterDecision(False, f"irrelevant_title:{irrelevant_tech_title}")

    if _first_match(title_text, PURE_DEVELOPER_TERMS) and not title_keyword:
        return FilterDecision(False, "pure_developer_without_testing_support_relevance")

    if not text_keyword:
        return FilterDecision(False, "keyword_mismatch")

    if not title_keyword and text_keyword in {"qa", "quality", "automation", "test"}:
        return FilterDecision(False, "weak_description_only_keyword")

    if not _location_is_relevant(job):
        return FilterDecision(False, "location_mismatch")

    return FilterDecision(True, "accepted", text_keyword, _categorize(title_text, searchable_text))


def _location_is_relevant(job: RawJob) -> bool:
    location_text = _normalize(" ".join([job.location, job.snippet, job.url]))
    if _first_match(location_text, IRELAND_LOCATION_TERMS):
        return True
    if _first_match(_normalize(job.location), REMOTE_TERMS) and _first_match(location_text, IRELAND_LOCATION_TERMS):
        return True
    return False


def _categorize(title: str, text: str) -> str:
    if _first_match(title, ["application support", "production support", "test support", "support engineer", "technical support", "operations support", "l2 support", "l3 support", "incident", "application analyst", "support analyst"]):
        return "Production/Application Support roles relevant to QA profile"
    if _first_match(title, ["performance", "api testing", "api test", "jmeter", "postman", "rest assured"]):
        return "Performance / API Testing roles"
    if _first_match(title, ["validation", "computer system validation", "csv"]):
        return "Validation / CSV roles"
    if _first_match(title, ["qa", "sdet", "test automation", "automation tester", "software development engineer in test", "software engineer in test", "software test", "test engineer", "quality engineer", "cypress", "playwright", "selenium"]):
        return "QA / SDET / Test Automation roles"
    for category, terms in CATEGORY_KEYWORDS:
        if _first_match(text, terms):
            return category
    return "Other relevant Quality/Test roles"


def _first_match(text: str, terms: list[str]) -> str:
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
            return term
    return ""


def _strip_negative_phrases(text: str) -> str:
    cleaned = _normalize(text)
    for phrase in ["no testing", "no qa", "no support", "no automation", "without testing", "without qa"]:
        cleaned = cleaned.replace(phrase, "")
    return cleaned


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()
