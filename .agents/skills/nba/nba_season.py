#!/usr/bin/env python3
"""Canonical six-stage NBA lifecycle classifier.

The public phase is intentionally separate from the legacy strategy phase so
existing scoring behaviour remains stable while operations gain explicit
off-season/preseason states.
"""
from __future__ import annotations

import json
from datetime import datetime
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
    path = Path(__file__).resolve().parent / "nba_wong_choi" / "resources" / "nba_season_config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _parse_date(value: Any) -> datetime:
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d")
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
