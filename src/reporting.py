from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from filters import evaluate_job
from models import CompanyConfig, RawJob, SearchReport
from provider_detection import detect_provider


WEAK_SOURCE_TYPES = {"company_careers", "company_custom", "fallback_search"}


def provider_detection_results(companies: list[CompanyConfig]) -> list[dict]:
    results = []
    for company in companies:
        detection = detect_provider(company.careers_url)
        configured = [source.source_type for source in company.sources]
        results.append(
            {
                "company": company.brand_name,
                "legal_name": company.legal_name,
                "careers_url": company.careers_url,
                "configured_sources": configured,
                **detection.to_dict(),
            }
        )
    return results


def missing_source_mappings(companies: list[CompanyConfig]) -> list[dict]:
    missing = []
    for company in companies:
        configured = [source.source_type for source in company.sources]
        detection = detect_provider(company.careers_url)
        weak_sources = [source_type for source_type in configured if source_type in WEAK_SOURCE_TYPES]
        if weak_sources or not configured:
            missing.append(
                {
                    "company": company.brand_name,
                    "legal_name": company.legal_name,
                    "careers_url": company.careers_url,
                    "configured_sources": configured,
                    "weak_sources": weak_sources,
                    "detected_provider": detection.detected_provider,
                    "confidence": detection.confidence,
                    "evidence": detection.evidence,
                    "recommended_mapping": detection.recommended_mapping,
                    "recommended_next_action": _next_action(configured, company.careers_url),
                }
            )
    return missing


def source_coverage(companies: list[CompanyConfig], report: SearchReport | None, generated_at: datetime) -> dict:
    provider_counts = Counter(source.source_type for company in companies for source in company.sources)
    by_provider: dict[str, list[str]] = defaultdict(list)
    for company in companies:
        for source in company.sources:
            by_provider[source.source_type].append(company.brand_name)

    source_health = [asdict(stats) for stats in report.source_health] if report else []
    stats_by_company = defaultdict(list)
    for stats in source_health:
        stats_by_company[stats["company"]].append(stats)

    companies_detail = []
    for company in companies:
        configured_sources = [source.source_type for source in company.sources]
        company_stats = stats_by_company.get(company.brand_name, [])
        companies_detail.append(
            {
                "company": company.brand_name,
                "legal_name": company.legal_name,
                "careers_url": company.careers_url,
                "configured_sources": configured_sources,
                "is_generic": "company_careers" in configured_sources,
                "is_weak_mapping": any(source_type in WEAK_SOURCE_TYPES for source_type in configured_sources),
                "source_health": company_stats,
                "raw_jobs_found_last_run": sum(stats.get("raw_jobs_found", 0) for stats in company_stats),
                "accepted_jobs_last_run": sum(stats.get("accepted_jobs", 0) for stats in company_stats),
                "last_successful_fetch": _last_success(company_stats),
                "failure_reason": _failure_reason(company_stats),
                "recommended_next_action": _next_action(configured_sources, company.careers_url),
            }
        )

    return {
        "generated_at": generated_at.isoformat(),
        "total_companies_configured": len(companies),
        "provider_counts": dict(provider_counts),
        "companies_by_provider": {provider: sorted(set(names)) for provider, names in sorted(by_provider.items())},
        "generic_company_count": provider_counts.get("company_careers", 0),
        "weak_mapping_count": sum(1 for company in companies if any(source.source_type in WEAK_SOURCE_TYPES for source in company.sources)),
        "blocked_company_count": sum(1 for stats in source_health if stats.get("status") == "blocked"),
        "invalid_url_company_count": sum(1 for stats in source_health if stats.get("status") == "invalid_url"),
        "limited_extraction_count": sum(1 for stats in source_health if stats.get("status") == "limited_extraction"),
        "companies": companies_detail,
    }


def provider_audit_markdown(coverage: dict, missing: list[dict]) -> str:
    lines = [
        "# Careers Provider Audit",
        "",
        f"Generated: {coverage['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Total companies configured: {coverage['total_companies_configured']}",
        f"- Generic `company_careers` entries: {coverage['generic_company_count']}",
        f"- Weak custom/fallback mappings: {coverage['weak_mapping_count']}",
        f"- Blocked sources last run: {coverage['blocked_company_count']}",
        f"- Invalid URLs last run: {coverage['invalid_url_company_count']}",
        f"- Limited extraction sources last run: {coverage['limited_extraction_count']}",
        "",
        "## Provider Counts",
        "",
        "| Provider | Company entries |",
        "| --- | ---: |",
    ]
    for provider, count in sorted(coverage["provider_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{provider}` | {count} |")

    lines.extend(["", "## Companies By Provider", ""])
    for provider, companies in coverage["companies_by_provider"].items():
        lines.append(f"### `{provider}`")
        lines.append(", ".join(companies) or "(none)")
        lines.append("")

    lines.extend(["## Remaining Generic / Weak Mappings", "", "| Company | Configured sources | Detected provider | Confidence | Recommended next action | URL |", "| --- | --- | --- | ---: | --- | --- |"])
    for item in missing:
        lines.append(f"| {item['company']} | `{', '.join(item['configured_sources'])}` | {item['detected_provider']} | {item['confidence']} | {item['recommended_next_action']} | {item['careers_url']} |")

    return "\n".join(lines).rstrip() + "\n"


def save_provider_audit(path: Path, coverage: dict, missing: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(provider_audit_markdown(coverage, missing), encoding="utf-8")


def known_missed_jobs_check(fixture_path: Path, generated_at: datetime) -> list[dict]:
    if not fixture_path.exists():
        return []
    with fixture_path.open("r", encoding="utf-8") as handle:
        rows = json.load(handle)
    results = []
    for row in rows:
        raw_job = RawJob(
            company=row.get("company", ""),
            title=row.get("title", ""),
            location=row.get("location", ""),
            url=row.get("url", ""),
            source=row.get("source", "known_missed_fixture"),
            endpoint=row.get("endpoint", ""),
            snippet=row.get("description", ""),
            work_type=row.get("work_type", ""),
            category=row.get("category", ""),
            source_type=row.get("source_type", "fixture"),
            source_quality=row.get("source_quality", "fixture"),
        )
        decision = evaluate_job(raw_job)
        results.append(
            {
                **row,
                "accepted": decision.accepted,
                "reason": decision.reason,
                "matched_keyword": decision.matched_keyword,
                "category": decision.category,
                "score": decision.score,
                "checked_at": generated_at.isoformat(),
            }
        )
    return results


def _last_success(stats: list[dict]) -> str:
    successful = [stat.get("last_checked_timestamp", "") for stat in stats if stat.get("status") == "success"]
    return max(successful) if successful else ""


def _failure_reason(stats: list[dict]) -> str:
    errors = [stat.get("error", "") for stat in stats if stat.get("error")]
    return errors[0] if errors else ""


def _next_action(configured_sources: list[str], careers_url: str) -> str:
    if not configured_sources:
        return "Add a source mapping."
    if "company_careers" in configured_sources:
        detection = detect_provider(careers_url)
        if detection.detected_provider != "unknown":
            return f"Verify and convert to `{detection.detected_provider}`."
        return "Manually inspect for custom API or provider scripts."
    if "company_custom" in configured_sources:
        detection = detect_provider(careers_url)
        if detection.detected_provider != "unknown":
            return f"Replace custom scraper with `{detection.detected_provider}` parser after endpoint verification."
        return "Custom public careers page; inspect browser network for a stable public jobs API."
    if "fallback_search" in configured_sources:
        return "Find a direct public careers provider; search fallback should remain last resort."
    return "Mapped to direct provider."
