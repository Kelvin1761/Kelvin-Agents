#!/usr/bin/env python3
"""Canonical six-stage NBA lifecycle classifier.

The public phase is intentionally separate from the legacy strategy phase so
existing scoring behaviour remains stable while operations gain explicit
off-season/preseason states.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PUBLIC_PHASES = {
    "OFF_SEASON",
    "PRESEASON",
    "EARLY_REGULAR",
    "REGULAR_SEASON",
    "LATE_REGULAR",
    "POSTSEASON",
}
POSTSEASON_TYPES = {"PLAY_IN", "PLAYOFFS"}
LEGACY_PHASE_MAP = {
    "EARLY_SEASON": ("EARLY_REGULAR", None),
    "MID_SEASON": ("REGULAR_SEASON", None),
    "LATE_REGULAR": ("LATE_REGULAR", None),
    "PLAY_IN": ("POSTSEASON", "PLAY_IN"),
    "PLAYOFFS": ("POSTSEASON", "PLAYOFFS"),
}


def load_season_config() -> dict[str, Any]:
    """Hand-written fallback, used only when ESPN's calendar cannot be read."""
    path = Path(__file__).resolve().parent / "nba_wong_choi" / "resources" / "nba_season_config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ESPN publishes each season's official windows (core API season "types"). Times are
# US-midnight boundaries in UTC; a Sydney date D carries the US games of D - 1.
ESPN_TYPE_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/{year}/types/{type_id}"
ESPN_TYPES = {"preseason": 1, "regular": 2, "playoffs": 3, "play_in": 5}
EARLY_REGULAR_DAYS = 26     # first ~4 weeks of the regular season are EARLY_REGULAR
LATE_REGULAR_DAYS = 18      # last ~2.5 weeks are LATE_REGULAR
CALENDAR_MAX_AGE = timedelta(days=7)
_ESPN_MEMO: dict[int, dict[str, Any] | None] = {}


def _sydney_window(payload: dict[str, Any]) -> tuple[date, date]:
    """(first, last) Sydney game date of one ESPN season type."""
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo("America/New_York")
    parse = lambda text: datetime.fromisoformat(str(text).replace("Z", "+00:00"))  # noqa: E731
    first_us = (parse(payload["startDate"]) + timedelta(hours=12)).astimezone(eastern).date()
    last_us = (parse(payload["endDate"]) - timedelta(hours=12)).astimezone(eastern).date()
    return first_us + timedelta(days=1), last_us + timedelta(days=1)


def espn_season_config(day: datetime, *, get=None) -> dict[str, Any] | None:
    """Season dates from ESPN for the season ``day`` falls in, in the config's shape.

    Answers are cached on disk for a week (nba_espn_http) and per process. Returns
    None when ESPN cannot be read -- the caller then uses the hand-written config.
    Tests never reach the network unless they inject ``get``.
    """
    year = day.year + 1 if day.month >= 8 else day.year      # ESPN names a season by its end year
    if get is None and year in _ESPN_MEMO:
        return _ESPN_MEMO[year]
    if get is None and "pytest" in sys.modules:
        return None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from nba_espn_http import get_json
        windows = {}
        for name, type_id in ESPN_TYPES.items():
            payload = get_json(ESPN_TYPE_URL.format(year=year, type_id=type_id), get=get,
                               fresh_after=datetime.now(timezone.utc) - CALENDAR_MAX_AGE)
            windows[name] = _sydney_window(payload)
        regular_first, regular_last = windows["regular"]
        iso = lambda d: d.isoformat()  # noqa: E731
        config = {
            "season": f"{year - 1}-{str(year)[2:]}", "source": "espn_calendar",
            "preseason_start": iso(windows["preseason"][0]), "preseason_end": iso(windows["preseason"][1]),
            "regular_season_start": iso(regular_first), "regular_season_end": iso(regular_last),
            "early_regular_end": iso(regular_first + timedelta(days=EARLY_REGULAR_DAYS)),
            "late_regular_start": iso(regular_last - timedelta(days=LATE_REGULAR_DAYS)),
            "late_regular_end": iso(regular_last),
            "play_in_start": iso(windows["play_in"][0]), "play_in_end": iso(windows["play_in"][1]),
            "playoffs_start": iso(windows["playoffs"][0]), "playoffs_end": iso(windows["playoffs"][1]),
        }
    except Exception:  # noqa: BLE001 -- any ESPN failure falls back to the hand config
        config = None
    if get is None:
        _ESPN_MEMO[year] = config
    return config


def _parse_date(value: Any) -> datetime:
    """The Sydney date a value refers to. A tip-off timestamp ('2026-10-20T23:30Z', what
    the extractor passes) is converted; a plain date is already a Sydney target date."""
    text = str(value or "")
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        stamp = None
    if stamp is not None and stamp.tzinfo is not None:
        from zoneinfo import ZoneInfo
        local = stamp.astimezone(ZoneInfo("Australia/Sydney")).date()
        return datetime(local.year, local.month, local.day)
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return datetime.now()


