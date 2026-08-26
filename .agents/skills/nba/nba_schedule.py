#!/usr/bin/env python3
"""Shared NBA schedule/date and team-tag normalization helpers."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from urllib import request
from zoneinfo import ZoneInfo


SYDNEY = ZoneInfo("Australia/Sydney")
ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
)
TEAM_ALIASES = {
    "GS": "GSW",
    "NO": "NOP",
    "NY": "NYK",
    "SA": "SAS",
    "UTAH": "UTA",
    "WSH": "WAS",
}


def canonical_team_abbr(value: object) -> str:
    abbreviation = str(value or "").strip().upper()
    return TEAM_ALIASES.get(abbreviation, abbreviation)


def canonical_game_tag(value: object) -> str:
    text = str(value or "").strip().upper().replace(" @ ", "_")
    text = text.replace("@", "_").replace(" ", "_")
    parts = [part for part in text.split("_") if part]
    if len(parts) != 2:
        return text
    return f"{canonical_team_abbr(parts[0])}_{canonical_team_abbr(parts[1])}"


def event_sydney_start(event: dict) -> datetime | None:
    raw = event.get("date")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(SYDNEY)


def event_sydney_date(event: dict) -> date | None:
    start = event_sydney_start(event)
    return start.date() if start is not None else None


def events_for_sydney_date(payload: dict, target_date: str) -> dict[str, datetime]:
    target = date.fromisoformat(target_date)
    events: dict[str, datetime] = {}
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        starts_at = event_sydney_start(event)
        if starts_at is None or starts_at.date() != target:
            continue
        competitions = event.get("competitions") or []
        if not competitions or not isinstance(competitions[0], dict):
            continue
        away = home = ""
        for competitor in competitions[0].get("competitors") or []:
            team = competitor.get("team") or {}
            abbreviation = canonical_team_abbr(team.get("abbreviation"))
            if competitor.get("homeAway") == "home":
                home = abbreviation
            elif competitor.get("homeAway") == "away":
                away = abbreviation
        if away and home:
            tag = f"{away}_{home}"
            current = events.get(tag)
            if current is None or starts_at < current:
                events[tag] = starts_at
    return events


def tags_for_sydney_date(payload: dict, target_date: str) -> set[str]:
    return set(events_for_sydney_date(payload, target_date))


def load_espn_events(
    target_date: str, *, timeout: int = 10
) -> tuple[dict[str, datetime], bool]:
    """Return exact Australia/Sydney game starts and source reachability.

    ESPN indexes by US date, so two adjacent indexes are queried. Every event
    is converted from its UTC start time and retained only when its Sydney date
    exactly matches ``target_date``.
    """
    target = date.fromisoformat(target_date)
    events: dict[str, datetime] = {}
    reachable = False
    for query_date in (target - timedelta(days=1), target):
        url = f"{ESPN_SCOREBOARD}?dates={query_date:%Y%m%d}"
        try:
            req = request.Request(
                url,
                headers={
                    "User-Agent": "curl/8.7.1",
                    "Accept": "application/json",
                },
            )
            with request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            continue
        reachable = True
        for tag, starts_at in events_for_sydney_date(payload, target_date).items():
            current = events.get(tag)
            if current is None or starts_at < current:
                events[tag] = starts_at
    return events, reachable


def load_espn_schedule(target_date: str, *, timeout: int = 10) -> tuple[set[str], bool]:
    """Backward-compatible tag-only schedule view."""
    events, reachable = load_espn_events(target_date, timeout=timeout)
    return set(events), reachable
