"""ESPN player endpoints: roster and game logs (ESPN is the only source).

Introduced 2026-10-30 as stand-ins while stats.nba.com (Akamai) blocked this
machine; since EXP-20261101-60 they are the only player feed, and players are
keyed by the ESPN athlete id everywhere.

Both helpers return the shapes the old nba_api calls returned:

* ``espn_roster(team)``      -> CommonTeamRoster-style rows; ``player_id`` is
  the ESPN athlete id (``player_id_source: espn``).
* ``espn_gamelog_frame(...)`` -> a PlayerGameLog DataFrame (GAME_DATE,
  MATCHUP, WL, PTS ... FTA, PLUS_MINUS), so ``fetch_player_gamelog`` keeps all
  of its own cut-off, dedup and L10 logic unchanged.

What ESPN does not have: PLUS_MINUS (written as 0; nothing downstream reads
it) and OREB/DREB (not used by the L10 record). Minutes are whole minutes, as
nba_api's PlayerGameLog MIN is. ``tests/test_espn_stats_parity`` pins the
numbers against nba_api-built packages.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nba_schedule import TEAM_ALIASES, canonical_team_abbr

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"
US_EASTERN = ZoneInfo("America/New_York")
_ESPN_TEAM = {canonical: alias for alias, canonical in TEAM_ALIASES.items()}

# nba_api season_type_all_star -> ESPN seasonTypes displayName suffix
_SEASON_TYPES = {
    "Regular Season": "Regular Season",
    "Playoffs": "Postseason",
    "Pre Season": "Preseason",
}
# One payload holds every season type, and nba_api asks per type (playoffs,
# regular season, then both again for the prior season): fetch it once per run.
_GAMELOG_CACHE: dict = {}
GAMELOG_COLUMNS = ("GAME_DATE", "MATCHUP", "WL", "MIN", "FGM", "FGA", "FG_PCT",
                   "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT", "REB",
                   "AST", "STL", "BLK", "TOV", "PF", "PTS", "PLUS_MINUS")


def _get_json(url, get=None, timeout=15, fresh_after=None):
    import nba_espn_http
    return nba_espn_http.get_json(url, get=get, timeout=timeout, fresh_after=fresh_after)


US_EASTERN = ZoneInfo("America/New_York")


def gamelog_fresh_after(espn_year: int, date_to=None, *, now=None):
    """Earliest fetch time whose game log already holds every game up to ``date_to``.

    A finished season (ESPN names it by the year it ends) is closed once the
    Finals are over; otherwise the window closes at 06:00 ET the day after
    ``date_to``. ``None`` = still open, do not reuse a cached copy.
    """
    now = now or datetime.now(US_EASTERN)
    season_end = datetime(espn_year, 7, 15, tzinfo=US_EASTERN)
    if now >= season_end:
        return season_end
    if date_to is None:
        return None
    closes = datetime(date_to.year, date_to.month, date_to.day, 6, tzinfo=US_EASTERN) + timedelta(days=1)
    return closes if now >= closes else None


def espn_season_year(nba_season: str) -> int:
    """'2026-27' -> 2027 (ESPN names a season by the year it ends)."""
    return int(str(nba_season)[:4]) + 1


def espn_roster(team_abbr: str, *, get=None):
    """ESPN team roster as CommonTeamRoster-style rows keyed by ESPN athlete id.

    ``experience`` is ``"R"`` for a rookie (0 years), as nba.com wrote it.
    """
    team = _ESPN_TEAM.get(canonical_team_abbr(team_abbr), team_abbr)
    payload = _get_json(f"{SITE}/teams/{team.lower()}/roster", get=get)
    rows = []
    for athlete in payload.get("athletes") or []:
        name = str(athlete.get("fullName") or athlete.get("displayName") or "").strip()
        if not name:
            continue
        espn_id = str(athlete.get("id") or "")
        if not espn_id:
            continue
        years = (athlete.get("experience") or {}).get("years", "")
        rows.append({
            "player_id": espn_id,
            "player_id_source": "espn",
            "espn_id": espn_id,
            "name": name,
            "position": ((athlete.get("position") or {}).get("abbreviation") or ""),
            "age": athlete.get("age", ""),
            "num": athlete.get("jersey", ""),
            "experience": "R" if years == 0 else str(years),
            "source": "espn",
        })
    return rows


def _split(text):
    made, _, attempted = str(text or "").partition("-")
    try:
        return int(made), int(attempted)
    except ValueError:
        return 0, 0


def _num(text, cast=int):
    try:
        return cast(float(text))
    except (TypeError, ValueError):
        return cast(0)


def _pct(made, attempted):
    return round(made / attempted, 3) if attempted else 0.0


def gamelog_rows(payload, season_type="Regular Season", date_to=None):
    """ESPN gamelog payload -> PlayerGameLog-style row dicts, newest first.

    ``date_to`` (a date) mirrors nba_api's ``date_to_nullable``: games on a
    later US date are dropped. GAME_DATE is the US Eastern calendar day, as
    nba.com reports it, never the UTC timestamp's day.
    """
    wanted = _SEASON_TYPES.get(season_type, season_type)
    names = payload.get("names") or []
    events = payload.get("events") or {}
    rows = []
    for block in payload.get("seasonTypes") or []:
        label = str(block.get("displayName") or "")
        # "2025-26 Play In Regular Season" also ends in "Regular Season", but
        # nba_api files Play-In under its own type and never in Regular Season
        # or Playoffs: counting it pulled April play-in games into the L10.
        if not label.endswith(wanted) or "play in" in label.lower():
            continue
        for category in block.get("categories") or []:
            for line in category.get("events") or []:
                meta = events.get(str(line.get("eventId"))) or {}
                stats = dict(zip(names, line.get("stats") or []))
                try:
                    played = datetime.fromisoformat(
                        str(meta["gameDate"]).replace("Z", "+00:00")).astimezone(US_EASTERN).date()
                except (KeyError, ValueError):
                    continue
                if date_to is not None and played > date_to:
                    continue
                team = canonical_team_abbr((meta.get("team") or {}).get("abbreviation"))
                opp = canonical_team_abbr((meta.get("opponent") or {}).get("abbreviation"))
                sep = "@" if meta.get("atVs") == "@" else "vs."
                fgm, fga = _split(stats.get("fieldGoalsMade-fieldGoalsAttempted"))
                tpm, tpa = _split(stats.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
                ftm, fta = _split(stats.get("freeThrowsMade-freeThrowsAttempted"))
                rows.append({
                    "GAME_DATE": played.strftime("%b %d, %Y").upper(),
                    "MATCHUP": f"{team} {sep} {opp}",
                    "WL": str(meta.get("gameResult") or ""),
                    "MIN": _num(stats.get("minutes")),
                    "FGM": fgm, "FGA": fga, "FG_PCT": _pct(fgm, fga),
                    "FG3M": tpm, "FG3A": tpa, "FG3_PCT": _pct(tpm, tpa),
                    "FTM": ftm, "FTA": fta, "FT_PCT": _pct(ftm, fta),
                    "REB": _num(stats.get("totalRebounds")),
                    "AST": _num(stats.get("assists")),
                    "STL": _num(stats.get("steals")),
                    "BLK": _num(stats.get("blocks")),
                    "TOV": _num(stats.get("turnovers")),
                    "PF": _num(stats.get("fouls")),
                    "PTS": _num(stats.get("points")),
                    "PLUS_MINUS": 0,
                    "_played_on": played,
                })
    rows.sort(key=lambda row: row["_played_on"], reverse=True)
    for row in rows:
        row.pop("_played_on")
    return rows


def espn_gamelog_frame(espn_id, nba_season, season_type="Regular Season",
                       date_to=None, *, get=None):
    """PlayerGameLog-shaped DataFrame from ESPN (empty frame = no games)."""
    import pandas as pd
    key = (str(espn_id), espn_season_year(nba_season))
    payload = _GAMELOG_CACHE.get(key) if get is None else None
    if payload is None:
        payload = _get_json(f"{WEB}/athletes/{key[0]}/gamelog?season={key[1]}", get=get,
                            fresh_after=gamelog_fresh_after(key[1], date_to))
        if get is None:
            _GAMELOG_CACHE[key] = payload
    rows = gamelog_rows(payload, season_type, date_to)
    return pd.DataFrame(rows, columns=list(GAMELOG_COLUMNS))
