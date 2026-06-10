from __future__ import annotations

import re


IRELAND_LOCATIONS = [
    ("dublin", "Dublin"),
    ("cork", "Cork"),
    ("galway", "Galway"),
    ("limerick", "Limerick"),
    ("waterford", "Waterford"),
    ("sligo", "Sligo"),
    ("mayo", "Mayo"),
    ("westport", "Westport"),
    ("donegal", "Donegal"),
    ("letterkenny", "Letterkenny"),
    ("athlone", "Athlone"),
    ("roscommon", "Roscommon"),
    ("leitrim", "Leitrim"),
    ("clare", "Clare"),
    ("ennis", "Ennis"),
    ("kerry", "Kerry"),
    ("tralee", "Tralee"),
    ("killarney", "Killarney"),
    ("kilkenny", "Kilkenny"),
    ("carlow", "Carlow"),
    ("wexford", "Wexford"),
    ("wicklow", "Wicklow"),
    ("kildare", "Kildare"),
    ("naas", "Naas"),
    ("meath", "Meath"),
    ("louth", "Louth"),
    ("dundalk", "Dundalk"),
    ("drogheda", "Drogheda"),
    ("monaghan", "Monaghan"),
    ("cavan", "Cavan"),
    ("longford", "Longford"),
    ("laois", "Laois"),
    ("offaly", "Offaly"),
    ("tipperary", "Tipperary"),
]

IRELAND_REGION_CODES = {
    "co": "Cork",
    "c": "Cork",
    "so": "Sligo",
    "g": "Galway",
    "lk": "Limerick",
    "d": "Dublin",
    "wd": "Waterford",
    "wh": "Westmeath",
}


def normalize_ireland_location(*parts: str) -> str:
    text = _normalize(" ".join(part for part in parts if part))
    if not text:
        return ""

    remote = bool(_first_match(text, ["remote", "hybrid"]))
    matched_locations = _matched_locations(text)
    region_location = _region_code_location(text)
    if region_location and region_location not in matched_locations:
        matched_locations.append(region_location)

    has_ireland = bool(_first_match(text, ["ireland", "ie", "irl", "remote ireland", "hybrid ireland", "ireland remote"]))
    if not matched_locations and not has_ireland:
        return ""

    if not matched_locations and has_ireland:
        matched_locations.append("Ireland")

    if remote and "Ireland" not in matched_locations and has_ireland:
        matched_locations.insert(0, "Ireland")

    return "Ireland / " + " / ".join(dict.fromkeys(location for location in matched_locations if location != "Ireland")) if any(location != "Ireland" for location in matched_locations) else "Ireland"


def is_ireland_relevant(*parts: str) -> bool:
    return bool(normalize_ireland_location(*parts))


def _matched_locations(text: str) -> list[str]:
    matches = []
    for term, label in IRELAND_LOCATIONS:
        if _first_match(text, [term]):
            matches.append(label)
    return list(dict.fromkeys(matches))


def _region_code_location(text: str) -> str:
    tokens = [token for token in re.split(r"[^a-z0-9]+", text) if token]
    for token in tokens:
        if token in IRELAND_REGION_CODES:
            return IRELAND_REGION_CODES[token]
    return ""


def _first_match(text: str, terms: list[str]) -> str:
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
            return term
    return ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()
