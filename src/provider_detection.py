from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProviderDetection:
    detected_provider: str
    confidence: int
    evidence: list[str]
    recommended_mapping: dict[str, str]

    def to_dict(self) -> dict:
        return asdict(self)


PROVIDER_PATTERNS = [
    ("workday", ["myworkdayjobs.com", "myworkdaysite.com", "/wday/cxs/"]),
    ("successfactors", ["successfactors.eu", "successfactors.com", "jobTitle-link", "tr data-row"]),
    ("phenom", ["phenompeople.com", "/widgets", "data-ph-at-id", "refineSearch"]),
    ("oracle_hcm", ["oraclecloud.com/hcmUI", "/hcmRestApi/", "CandidateExperience"]),
    ("eightfold", ["eightfold.ai", "static.vscdn.net", "pcsx"]),
    ("greenhouse", ["greenhouse.io", "boards.greenhouse.io", "boards-api.greenhouse.io", "gh_jid"]),
    ("lever", ["lever.co", "api.lever.co"]),
    ("ashby", ["ashbyhq.com", "api.ashbyhq.com"]),
    ("smartrecruiters", ["smartrecruiters.com", "api.smartrecruiters.com"]),
    ("icims", ["icims.com", "iCIMS"]),
    ("teamtailor", ["teamtailor.com"]),
    ("bamboohr", ["bamboohr.com"]),
    ("jobvite", ["jobvite.com", "jobs.jobvite.com"]),
    ("taleo", ["taleo.net", "taleo"]),
    ("personio", ["personio.com", "jobs.personio.com"]),
    ("recruitee", ["recruitee.com", "api/offers"]),
    ("pinpoint", ["pinpointhq.com", "pinpoint"]),
]


def detect_provider(url: str, html: str = "") -> ProviderDetection:
    haystack = f"{url}\n{html}".lower()
    evidence: list[str] = []
    provider_scores: dict[str, int] = {}
    for provider, patterns in PROVIDER_PATTERNS:
        if provider == "workday" and not _has_workday_signal(url, html):
            continue
        for pattern in patterns:
            if pattern.lower() in haystack:
                provider_scores[provider] = provider_scores.get(provider, 0) + 25
                evidence.append(f"{provider}: matched `{pattern}`")

    if not provider_scores:
        return ProviderDetection("unknown", 0, [], {})

    provider = max(provider_scores, key=provider_scores.get)
    confidence = min(provider_scores[provider], 95)
    return ProviderDetection(provider, confidence, evidence, _recommended_mapping(provider, url, html))


def _recommended_mapping(provider: str, url: str, html: str) -> dict[str, str]:
    parsed = urlparse(url)
    if provider == "workday":
        if "myworkdayjobs.com" in parsed.netloc:
            return {"source_type": "workday", "host": parsed.netloc, "tenant": parsed.netloc.split(".")[0], "site": parsed.path.strip("/").split("/")[0] if parsed.path.strip("/") else ""}
        link = _match_first(r"(https://[^\"'<\s]+?\.myworkdayjobs\.com/(?:en-US/)?[^\"'<\s/?#]+)", html)
        if link:
            linked = urlparse(link)
            path = linked.path.strip("/").split("/")
            site = path[-1] if path else ""
            return {"source_type": "workday", "host": linked.netloc, "tenant": linked.netloc.split(".")[0], "site": site}
        match = re.search(r"https://([^/\"'<\s]+)/(?:[^\"'<\s]+/)?recruiting/([^/]+)/([^/]+)/?", f"{url}\n{html}")
        if match:
            return {"source_type": "workday", "host": match.group(1), "tenant": match.group(2), "site": match.group(3)}
    if provider == "greenhouse":
        slug = _match_first(r"boards-api\.greenhouse\.io/v1/boards/([^/]+)/jobs|gh_jid", html)
        return {"source_type": "greenhouse", "slug": slug or ""}
    if provider == "oracle_hcm":
        site = _match_first(r"siteNumber:\s*'([^']+)'|sites/([^/'\"]+)", html) or parsed.path.strip("/").split("/")[-1]
        return {"source_type": "oracle_hcm", "host": parsed.netloc, "site": site}
    if provider == "phenom":
        return {"source_type": "phenom", "endpoint": f"{parsed.scheme}://{parsed.netloc}/widgets"}
    if provider in {"successfactors", "eightfold", "icims", "teamtailor", "bamboohr", "jobvite", "taleo", "personio", "recruitee", "pinpoint"}:
        return {"source_type": provider, "endpoint": url}
    return {"source_type": provider, "endpoint": url}


def _match_first(pattern: str, text: str) -> str:
    match = re.search(pattern, text or "", re.IGNORECASE)
    if not match:
        return ""
    for group in match.groups():
        if group:
            return group
    return match.group(0)


def _has_workday_signal(url: str, html: str) -> bool:
    text = f"{url}\n{html}"
    parsed = urlparse(url)
    if "myworkdayjobs.com" in parsed.netloc or "myworkdaysite.com" in parsed.netloc:
        return True
    return bool(
        re.search(r"https://[^\"'<\s]+\.myworkdayjobs\.com/[^\"'<\s]+", text, re.IGNORECASE)
        or re.search(r"/wday/cxs/[^\"'<\s]+", text, re.IGNORECASE)
        or re.search(r"/recruiting/[^\"'<\s]+/[^\"'<\s]+", text, re.IGNORECASE)
    )
