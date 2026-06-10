from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from location_utils import is_ireland_relevant, normalize_ireland_location


def test_normalizes_ireland_county_codes_and_remote_context() -> None:
    assert normalize_ireland_location("Sligo, SO") == "Ireland / Sligo"
    assert normalize_ireland_location("Cork, CO") == "Ireland / Cork"
    assert normalize_ireland_location("Dublin / Remote") == "Ireland / Dublin"
    assert normalize_ireland_location("Remote Ireland") == "Ireland"


def test_rejects_non_ireland_location() -> None:
    assert not is_ireland_relevant("Manila")
    assert not is_ireland_relevant("London, United Kingdom")
