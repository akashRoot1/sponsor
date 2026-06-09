from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable


LOGGER = logging.getLogger(__name__)


def load_seen_jobs(path: Path) -> set[str]:
    if not path.exists():
        return set()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("Could not parse %s; starting with an empty seen job list.", path)
        return set()

    if isinstance(data, list):
        return {str(item) for item in data}
    if isinstance(data, dict):
        return {str(item) for item in data.get("seen_urls", [])}
    return set()


def save_seen_jobs(path: Path, seen_urls: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_urls = sorted({url for url in seen_urls if url})
    path.write_text(json.dumps(clean_urls, indent=2) + "\n", encoding="utf-8")


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
