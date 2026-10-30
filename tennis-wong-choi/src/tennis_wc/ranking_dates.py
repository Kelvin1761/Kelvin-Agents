"""Calendar dates supplied by ranking sources, never invented from a request."""
from __future__ import annotations

from datetime import date, datetime, timezone
import re


class RankingDateError(ValueError):
    pass


def normalise_ranking_date(value) -> str | None:
    if not isinstance(value, (str, date)):
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def uts_source_date_issue(item):
    raw = item.get("raw") or {}
    if not isinstance(raw, dict):
        raw = {}
    if raw.get("source") != "ultimate_tennis_statistics" and not str(item.get("player_id", "")).startswith("uts:"):
        return None
    effective = normalise_ranking_date(raw.get("source_ranking_date"))
    if (effective is None or effective != normalise_ranking_date(item.get("ranking_date"))
            or raw.get("source_date_url") != "https://www.ultimatetennisstatistics.com/rankingsDate?rankType=RANK"
            or not re.fullmatch(r"[a-f0-9]{64}", str(raw.get("source_date_sha256", "")))):
        return "ranking_source_date_unverified"
    return None


def validate_ranking_rows(rows, requested_date=None, *, max_age_hours=None, today=None):
    """Return normalized copies; one invalid date rejects the whole source batch."""
    today = today or datetime.now(timezone.utc).date()
    requested = normalise_ranking_date(requested_date) if requested_date is not None else today.isoformat()
    if requested is None:
        raise RankingDateError(f"invalid requested ranking date: {requested_date!r}")
    reference = min(date.fromisoformat(requested), today)
    normalized, errors = [], []
    for index, row in enumerate(rows):
        effective = normalise_ranking_date(row.get("ranking_date"))
        if effective is None:
            errors.append(f"row {index}: missing/invalid source ranking date")
        elif date.fromisoformat(effective) > reference:
            errors.append(f"row {index}: source ranking date {effective} after {reference}")
        elif max_age_hours is not None and (reference-date.fromisoformat(effective)).days*24 > max_age_hours:
            errors.append(f"row {index}: stale source ranking date {effective} at {reference}")
        elif uts_source_date_issue(row):
            errors.append(f"row {index}: ranking_source_date_unverified")
        normalized.append({**row, "ranking_date": effective})
    if errors:
        raise RankingDateError(f"ranking source date rejected ({len(errors)}/{len(rows)} rows): {errors[0]}")
    return normalized
