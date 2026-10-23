"""Verified, short-lived availability kept separate from historical NBA statistics."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from nba_identity import player_name_key
from nba_schedule import TEAM_ALIASES, canonical_team_abbr

MAX_AGE_SECONDS = 30 * 60  # operational refresh cadence, not a fitted model parameter


class AvailabilityUnavailable(RuntimeError):
    pass


class RosterChanged(AvailabilityUnavailable):
    pass


class InjuryMap(dict):
    """A verified injury response, including the full roster that established it."""

    def __init__(self, injuries, roster_names, captured_at):
        super().__init__(injuries)
        self.roster_names = roster_names
        self.captured_at = captured_at


def aware_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def fetch_team_availability(team, *, get=None, now=None):
    if get is None:
        import requests
        get = requests.get
    espn_alias = {canonical: alias for alias, canonical in TEAM_ALIASES.items()}
    source_team = espn_alias.get(canonical_team_abbr(team), team)
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{source_team}/roster"
    try:
        response = get(url, timeout=10)
        if response.status_code != 200:
            raise AvailabilityUnavailable(f"{team}: injury source HTTP {response.status_code}")
        athletes = response.json().get("athletes")
        if not isinstance(athletes, list) or len(athletes) < 5:
            raise AvailabilityUnavailable(f"{team}: incomplete roster response")
        names, injuries = [], {}
        for athlete in athletes:
            name = athlete.get("fullName")
            if not isinstance(name, str) or not player_name_key(name):
                raise AvailabilityUnavailable(f"{team}: player identity missing")
            names.append(player_name_key(name))
            entries = athlete.get("injuries", [])
            if not isinstance(entries, list):
                raise AvailabilityUnavailable(f"{team}: injury entries malformed")
            if entries:
                status = entries[0].get("status")
                if not isinstance(status, str) or not status.strip():
                    raise AvailabilityUnavailable(f"{team}: injury status missing for {name}")
                injuries[name] = status
        if len(set(names)) != len(names):
            raise AvailabilityUnavailable(f"{team}: ambiguous roster identities")
    except AvailabilityUnavailable:
        raise
    except Exception as exc:
        raise AvailabilityUnavailable(f"{team}: availability source failed: {type(exc).__name__}") from exc
    captured = now or datetime.now(timezone.utc)
    return InjuryMap(injuries, sorted(names), captured.isoformat())


def availability_metadata(maps):
    if len(maps) != 2 or not all(isinstance(value, InjuryMap) for value in maps.values()):
        return {"contract": 1, "status": "unverified"}
    return {"contract": 1, "status": "verified", "source": "ESPN team roster/injuries",
            "captured_at": min(value.captured_at for value in maps.values()),
            "rosters": {team: value.roster_names for team, value in maps.items()}}


def availability_current(payload, *, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        meta = payload["meta"]["availability"]
        captured = aware_time(meta["captured_at"])
        rosters = meta["rosters"]
        if (meta.get("contract") != 1 or meta.get("status") != "verified" or not captured
                or not isinstance(rosters, dict) or len(rosters) != 2):
            return False
        if any(not isinstance(names, list) or len(names) < 5 or len(set(names)) != len(names) for names in rosters.values()):
            return False
        if set(rosters) != set(payload.get("injuries", {})):
            return False
        if any(not isinstance(values, dict) for values in payload["injuries"].values()):
            return False
        teams = {(payload["meta"].get(side) or {}).get("abbr") for side in ("away", "home")}
        if None not in teams and teams != set(rosters):
            return False
        return 0 <= (now - captured).total_seconds() <= MAX_AGE_SECONDS
    except (KeyError, TypeError, ValueError):
        return False


def apply_availability(payload, maps):
    result = copy.deepcopy(payload)
    result["injuries"] = {team: dict(values) for team, values in maps.items()}
    result["meta"]["availability"] = availability_metadata(maps)
    for team, players in result.get("players", {}).items():
        statuses = {player_name_key(name): status for name, status in maps[team].items()}
        for player in players:
            player["status"] = statuses.get(player_name_key(player.get("name", "")), "Active")
    return result


def refresh_availability(payload, *, fetch=fetch_team_availability, now=None):
    """Return a new verified payload. Caller atomically writes only on success."""
    now = now or datetime.now(timezone.utc)
    meta = payload.get("meta", {})
    tip = aware_time(meta.get("date"))
    if tip is not None and tip <= now:
        raise AvailabilityUnavailable("game already started; availability refresh is forbidden")
    teams = [(meta.get(side) or {}).get("abbr") for side in ("away", "home")]
    if not all(teams) or len(set(teams)) != 2:
        raise AvailabilityUnavailable("game team identities missing")
    maps = {team: fetch(team) for team in teams}
    new = availability_metadata(maps)
    previous = meta.get("availability", {})
    if previous.get("rosters") != new.get("rosters"):
        raise RosterChanged("roster changed or never verified; full extraction required")
    result = apply_availability(payload, maps)
    if not availability_current(result, now=now):
        raise AvailabilityUnavailable("availability response is stale or unverified")
    return result
