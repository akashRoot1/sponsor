from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceConfig:
    source_type: str
    endpoint: str = ""
    slug: str = ""
    host: str = ""
    tenant: str = ""
    site: str = ""


@dataclass(frozen=True)
class CompanyConfig:
    legal_name: str
    brand_name: str
    aliases: list[str]
    careers_url: str = ""
    sources: list[SourceConfig] = field(default_factory=list)
    priority: bool = False


@dataclass
class RawJob:
    company: str
    title: str
    location: str
    url: str
    source: str
    endpoint: str
    snippet: str = ""
    work_type: str = ""
    category: str = ""
    source_type: str = ""
    source_quality: str = "failed"


@dataclass
class JobResult:
    title: str
    company: str
    location: str
    url: str
    matching_keyword: str
    source: str
    date_found: str
    category: str
    work_type: str = ""
    score: int = 0
    accepted_reason: str = ""
    source_type: str = ""
    source_quality: str = ""

    @property
    def unique_id(self) -> str:
        raw = "|".join([_normalize_key(self.company), _normalize_key(self.title), _normalize_key(self.location), _normalize_key(self.url)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @property
    def dedupe_key(self) -> str:
        return "|".join([_normalize_key(self.company), _normalize_key(self.title), _normalize_key(self.location), _normalize_key(self.url)])


@dataclass
class RejectedJob:
    company: str
    title: str
    location: str
    url: str
    source: str
    reason: str
    matched_keyword: str = ""
    snippet: str = ""
    score: int = 0
    source_type: str = ""
    source_quality: str = ""


@dataclass
class SearchFailure:
    company: str
    source_type: str
    endpoint: str
    error: str
    http_status: int | None = None
    error_type: str = "api_failure"
    retry_count: int = 0
    timestamp: str = ""


@dataclass
class SourceStats:
    company: str
    aliases_used: list[str]
    source_type: str
    endpoint: str
    source_quality: str = "failed"
    raw_jobs_found: int = 0
    accepted_jobs: int = 0
    rejected_jobs: int = 0
    failed: bool = False
    error: str = ""
    error_type: str = ""
    retries_performed: int = 0
    api_failures: int = 0
    parsing_failures: int = 0
    timeout_failures: int = 0
    fallback_used: bool = False


@dataclass
class CompanySearchReport:
    company: str
    aliases_used: list[str]
    searched_successfully: bool = False
    missing_direct_source: bool = False
    accepted_jobs: list[JobResult] = field(default_factory=list)
    raw_jobs: list[RawJob] = field(default_factory=list)
    rejected_jobs: list[RejectedJob] = field(default_factory=list)
    failures: list[SearchFailure] = field(default_factory=list)
    source_stats: list[SourceStats] = field(default_factory=list)

    @property
    def had_failure(self) -> bool:
        return bool(self.failures or self.missing_direct_source)


@dataclass
class SearchReport:
    companies: list[CompanySearchReport]
    jobs: list[JobResult]
    duplicates_removed: list[JobResult] = field(default_factory=list)

    @property
    def raw_jobs(self) -> list[RawJob]:
        return [job for company in self.companies for job in company.raw_jobs]

    @property
    def rejected_jobs(self) -> list[RejectedJob]:
        return [job for company in self.companies for job in company.rejected_jobs]

    @property
    def failures(self) -> list[SearchFailure]:
        return [failure for company in self.companies for failure in company.failures]

    @property
    def successful_company_count(self) -> int:
        return sum(1 for company in self.companies if company.searched_successfully)

    @property
    def failed_company_count(self) -> int:
        return sum(1 for company in self.companies if company.had_failure)

    @property
    def partially_successful_company_count(self) -> int:
        return sum(1 for company in self.companies if company.searched_successfully and company.had_failure)

    @property
    def no_job_company_count(self) -> int:
        return sum(1 for company in self.companies if company.searched_successfully and not company.had_failure and not company.accepted_jobs)

    @property
    def source_health(self) -> list[SourceStats]:
        return [stats for company in self.companies for stats in company.source_stats]

    @property
    def retries_performed(self) -> int:
        return sum(stats.retries_performed for stats in self.source_health)

    @property
    def api_failure_count(self) -> int:
        return sum(stats.api_failures for stats in self.source_health)

    @property
    def parsing_failure_count(self) -> int:
        return sum(stats.parsing_failures for stats in self.source_health)

    @property
    def timeout_failure_count(self) -> int:
        return sum(stats.timeout_failures for stats in self.source_health)

    @property
    def fallback_fetch_count(self) -> int:
        return sum(1 for stats in self.source_health if stats.fallback_used)

    def artifacts(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        return (
            [asdict(job) for job in self.raw_jobs],
            [asdict(job) | {"unique_id": job.unique_id} for job in self.jobs],
            [asdict(job) for job in self.rejected_jobs],
            [asdict(failure) for failure in self.failures],
            [asdict(job) | {"unique_id": job.unique_id} for job in self.jobs],
            [asdict(job) | {"unique_id": job.unique_id} for job in self.duplicates_removed],
            [asdict(stats) for stats in self.source_health],
        )


def _normalize_key(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()
