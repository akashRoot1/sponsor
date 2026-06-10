from __future__ import annotations

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from filters import evaluate_job
from models import RawJob


def test_known_missed_jobs_are_accepted() -> None:
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "known_missed_jobs.json"
    rows = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert rows

    for row in rows:
        decision = evaluate_job(
            RawJob(
                company=row["company"],
                title=row["title"],
                location=row["location"],
                url=row["url"],
                source=row.get("source", "fixture"),
                endpoint=row.get("endpoint", ""),
                snippet=row.get("description", ""),
                work_type=row.get("work_type", ""),
                category=row.get("category", ""),
                source_type="fixture",
                source_quality="fixture",
            )
        )
        assert decision.accepted, f"{row['company']} {row['title']} rejected as {decision.reason}"
