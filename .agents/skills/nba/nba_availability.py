"""Verified, short-lived availability kept separate from historical NBA statistics."""
from __future__ import annotations

import copy
import math
from datetime import datetime, timezone

from nba_identity import player_name_key
from nba_schedule import TEAM_ALIASES, canonical_team_abbr

MAX_AGE_SECONDS = 30 * 60  # operational refresh cadence, not a fitted model parameter


def classify_injury_status(status):
    text = str(status or "").strip().lower()
    if (text.startswith("out") or text in ("doubtful", "suspension", "suspended", "inactive", "not on verified roster")
            or "injured reserve" in text or text == "ir"):
        return "out"
    if text in ("day-to-day", "day to day", "dtd", "questionable", "game-time decision", "gtd"):
        return "dtd"
    return "ok"


def compute_usage_redistribution(players, team_abbr=None):
    """Preserve the allocation rule, funding it only from confirmed absences.

    USG values and bonuses are percentage points. Missing game history never
    establishes an injury; uncertain players neither fund nor receive a bonus.
    """
    active, absent_usg = [], 0.0
    for player in players:
        if player.get("roster_verified") is False:
            continue  # a waived/traded player is not an injured teammate
        value = (player.get("advanced") or {}).get("USG_PCT")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 < value <= 100:
            continue
        status = classify_injury_status(player.get("status"))
        if status == "out":
            absent_usg += value
        elif status == "ok":
            active.append((player, value))
    total = sum(value for _, value in active)
    if not absent_usg or not total:
        return {}
    return {player["name"]: {"original_USG": value, "bonus_USG": round(absent_usg * value / total, 1),
                             "projected_USG": round(value + absent_usg * value / total, 1),
                             "unit": "percentage_points"} for player, value in active}


def usage_from_injuries(players_by_team, injuries):
    result = {}
    for team, players in players_by_team.items():
        statuses = {player_name_key(name): status for name, status in injuries.get(team, {}).items()}
        current = [{**player, "status": statuses.get(player_name_key(player.get("name", "")), "Active")}
                   for player in players]
        if bonus := compute_usage_redistribution(current, team):
            result[team] = bonus
    return result


def usage_bonus_for(redistribution, team, name):
    key = player_name_key(name)
    matches = [value for player, value in redistribution.get(team, {}).items() if player_name_key(player) == key]
    return matches[0].get("bonus_USG", 0) if len(matches) == 1 else 0


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
        roster = {player_name_key(name) for name in maps[team].roster_names} if isinstance(maps[team], InjuryMap) else None
        for player in players:
            key = player_name_key(player.get("name", ""))
            if roster is not None:
                player["roster_verified"] = key in roster
            if roster is not None and key not in roster:
                player["status"] = "Not On Verified Roster"
                result["injuries"][team][player["name"]] = player["status"]
            else:
                player["status"] = statuses.get(key, "Active")
    result["usage_redistribution"] = {team: bonus for team, players in result.get("players", {}).items()
                                    if (bonus := compute_usage_redistribution(players, team))}
    return result


def _utc_now():
    return datetime.now(timezone.utc)


def refresh_availability(payload, *, fetch=fetch_team_availability, now=None):
    """Return a new verified payload. Caller atomically writes only on success."""
    started_at = now or _utc_now()
    meta = payload.get("meta", {})
    tip = aware_time(meta.get("date"))
    if tip is not None and tip <= started_at:
        raise AvailabilityUnavailable("game already started; availability refresh is forbidden")
    teams = [(meta.get(side) or {}).get("abbr") for side in ("away", "home")]
    if not all(teams) or len(set(teams)) != 2:
        raise AvailabilityUnavailable("game team identities missing")
    maps = {team: fetch(team) for team in teams}
    completed_at = now or _utc_now()
    if tip is not None and tip <= completed_at:
        raise AvailabilityUnavailable("game started during availability refresh")
    new = availability_metadata(maps)
    previous = meta.get("availability", {})
    if previous.get("rosters") != new.get("rosters"):
        raise RosterChanged("roster changed or never verified; full extraction required")
    result = apply_availability(payload, maps)
    if not availability_current(result, now=completed_at):
        raise AvailabilityUnavailable("availability response is stale or unverified")
    return result
