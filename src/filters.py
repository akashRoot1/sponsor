from __future__ import annotations

import re
from dataclasses import dataclass

from models import RawJob


BEST_MATCH_CATEGORY = "Best matches - apply first"
SUPPORT_CATEGORY = "Production/Application Support roles"
API_PERFORMANCE_CATEGORY = "Performance / API Testing roles"
VALIDATION_CATEGORY = "Validation / CSV roles"
MAYBE_CATEGORY = "Maybe relevant - review manually"

STRONG_KEYWORDS = [
    "qa engineer",
    "qa automation",
    "quality engineer",
    "quality assurance engineer",
    "software qa",
    "sdet",
    "software development engineer in test",
    "software engineer in test",
    "test engineer",
    "software test engineer",
    "test automation engineer",
    "automation tester",
    "api test engineer",
    "performance test engineer",
    "jmeter",
    "selenium",
    "playwright",
    "cypress",
    "postman",
    "rest assured",
    "test support engineer",
    "application support engineer",
    "production support engineer",
    "technical support engineer",
    "support engineer",
    "l2 support",
    "l3 support",
    "incident management engineer",
    "application analyst",
    "support analyst",
    "validation engineer",
    "computer system validation",
    "csv engineer",
    "csv tester",
]

WEAK_KEYWORDS = [
    "quality",
    "release",
    "incident",
    "validation",
    "support",
    "technical support",
    "customer success",
    "technical account manager",
    "product enablement",
]

