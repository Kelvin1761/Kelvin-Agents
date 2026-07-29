from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path


FIELD_TRAILER_RE = re.compile(
    r"\s*\|\s*負重:\s*(?:[0-9.]+kg|未知|N/A|-)\s*$"
)
HORSE_HEADER_RE = re.compile(
    r"^### 馬匹 #(\d+) (.+?) \(檔位 (\d+)\)"
    r"(?:\s*\| 騎師: ([^|]+?))?"
    r"(?:\s*\| 練馬師: ([^|\n\r]+?))?"
    r"(?:\s*\| 負重: (?:([0-9.]+)kg|未知|N/A|-))?$",
    re.M,
)
RACECARD_HORSE_RE = re.compile(r"^\d+\.\s+(.+?)\s+\((\d+)\)$")
RACECARD_META_RE = re.compile(
    r"^Trainer:\s.*?\|\sJockey:\s.*?\|\sWeight:\s*([0-9.]+)"
    r"(?:kg)?(?:\s*\([^|]*\))?\s*\|\sAge:\s.*?\|\sRating:\s*([0-9.]+)?"
)
RAW_HORSE_HEADER_RE = re.compile(r"^### 馬匹 #(\d+)\b", re.M)


def clean_identity(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return FIELD_TRAILER_RE.sub("", text).strip(" |")


def normalize_horse_name(name: object) -> str:
    without_suffix = re.sub(r"\s*\([^)]*\)", "", str(name or ""))
    return re.sub(r"[^a-z0-9]+", "", without_suffix.lower())


def validate_facts_horse_alignment(
    text: str,
    *,
    logic_horse_keys: Iterable[object] | None = None,
    source: str = "Facts.md",
) -> list[re.Match[str]]:
    matches = list(HORSE_HEADER_RE.finditer(text))
    raw_keys = [match.group(1) for match in RAW_HORSE_HEADER_RE.finditer(text)]
    parsed_keys = [match.group(1) for match in matches]
    errors: list[str] = []

    if not raw_keys:
        errors.append("no horse blocks found")
    if len(raw_keys) != len(parsed_keys):
        errors.append(
            f"{len(raw_keys)} horse blocks but only {len(parsed_keys)} parsed"
        )
    duplicate_keys = sorted(
        (key for key, count in Counter(parsed_keys).items() if count > 1),
        key=_horse_number_sort_key,
    )
    if duplicate_keys:
        errors.append(f"duplicate horse numbers {duplicate_keys}")

    if logic_horse_keys is not None:
        logic_keys = {str(key) for key in logic_horse_keys}
        facts_keys = set(parsed_keys)
        missing = sorted(facts_keys - logic_keys, key=_horse_number_sort_key)
        stale = sorted(logic_keys - facts_keys, key=_horse_number_sort_key)
        if missing:
            errors.append(f"Facts runners missing from Logic {missing}")
        if stale:
            errors.append(f"Logic runners absent from Facts {stale}")

    if errors:
        raise ValueError(f"FIELD ALIGNMENT FAILED in {source}: " + "; ".join(errors))
    return matches


def race_source_candidates(folder: Path, race_number: int, kind: str) -> list[Path]:
    patterns = (
        f"*Race {race_number} {kind}.md",
        f"*Race_{race_number}_{kind}.md",
    )
    matches = {
        path
        for pattern in patterns
        for path in folder.glob(pattern)
        if path.is_file()
    }
    return sorted(matches)


def venue_from_meeting_name(name: object) -> str:
    value = re.sub(
        r"^\d{4}-\d{2}-\d{2}[_\s-]*",
        "",
        str(name or ""),
    ).strip()
    value = value.replace("_", " ")
    value = re.sub(r"\bRace\s*\d+.*$", "", value, flags=re.I)
    return " ".join(value.strip(" _-").split())


def _horse_number_sort_key(value: object) -> tuple[int, str]:
    text = str(value)
    return (int(text), "") if text.isdigit() else (999, text)
