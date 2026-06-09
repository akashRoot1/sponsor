from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable
import re

import requests

from filters import evaluate_job, normalize_dedupe_value
from models import CompanyConfig, CompanySearchReport, JobResult, RejectedJob, SearchFailure, SearchReport, SourceStats
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


def _search_company(session, company: CompanyConfig, generated_at: datetime) -> CompanySearchReport:
    report = CompanySearchReport(company=company.brand_name, aliases_used=company.aliases)
    if not company.sources:
        report.missing_direct_source = True
        report.failures.append(SearchFailure(company.brand_name, "missing_direct_source", company.careers_url, "No direct source configured."))
        return report

    for source in company.sources:
        endpoint = source_endpoint(source)
        stats = SourceStats(company=company.brand_name, aliases_used=company.aliases, source_type=source.source_type, endpoint=endpoint, source_quality=source_quality(source.source_type))
        try:
            raw_jobs = fetch_jobs(session, company, source)
            stats.raw_jobs_found = len(raw_jobs)
            report.raw_jobs.extend(raw_jobs)
            for raw_job in raw_jobs:
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
                else:
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
                    LOGGER.info("Rejected job company=%s source=%s title=%s reason=%s", company.brand_name, raw_job.source, raw_job.title, decision.reason)
            report.searched_successfully = True
            LOGGER.info(
                "Source summary company=%s source=%s endpoint=%s raw=%s accepted=%s rejected=%s",
                company.brand_name,
                source.source_type,
                endpoint,
                stats.raw_jobs_found,
                stats.accepted_jobs,
                stats.rejected_jobs,
            )
        except SourceError as exc:
            stats.failed = True
            stats.error = str(exc)
            report.failures.append(SearchFailure(company.brand_name, source.source_type, endpoint, str(exc), exc.http_status))
            LOGGER.warning("Source failure company=%s source=%s endpoint=%s status=%s error=%s", company.brand_name, source.source_type, endpoint, exc.http_status, exc)
        except requests.Timeout as exc:
            stats.failed = True
            stats.error = f"timeout: {exc}"
            report.failures.append(SearchFailure(company.brand_name, source.source_type, endpoint, f"timeout: {exc}"))
            LOGGER.warning("Source timeout company=%s source=%s endpoint=%s error=%s", company.brand_name, source.source_type, endpoint, exc)
        except Exception as exc:
            stats.failed = True
            stats.error = str(exc)
            report.failures.append(SearchFailure(company.brand_name, source.source_type, endpoint, str(exc)))
            LOGGER.warning("Source failure company=%s source=%s endpoint=%s error=%s", company.brand_name, source.source_type, endpoint, exc)
        finally:
            report.source_stats.append(stats)

    report.accepted_jobs, _ = _dedupe_jobs(report.accepted_jobs)
    return report


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
