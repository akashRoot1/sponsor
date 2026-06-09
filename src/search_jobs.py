from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Iterable

import requests

from filters import evaluate_job, normalize_dedupe_value
from models import CompanyConfig, CompanySearchReport, JobResult, RejectedJob, SearchFailure, SearchReport, SourceConfig, SourceStats
from sources import SourceError, fetch_jobs, new_session, source_endpoint, source_quality


LOGGER = logging.getLogger(__name__)


def find_jobs(companies: Iterable[CompanyConfig], generated_at: datetime) -> SearchReport:
    session = new_session()
    company_reports: list[CompanySearchReport] = []
    all_jobs: list[JobResult] = []

    for index, company in enumerate(companies, start=1):
        LOGGER.info("Searching company=%s brand=%s aliases=%s index=%s", company.legal_name, company.brand_name, company.aliases, index)
        report = _search_company(session, company, generated_at)
        company_reports.append(report)
        all_jobs.extend(report.accepted_jobs)
        LOGGER.info(
            "Company summary company=%s raw=%s accepted=%s rejected=%s failures=%s success=%s",
            company.brand_name,
            len(report.raw_jobs),
            len(report.accepted_jobs),
            len(report.rejected_jobs),
            len(report.failures),
            report.searched_successfully,
        )

    unique_jobs, duplicates_removed = _dedupe_jobs(all_jobs)
    return SearchReport(company_reports, unique_jobs, duplicates_removed)


def _search_company(session: requests.Session, company: CompanyConfig, generated_at: datetime) -> CompanySearchReport:
    report = CompanySearchReport(company=company.brand_name, aliases_used=company.aliases)
    if not company.sources:
        report.missing_direct_source = True
        report.failures.append(_failure(company, SourceConfig("missing_direct_source", endpoint=company.careers_url), "No direct source configured.", generated_at))
        return report

    for source in company.sources:
        stats = _run_source(session, company, source, generated_at, report)
        report.source_stats.append(stats)
        if stats.failed and company.careers_url and source.source_type != "company_careers":
            fallback = SourceConfig("company_careers", endpoint=company.careers_url)
            LOGGER.info("Trying fallback careers page company=%s after source=%s failed", company.brand_name, source.source_type)
            fallback_stats = _run_source(session, company, fallback, generated_at, report, fallback_used=True)
            report.source_stats.append(fallback_stats)

    report.accepted_jobs, _ = _dedupe_jobs(report.accepted_jobs)
    return report


def _run_source(
    session: requests.Session,
    company: CompanyConfig,
    source: SourceConfig,
    generated_at: datetime,
    report: CompanySearchReport,
    fallback_used: bool = False,
) -> SourceStats:
    endpoint = source_endpoint(source)
    stats = SourceStats(
        company=company.brand_name,
        aliases_used=company.aliases,
        source_type=source.source_type,
        endpoint=endpoint,
        source_quality=source_quality(source.source_type),
        fallback_used=fallback_used,
    )
    try:
        raw_jobs = fetch_jobs(session, company, source)
        stats.raw_jobs_found = len(raw_jobs)
        report.raw_jobs.extend(raw_jobs)
        for raw_job in raw_jobs:
            _record_job(raw_job, company, generated_at, report, stats)
        report.searched_successfully = True
        LOGGER.info(
            "Source summary company=%s source=%s endpoint=%s raw=%s accepted=%s rejected=%s fallback=%s",
            company.brand_name,
            source.source_type,
            endpoint,
            stats.raw_jobs_found,
            stats.accepted_jobs,
            stats.rejected_jobs,
            fallback_used,
        )
    except SourceError as exc:
        _mark_source_failure(stats, exc.error_type, str(exc), exc.retry_count)
        report.failures.append(_failure(company, source, str(exc), generated_at, exc.http_status, exc.error_type, exc.retry_count))
        LOGGER.warning("Source failure company=%s source=%s endpoint=%s status=%s error_type=%s retries=%s error=%s", company.brand_name, source.source_type, endpoint, exc.http_status, exc.error_type, exc.retry_count, exc)
    except requests.Timeout as exc:
        _mark_source_failure(stats, "timeout_failure", f"timeout_failure: {exc}", 0)
        report.failures.append(_failure(company, source, f"timeout_failure: {exc}", generated_at, None, "timeout_failure", 0))
        LOGGER.warning("Source timeout company=%s source=%s endpoint=%s error=%s", company.brand_name, source.source_type, endpoint, exc)
    except requests.RequestException as exc:
        _mark_source_failure(stats, "network_failure", f"network_failure: {exc}", 0)
        report.failures.append(_failure(company, source, f"network_failure: {exc}", generated_at, None, "network_failure", 0))
        LOGGER.warning("Source network failure company=%s source=%s endpoint=%s error=%s", company.brand_name, source.source_type, endpoint, exc)
    except Exception as exc:
        _mark_source_failure(stats, "unexpected_failure", str(exc), 0)
        report.failures.append(_failure(company, source, str(exc), generated_at, None, "unexpected_failure", 0))
        LOGGER.warning("Source failure company=%s source=%s endpoint=%s error=%s", company.brand_name, source.source_type, endpoint, exc)
    return stats


