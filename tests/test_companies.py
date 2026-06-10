from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from companies import COMPANIES


def test_generic_company_careers_mappings_stay_below_threshold() -> None:
    counts = Counter(source.source_type for company in COMPANIES for source in company.sources)
    assert counts["company_careers"] < 20
    assert counts["company_careers"] == 0
    assert counts["company_custom"] > 0


def test_priority_companies_have_direct_non_search_sources() -> None:
    priority_companies = [company for company in COMPANIES if company.priority]
    assert priority_companies
    for company in priority_companies:
        source_types = {source.source_type for source in company.sources}
        assert "fallback_search" not in source_types
        assert source_types