CONTEXT_KEYWORDS = [
    "qa",
    "testing",
    "test",
    "automation",
    "api support",
    "application support",
    "production support",
    "incident troubleshooting",
    "troubleshooting",
    "software support",
    "postman",
    "jmeter",
    "selenium",
    "playwright",
    "cypress",
    "rest assured",
    "csv",
    "computer system validation",
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

EXCLUDED_BUSINESS_TERMS = [
    "sales",
    "marketing",
    "finance",
    "legal",
    "hr",
    "human resources",
    "warehouse",
    "chef",
    "nurse",
    "driver",
    "accountant",
    "global sanctions",
    "engagement manager",
    "product manager",
    "project manager",
    "program manager",
    "business development",
    "corporate development",
    "revenue operations",
    "gtm product enablement",
    "product enablement",
]

SECURITY_TERMS = ["security engineer", "security engineering manager"]
NETWORK_CABLING_TERMS = ["cabling quality", "network cabling", "network infrastructure construction", "data center construction"]
CUSTOMER_SUCCESS_TERMS = ["customer success", "account manager", "technical account manager"]
GENERIC_QUALITY_TERMS = ["supplier quality engineer", "cabling quality manager", "quality technician", "quality program manager"]
PURE_DEVELOPER_TERMS = ["backend engineer", "frontend engineer", "front end engineer", "software developer", "full stack engineer"]
PURE_MANAGER_TERMS = ["manager", "director", "vp ", "svp ", "head of"]


@dataclass(frozen=True)
class FilterDecision:
    accepted: bool
    reason: str
    matched_keyword: str = ""
    category: str = MAYBE_CATEGORY
    score: int = 0


def evaluate_job(job: RawJob) -> FilterDecision:
    title = _normalize(job.title)
    description = _normalize(_strip_negative_phrases(job.snippet))
    location = _normalize(job.location)
    combined = " ".join([title, description, location, _normalize(job.work_type), _normalize(job.category), _normalize(job.url)])

    strong_title = _first_match(title, STRONG_KEYWORDS)
    strong_description = _first_match(description, STRONG_KEYWORDS)
    weak_title = _first_match(title, WEAK_KEYWORDS)
    weak_description = _first_match(description, WEAK_KEYWORDS)
    context = _first_match(" ".join([title, description]), CONTEXT_KEYWORDS)
    location_relevant = _location_is_relevant(combined)

    score = 0
    if strong_title:
        score += 10
    if strong_description:
        score += 5
    if weak_title:
        score += 3
    if weak_description:
        score += 1
    if location_relevant:
        score += 5

    hard_rejection = _hard_rejection_reason(title, description, bool(strong_title), bool(strong_description), bool(context))
    if hard_rejection:
        return FilterDecision(False, hard_rejection, strong_title or strong_description or weak_title or weak_description, _category(title, description), score)

    if not location_relevant:
        return FilterDecision(False, "location_mismatch", strong_title or strong_description or weak_title or weak_description, _category(title, description), score - 20)

    if weak_description and not (strong_title or strong_description or context):
        return FilterDecision(False, "weak_description_only_keyword", weak_description, MAYBE_CATEGORY, score)

    matched = strong_title or strong_description or weak_title or weak_description
    if not matched:
        return FilterDecision(False, "keyword_mismatch", "", MAYBE_CATEGORY, score)

    if score < 10:
        return FilterDecision(False, "weak_description_only_keyword", matched, _category(title, description), score)

    return FilterDecision(True, f"score={score}; title-first match", matched, _category(title, description), score)


def _hard_rejection_reason(title: str, description: str, strong_title: bool, strong_description: bool, has_context: bool) -> str:
    if _first_match(title, EXCLUDED_BUSINESS_TERMS):
        return "excluded_sales_marketing_finance_hr_legal" if _first_match(title, ["sales", "marketing", "finance", "legal", "hr", "human resources", "accountant"]) else "manager_business_role"
    if _first_match(title, NETWORK_CABLING_TERMS):
        return "network_cabling_quality_role"
    if _first_match(title, GENERIC_QUALITY_TERMS) and not has_context:
        return "generic_quality_role_not_software_testing"
    if _first_match(title, SECURITY_TERMS) and not (strong_title or strong_description):
        return "security_role_not_qa"
    if _first_match(title, CUSTOMER_SUCCESS_TERMS) and not (strong_title or strong_description or _first_match(description, CONTEXT_KEYWORDS)):
        if "technical account manager" in title:
            return "technical_account_manager_not_qa"
        return "customer_success_not_support_engineering"
    if _first_match(title, PURE_DEVELOPER_TERMS) and not (strong_title or strong_description):
        return "pure_developer_without_testing_support"
    if _first_match(title, PURE_MANAGER_TERMS) and not (strong_title or strong_description):
        return "manager_business_role"
    return ""


def _category(title: str, description: str) -> str:
    text = " ".join([title, description])
    if _first_match(title, ["qa automation", "sdet", "software test engineer", "test automation engineer", "qa engineer", "quality assurance engineer", "test support engineer", "test engineer", "automation tester"]):
        return BEST_MATCH_CATEGORY
    if _first_match(title, ["application support engineer", "production support engineer", "technical support engineer", "support engineer", "incident management engineer", "l2 support", "l3 support", "application analyst", "support analyst", "onsite support engineer", "ai support engineer", "senior support engineer"]):
        return SUPPORT_CATEGORY
    if _first_match(text, ["performance test engineer", "api test engineer", "jmeter", "postman", "rest assured"]):
        return API_PERFORMANCE_CATEGORY
    if _first_match(text, ["validation engineer", "csv engineer", "csv tester", "computer system validation"]):
        return VALIDATION_CATEGORY
    return MAYBE_CATEGORY


def _location_is_relevant(text: str) -> bool:
    return bool(_first_match(text, IRELAND_LOCATION_TERMS))


def _first_match(text: str, terms: list[str]) -> str:
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
            return term
    return ""


def normalize_dedupe_value(value: str) -> str:
    value = _normalize(value)
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\bii\s+bilingual\b", "ii bilingual", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _strip_negative_phrases(text: str) -> str:
    cleaned = _normalize(text)
    for phrase in ["no testing", "no qa", "no support", "no automation", "without testing", "without qa"]:
        cleaned = cleaned.replace(phrase, "")
    return cleaned


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()