def _record_job(raw_job, company: CompanyConfig, generated_at: datetime, report: CompanySearchReport, stats: SourceStats) -> None:
    decision = evaluate_job(raw_job)
    if decision.accepted:
        stats.accepted_jobs += 1
        report.accepted_jobs.append(
            JobResult(
                title=raw_job.title,
                company=company.brand_name,
                location=raw_job.location,
                url=raw_job.url,
                matching_keyword=decision.matched_keyword,
                source=raw_job.source,
                date_found=generated_at.strftime("%Y-%m-%d"),
                category=decision.category,
                work_type=raw_job.work_type,
                score=decision.score,
                accepted_reason=decision.reason,
                source_type=raw_job.source_type,
                source_quality=raw_job.source_quality,
            )
        )
        return

    stats.rejected_jobs += 1
    report.rejected_jobs.append(
        RejectedJob(
            company=company.brand_name,
            title=raw_job.title,
            location=raw_job.location,
            url=raw_job.url,
            source=raw_job.source,
            reason=decision.reason,
            matched_keyword=decision.matched_keyword,
            snippet=raw_job.snippet[:800],
            score=decision.score,
            source_type=raw_job.source_type,
            source_quality=raw_job.source_quality,
        )
    )
    LOGGER.info("Rejected job company=%s source=%s title=%s reason=%s score=%s", company.brand_name, raw_job.source, raw_job.title, decision.reason, decision.score)


def _mark_source_failure(stats: SourceStats, error_type: str, error: str, retries: int) -> None:
    stats.failed = True
    stats.error = error
    stats.error_type = error_type
    stats.retries_performed = retries
    if error_type in {"timeout_failure", "network_failure"}:
        stats.timeout_failures = 1
    elif error_type == "parsing_failure":
        stats.parsing_failures = 1
    else:
        stats.api_failures = 1


def _failure(
    company: CompanyConfig,
    source: SourceConfig,
    error: str,
    generated_at: datetime,
    http_status: int | None = None,
    error_type: str = "api_failure",
    retry_count: int = 0,
) -> SearchFailure:
    return SearchFailure(
        company=company.brand_name,
        source_type=source.source_type,
        endpoint=source_endpoint(source),
        error=error,
        http_status=http_status,
        error_type=error_type,
        retry_count=retry_count,
        timestamp=generated_at.isoformat(),
    )


def _dedupe_jobs(jobs: list[JobResult]) -> tuple[list[JobResult], list[JobResult]]:
    seen = set()
    unique = []
    duplicates = []
    for job in jobs:
        key = _job_dedupe_key(job)
        if key in seen:
            duplicates.append(job)
            continue
        seen.add(key)
        unique.append(job)
    return unique, duplicates


def _job_dedupe_key(job: JobResult) -> str:
    return "|".join(
        [
            normalize_dedupe_value(job.company),
            _normalize_title_for_dedupe(job.title),
            normalize_dedupe_value(job.location),
        ]
    )


def _normalize_title_for_dedupe(title: str) -> str:
    title = normalize_dedupe_value(title)
    title = re.sub(r"\bii\s+bilingual\b", "ii bilingual", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()
