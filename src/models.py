from __future__ import annotations

import hashlib
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

    @property
    def unique_id(self) -> str:
        raw = "|".join([self.company, self.title, self.location, self.url]).lower()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


@dataclass
class SearchFailure:
    company: str
    source_type: str
    endpoint: str
    error: str
    http_status: int | None = None


@dataclass
class SourceStats:
    company: str
    aliases_used: list[str]
    source_type: str
    endpoint: str
    raw_jobs_found: int = 0
    accepted_jobs: int = 0
    rejected_jobs: int = 0
    failed: bool = False
    error: str = ""


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
    def no_job_company_count(self) -> int:
        return sum(1 for company in self.companies if company.searched_successfully and not company.had_failure and not company.accepted_jobs)

    def artifacts(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        return (
            [asdict(job) for job in self.raw_jobs],
            [asdict(job) | {"unique_id": job.unique_id} for job in self.jobs],
            [asdict(job) for job in self.rejected_jobs],
            [asdict(failure) for failure in self.failures],
        )