def _metadata_phase(metadata: dict[str, Any]) -> tuple[str, str | None] | None:
    explicit = str(metadata.get("season_phase") or "").upper()
    subtype = str(metadata.get("postseason_type") or "").upper() or None
    if explicit in PUBLIC_PHASES:
        if explicit != "POSTSEASON":
            subtype = None
        elif subtype not in POSTSEASON_TYPES:
            subtype = "PLAYOFFS"
        return explicit, subtype
    if explicit in LEGACY_PHASE_MAP:
        return LEGACY_PHASE_MAP[explicit]

    meta_text = " ".join(
        str(metadata.get(key, ""))
        for key in (
            "season_type",
            "game_type",
            "game_status",
            "competition_type",
            "name",
            "short_name",
            "shortName",
            "series",
            "event_type",
            "season",
        )
    ).upper()
    if "PLAY-IN" in meta_text or "PLAY IN" in meta_text:
        return "POSTSEASON", "PLAY_IN"
    if "PLAYOFF" in meta_text or "POSTSEASON" in meta_text:
        return "POSTSEASON", "PLAYOFFS"
    if "PRESEASON" in meta_text or "PRE-SEASON" in meta_text:
        return "PRESEASON", None
    return None


def _phase_from_config(day: datetime, config: dict[str, Any]) -> tuple[str, str | None] | None:
    try:
        preseason_start = _parse_date(config["preseason_start"])
        preseason_end = _parse_date(config["preseason_end"])
        regular_start = _parse_date(config["regular_season_start"])
        early_end = _parse_date(config["early_regular_end"])
        late_start = _parse_date(config["late_regular_start"])
        regular_end = _parse_date(config["regular_season_end"])
        play_in_start = _parse_date(config["play_in_start"])
        play_in_end = _parse_date(config["play_in_end"])
        playoffs_start = _parse_date(config["playoffs_start"])
        playoffs_end = _parse_date(config["playoffs_end"])
    except KeyError:
        return None

    if day < preseason_start or day > playoffs_end:
        return None

    if preseason_start <= day <= preseason_end:
        return "PRESEASON", None
    if regular_start <= day <= early_end:
        return "EARLY_REGULAR", None
    if early_end < day < late_start:
        return "REGULAR_SEASON", None
    if late_start <= day <= regular_end:
        return "LATE_REGULAR", None
    if play_in_start <= day <= play_in_end:
        return "POSTSEASON", "PLAY_IN"
    if playoffs_start <= day <= playoffs_end:
        return "POSTSEASON", "PLAYOFFS"
    return "OFF_SEASON", None


def _generic_phase(day: datetime) -> tuple[str, str | None]:
    month, day_of_month = day.month, day.day
    if month == 10 and 3 <= day_of_month <= 19:
        return "PRESEASON", None
    if (month == 10 and day_of_month >= 20) or (month == 11 and day_of_month <= 15):
        return "EARLY_REGULAR", None
    if month in (11, 12, 1, 2) or (month == 3 and day_of_month <= 23):
        return "REGULAR_SEASON", None
    if (month == 3 and day_of_month >= 24) or (month == 4 and day_of_month <= 12):
        return "LATE_REGULAR", None
    if month == 4 and 13 <= day_of_month <= 18:
        return "POSTSEASON", "PLAY_IN"
    if (month == 4 and day_of_month >= 19) or month in (5, 6):
        return "POSTSEASON", "PLAYOFFS"
    return "OFF_SEASON", None


def strategy_phase(phase: str, postseason_type: str | None = None) -> str | None:
    if phase == "OFF_SEASON":
        return None
    if phase in {"PRESEASON", "EARLY_REGULAR"}:
        return "EARLY_SEASON"
    if phase == "REGULAR_SEASON":
        return "MID_SEASON"
    if phase == "LATE_REGULAR":
        return "LATE_REGULAR"
    return "PLAY_IN" if postseason_type == "PLAY_IN" else "PLAYOFFS"


def classify_nba_season(date_value: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    phase_info = _metadata_phase(metadata)
    source = "metadata"
    if phase_info is None:
        day = _parse_date(date_value)
        espn = espn_season_config(day)
        phase_info = _phase_from_config(day, espn) if espn else None
        source = "espn_calendar"
        if phase_info is None:
            phase_info = _phase_from_config(day, load_season_config())
            source = "season_config"
        if phase_info is None:
            phase_info = _generic_phase(day)
            source = "calendar_fallback"
    phase, postseason_type = phase_info
    mode = "dormant" if phase == "OFF_SEASON" else "shadow" if phase == "PRESEASON" else "production"
    return {
        "season_phase": phase,
        "postseason_type": postseason_type,
        "strategy_phase": strategy_phase(phase, postseason_type),
        "automation_mode": mode,
        "classification_source": source,
    }
