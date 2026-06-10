from __future__ import annotations

import re
from dataclasses import dataclass

from location_utils import is_ireland_relevant
from models import RawJob


BEST_MATCH_CATEGORY = "Apply First - Best QA/Test Matches"
BROAD_CATEGORY = "QA / Test / Quality Broad Matches"
SUPPORT_CATEGORY = "Production/Application Support Roles"
API_PERFORMANCE_CATEGORY = "API / Performance / Automation Tool Matches"
VALIDATION_CATEGORY = "Validation / CSV Roles"
MAYBE_CATEGORY = "Maybe Relevant - Review Manually"

VERY_STRONG_TITLE_KEYWORDS = [
    "quality assurance engineer",
    "software development engineer in test",
    "software engineer in test",
    "software testing",
    "software test engineer",
    "test automation engineer",
    "application support engineer",
    "production support engineer",
    "technical support engineer",
    "quality analyst",
    "test analyst",
    "qa analyst",
    "qa engineer",
    "quality engineer",
    "quality assurance",
    "software test",
    "test engineer",
    "test automation",
    "automation tester",
    "automation engineer",
    "support engineer",
    "validation engineer",
    "csv tester",
    "csv engineer",
    "sdet",
    "testing",
    "tester",
    "test",
    "qa",
]

BROAD_TITLE_KEYWORDS = [
    "quality analyst",
    "test analyst",
    "qa analyst",
    "quality assurance",
    "software test",
    "software testing",
    "testing",
    "tester",
    "quality",
    "test",
    "qa",
]

STRONG_DESCRIPTION_KEYWORDS = [
    "rest assured",
    "api testing",
    "performance testing",
    "regression testing",
    "manual testing",
    "functional testing",
    "ci/cd testing",
    "release testing",
    "defect management",
    "bug tracking",
    "test cases",
    "test plans",
    "test scripts",
    "selenium",
    "playwright",
    "cypress",
    "postman",
    "jmeter",
    "jira",
    "uat",
]

SUPPORT_ROLE_KEYWORDS = [
    "application support",
    "production support",
    "technical support",
    "support engineer",
    "support analyst",
    "application analyst",
    "incident management",
    "l2 support",
    "l3 support",
    "release support",
]

SUPPORT_TITLE_CONTEXT = ["engineer", "analyst", "support", "application", "production", "technical", "incident", "operations"]

TOOL_KEYWORDS = [
    "rest assured",
    "api testing",
    "performance testing",
    "jmeter",
    "selenium",
    "playwright",
    "cypress",
    "postman",
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
    "quality assurance",
    "software test",
    "software testing",
    "quality analyst",
    "test analyst",
    "qa analyst",
    "manual testing",
    "regression testing",
    "functional testing",
    "release testing",
    "defect management",
    "bug tracking",
    "test cases",
    "test plans",
    "test scripts",
    "postman",
    "jmeter",
    "selenium",
    "playwright",
    "cypress",
    "rest assured",
    "csv",
    "computer system validation",
    "uat",
]

WEAK_KEYWORDS = ["quality", "release", "incident", "validation", "support", "technical support"]

IRELAND_LOCATION_TERMS = [
    "ireland",
    "dublin",
    "cork",
    "galway",
    "sligo",
    "westport",
    "mayo",
    "athlone",
    "carlow",
    "kilkenny",
    "tipperary",
    "waterford",
    "wexford",
    "meath",
    "kildare",
    "louth",
    "wicklow",
    "clare",
    "donegal",
    "leitrim",
    "roscommon",
    "longford",
    "offaly",
    "laois",
    "westmeath",
    "monaghan",
    "cavan",
    "kerry",
    "kilkenny",
    "limerick",
    "remote ireland",
    "hybrid ireland",
    "ireland remote",
    "dublin / remote",
    "dublin/remote",
    "irl",
]

NON_IRELAND_LOCATION_TERMS = [
    "manila",
    "philippines",
    "madrid",
    "spain",
    "london",
    "united kingdom",
    "uk",
    "england",
    "scotland",
    "wales",
    "germany",
    "berlin",
    "france",
    "paris",
    "netherlands",
    "amsterdam",
    "poland",
    "warsaw",
    "india",
    "bangalore",
    "bengaluru",
    "hyderabad",
    "pune",
    "united states",
    "usa",
    "canada",
    "toronto",
    "australia",
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
CUSTOMER_SUCCESS_STRONG_CONTEXT = ["qa", "testing", "test automation", "application support", "production support", "api support", "incident management", "software support"]
GENERIC_QUALITY_TERMS = [
    "supplier quality engineer",
    "cabling quality manager",
    "quality technician",
    "quality program manager",
    "food quality inspector",
    "construction quality manager",
    "data center construction quality",
]
NON_SOFTWARE_QUALITY_CONTEXT = ["hardware", "supplier", "cabling", "construction", "food", "data center", "network"]
PURE_DEVELOPER_TERMS = ["backend engineer", "frontend engineer", "front end engineer", "software developer", "full stack engineer", "software engineer"]
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
    work_type = _normalize(job.work_type)
    category = _normalize(job.category)
    url = _normalize(job.url)
    combined = " ".join([title, description, location, work_type, category, url])

    very_strong_title = _first_match(title, VERY_STRONG_TITLE_KEYWORDS)
    broad_title = _first_match(title, BROAD_TITLE_KEYWORDS)
    strong_description = _first_match(description, STRONG_DESCRIPTION_KEYWORDS)
    support_title = _support_title_match(title)
    tool_title = _first_match(title, TOOL_KEYWORDS)
    tool_description = _first_match(description, TOOL_KEYWORDS)
    weak_title = _first_match(title, WEAK_KEYWORDS)
    weak_description = _first_match(description, WEAK_KEYWORDS)
    context = _first_match(" ".join([title, description]), CONTEXT_KEYWORDS)
    location_relevant = _job_location_is_relevant(location, " ".join([work_type, category, url, description]))

    score = 0
    if very_strong_title:
        score += 15
    if broad_title:
        score += 12
    if strong_description:
        score += 5
    if location_relevant:
        score += 5
    if support_title:
        score += 12
    if tool_title:
        score += 10
    if tool_description:
        score += 3
    if weak_title:
        score += 2
    if weak_description:
        score += 1
    if _first_match(title, EXCLUDED_BUSINESS_TERMS):
        score -= 20
    if _first_match(title, PURE_DEVELOPER_TERMS) and not _title_has_testing_override(title):
        score -= 15
    if _is_non_software_quality(title, description):
        score -= 12

    matched = very_strong_title or broad_title or support_title or strong_description or tool_title or tool_description or weak_title or weak_description
    hard_rejection = _hard_rejection_reason(title, description, bool(very_strong_title or support_title), bool(strong_description), bool(context))
    if hard_rejection:
        return FilterDecision(False, hard_rejection, matched, _category(title, description), score)

    if not location_relevant:
        return FilterDecision(False, "location_mismatch", matched, _category(title, description), score - 20)

    if not matched:
        return FilterDecision(False, "keyword_mismatch", "", MAYBE_CATEGORY, score)

    if _title_has_testing_override(title):
        return FilterDecision(True, f"score={score}; broad QA/Test/Quality title override", matched, _category(title, description), score)

    if weak_description and not (very_strong_title or broad_title or support_title or strong_description or context):
        return FilterDecision(False, "weak_description_only_keyword", matched, MAYBE_CATEGORY, score)

    if score < 12:
        return FilterDecision(False, "weak_description_only_keyword", matched, _category(title, description), score)

    return FilterDecision(True, f"score={score}; relevant role and Ireland location", matched, _category(title, description), score)


def _hard_rejection_reason(title: str, description: str, strong_title: bool, strong_description: bool, has_context: bool) -> str:
    if _first_match(title, EXCLUDED_BUSINESS_TERMS):
        return "excluded_sales_marketing_finance_hr_legal" if _first_match(title, ["sales", "marketing", "finance", "legal", "hr", "human resources", "accountant"]) else "manager_business_role"
    if _first_match(title, NETWORK_CABLING_TERMS):
        return "non_software_quality_role"
    if _is_non_software_quality(title, description):
        return "non_software_quality_role"
    if _first_match(title, SECURITY_TERMS) and not (strong_title or strong_description):
        return "security_role_not_qa"
    if _first_match(title, CUSTOMER_SUCCESS_TERMS) and not (strong_title or _first_match(description, CUSTOMER_SUCCESS_STRONG_CONTEXT)):
        if "technical account manager" in title:
            return "technical_account_manager_not_qa"
        return "customer_success_not_support_engineering"
    if _first_match(title, PURE_DEVELOPER_TERMS) and not _title_has_testing_override(title):
        return "pure_developer_without_testing_support"
    if _first_match(title, PURE_MANAGER_TERMS) and not (strong_title or strong_description):
        return "manager_business_role"
    return ""


def _category(title: str, description: str) -> str:
    text = " ".join([title, description])
    if _first_match(title, ["qa automation", "sdet", "software development engineer in test", "software engineer in test", "software test engineer", "test automation engineer", "qa engineer", "quality assurance engineer", "quality analyst", "test analyst", "qa analyst", "test engineer", "automation tester"]):
        return BEST_MATCH_CATEGORY
    if _first_match(title, ["application support engineer", "production support engineer", "technical support engineer", "support engineer", "incident management engineer", "l2 support", "l3 support", "application analyst", "support analyst", "onsite support engineer", "ai support engineer", "senior support engineer"]):
        return SUPPORT_CATEGORY
    if _first_match(text, ["performance test engineer", "api test engineer", "jmeter", "postman", "rest assured", "selenium", "playwright", "cypress", "api testing", "performance testing"]):
        return API_PERFORMANCE_CATEGORY
    if _first_match(text, ["validation engineer", "csv engineer", "csv tester", "computer system validation"]):
        return VALIDATION_CATEGORY
    if _first_match(title, BROAD_TITLE_KEYWORDS):
        return BROAD_CATEGORY
    return MAYBE_CATEGORY


def _location_is_relevant(text: str) -> bool:
    return bool(_first_match(text, IRELAND_LOCATION_TERMS) or is_ireland_relevant(text))


def _job_location_is_relevant(location: str, fallback_context: str) -> bool:
    if _location_is_relevant(location):
        return True
    if _has_explicit_non_ireland_location(location):
        return False
    return _location_is_relevant(fallback_context)


def _has_explicit_non_ireland_location(location: str) -> bool:
    return bool(location and not _location_is_relevant(location) and _first_match(location, NON_IRELAND_LOCATION_TERMS))


def _first_match(text: str, terms: list[str]) -> str:
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
            return term
    return ""


def _support_title_match(title: str) -> str:
    match = _first_match(title, SUPPORT_ROLE_KEYWORDS)
    if match and _first_match(title, SUPPORT_TITLE_CONTEXT):
        return match
    return ""


def _title_has_testing_override(title: str) -> bool:
    return bool(_first_match(title, ["quality analyst", "test analyst", "qa analyst", "quality assurance", "software test", "software testing", "sdet", "testing", "tester", "test", "qa"]))


def _is_non_software_quality(title: str, description: str) -> bool:
    text = " ".join([title, description])
    if not _first_match(title, ["quality", "validation"]):
        return False
    if _first_match(title, GENERIC_QUALITY_TERMS):
        return True
    if _first_match(title, ["quality analyst", "quality engineer", "quality assurance", "software quality", "qa", "test", "testing", "validation engineer"]):
        return False
    return bool(_first_match(text, NON_SOFTWARE_QUALITY_CONTEXT))


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
