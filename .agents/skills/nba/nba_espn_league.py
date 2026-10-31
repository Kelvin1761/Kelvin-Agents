"""League tables computed from ESPN box scores (2026-10-31).

Team advanced stats (pace, offensive/defensive rating) and player advanced
stats (usage, true shooting, assist rate, PIE) exist on stats.nba.com only,
and stats.nba.com has refused this machine's scripted requests since
2026-10-29 21:00 -- every slate since went without analysis because the
extractor fails closed without them. Both tables are arithmetic on box-score
totals, which ESPN serves, so when nba.com is unreachable they are computed
here instead.

Two honest differences from nba.com, measured in EXP-20261031-01:

* nba.com counts possessions from play-by-play; here they are the standard
  box-score estimate ``FGA + 0.44*FTA - OREB + TOV``, which runs about 2%
  high against nba.com. ``POSSESSION_SCALE`` (0.98) was fitted on the
  10-22..10-24 windows and checked on 10-25..10-27: median |error| PACE 0.65,
  OFF/DEF rating 1.1 / 0.85, DEF_RANK 1 place (3.2 / 2.6 unscaled).
* nba.com's usage and assist rates use the team's numbers *while the player
  was on court*; a box score only has whole-game team totals.

Player OFF/DEF/NET rating and player PACE need on-court possessions, and PIE
did not reproduce (median |error| 4.5 points); all are left ``None`` --
nothing downstream reads them. Key defenders and team
defence-vs-position are tracking data with no ESPN equivalent; they are not
computed here.

Completed games never change, so every final box score and every closed
scoreboard day is cached on disk for good: after the first fill a run asks
ESPN only for the days it has not seen.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nba_schedule import canonical_team_abbr

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
US_EASTERN = ZoneInfo("America/New_York")
REGULAR_SEASON = 2
SOURCE = "espn_box"
POSSESSION_SCALE = 0.98


def cache_root() -> Path:
    override = os.environ.get("WC_NBA_ESPN_BOX_DIR")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "wongchoi" / "espn_box"


def _get_json(url, get=None, timeout=20):
    if get is None:
        import requests
        get = requests.get
    response = get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, payload) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass   # a cache must not break a run


def _window_day(date_to) -> date | None:
    """nba_api ``date_to_nullable`` ('MM/DD/YYYY') -> date."""
    try:
        return datetime.strptime(str(date_to), "%m/%d/%Y").date()
    except (TypeError, ValueError):
        return None


def _day_closed(day: date) -> bool:
    """Every game of ``day`` (US Eastern) is final: 06:00 ET the next day."""
    closes = datetime.combine(day + timedelta(days=1), datetime.min.time(),
                              US_EASTERN) + timedelta(hours=6)
    return datetime.now(US_EASTERN) >= closes


def _scoreboard_events(day: date, get=None) -> list[dict]:
    """[{id, season_type, final}] for one US date; cached once the day closes."""
    path = cache_root() / "scoreboard" / f"{day.isoformat()}.json"
    cached = _read(path)
    if cached is not None:
        return cached
    payload = _get_json(f"{SITE}/scoreboard?dates={day:%Y%m%d}&limit=50", get=get)
    events = []
    for event in payload.get("events") or []:
        status = ((event.get("status") or {}).get("type") or {})
        events.append({
            "id": str(event.get("id")),
            "season_type": int(((event.get("season") or {}).get("type")) or 0),
            "final": bool(status.get("completed")),
        })
    if _day_closed(day):
        _write(path, events)
    return events


def _split(value) -> tuple[float, float]:
    made, _, attempted = str(value or "0-0").partition("-")
    return float(made or 0), float(attempted or 0)


def _num(value) -> float:
    try:
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return 0.0


def parse_summary(payload: dict, day: date) -> dict | None:
    """One final game -> team totals and player lines, or None if incomplete."""
    box = payload.get("boxscore") or {}
    competition = ((payload.get("header") or {}).get("competitions") or [{}])[0]
    # The summary's status carries no period count; the line scores do (5+ = OT).
    periods = max([len(c.get("linescores") or []) for c in competition.get("competitors") or []]
                  + [int(((competition.get("status") or {}).get("period")) or 0), 4])
    team_minutes = 5 * (48 + 5 * max(periods - 4, 0))
    points = {}
    for competitor in competition.get("competitors") or []:
        abbr = canonical_team_abbr(((competitor.get("team") or {}).get("abbreviation")) or "")
        points[abbr] = _num(competitor.get("score"))
    teams, players = {}, []
    for side in box.get("players") or []:
        abbr = canonical_team_abbr(((side.get("team") or {}).get("abbreviation")) or "")
        block = (side.get("statistics") or [{}])[0]
        names = block.get("names") or block.get("labels") or []
        totals = dict.fromkeys(("FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB",
                                "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS"), 0.0)
        for athlete in block.get("athletes") or []:
            stats = dict(zip(names, athlete.get("stats") or []))
            if athlete.get("didNotPlay") or not stats.get("MIN"):
                continue
            line = {"MIN": _num(stats.get("MIN")), "PTS": _num(stats.get("PTS")),
                    "REB": _num(stats.get("REB")), "AST": _num(stats.get("AST")),
                    "TOV": _num(stats.get("TO")), "STL": _num(stats.get("STL")),
                    "BLK": _num(stats.get("BLK")), "OREB": _num(stats.get("OREB")),
                    "DREB": _num(stats.get("DREB")), "PF": _num(stats.get("PF"))}
            line["FGM"], line["FGA"] = _split(stats.get("FG"))
            line["FG3M"], line["FG3A"] = _split(stats.get("3PT"))
            line["FTM"], line["FTA"] = _split(stats.get("FT"))
            for key in totals:
                totals[key] += line[key]
            person = athlete.get("athlete") or {}
            players.append({"espn_id": str(person.get("id") or ""),
                            "name": str(person.get("displayName") or ""),
                            "team": abbr, **line})
        teams[abbr] = totals
    # Team-credited turnovers (shot clock, 8-second...) are in no player line
    # but are possessions: take the team's own total where ESPN gives it.
    for side in box.get("teams") or []:
        abbr = canonical_team_abbr(((side.get("team") or {}).get("abbreviation")) or "")
        stats = {item.get("name"): item.get("displayValue") for item in side.get("statistics") or []}
        if abbr in teams and stats.get("totalTurnovers") is not None:
            teams[abbr]["PLAYER_TOV"] = teams[abbr]["TOV"]
            teams[abbr]["TOV"] = _num(stats["totalTurnovers"])
    if len(teams) != 2 or set(teams) != set(points):
        return None
    for abbr, totals in teams.items():
        totals["PTS"] = points[abbr]
        totals["MIN"] = float(team_minutes)
    return {"date": day.isoformat(), "teams": teams, "players": players}


def _game(event_id: str, day: date, get=None) -> dict | None:
    path = cache_root() / "games" / f"{event_id}.json"
    cached = _read(path)
    if cached is not None:
        return cached
    game = parse_summary(_get_json(f"{SITE}/summary?event={event_id}", get=get), day)
    if game is not None:
        _write(path, game)
    return game


def season_games(season: str, date_to, *, get=None) -> list[dict]:
    """Final regular-season games of ``season`` ('2026-27') on or before ``date_to``.

    Point-in-time by construction: only US dates <= ``date_to`` are read, the
    same window the nba_api calls use.
    """
    last = _window_day(date_to)
    if last is None:
        return []
    day = date(int(str(season)[:4]), 10, 1)
    games = []
    while day <= last:
        for event in _scoreboard_events(day, get=get):
            if event["season_type"] == REGULAR_SEASON and event["final"]:
                game = _game(event["id"], day, get=get)
                if game is not None:
                    games.append(game)
        day += timedelta(days=1)
    return games


def possessions(team: dict) -> float:
    return POSSESSION_SCALE * (team["FGA"] + 0.44 * team["FTA"] - team["OREB"] + team["TOV"])


def team_advanced(games: list[dict]) -> dict:
    """``fetch_team_advanced_stats``-shaped table from box scores.

    Season ratios of totals, not means of per-game ratings, as nba.com does.
    """
    acc: dict[str, dict] = {}
    for game in games:
        (a, ta), (b, tb) = game["teams"].items()
        for abbr, own, opp in ((a, ta, tb), (b, tb, ta)):
            row = acc.setdefault(abbr, {"pts": 0.0, "opp_pts": 0.0, "poss": 0.0,
                                        "opp_poss": 0.0, "min": 0.0, "gp": 0})
            row["pts"] += own["PTS"]
            row["opp_pts"] += opp["PTS"]
            row["poss"] += possessions(own)
            row["opp_poss"] += possessions(opp)
            row["min"] += own["MIN"]
            row["gp"] += 1
    result = {}
    for abbr, row in acc.items():
        if row["poss"] <= 0 or row["opp_poss"] <= 0:
            continue
        off = 100 * row["pts"] / row["poss"]
        defence = 100 * row["opp_pts"] / row["opp_poss"]
        result[abbr] = {
            "name": abbr,
            "DEF_RATING": round(defence, 1),
            "OFF_RATING": round(off, 1),
            "PACE": round(48 * (row["poss"] + row["opp_poss"]) / (2 * row["min"] / 5), 2),
            "NET_RATING": round(off - defence, 1),
            "GP": row["gp"],
            "source": SOURCE,
        }
    for rank, abbr in enumerate(sorted(result, key=lambda k: result[k]["DEF_RATING"]), 1):
        result[abbr]["DEF_RANK"] = rank
    return result


def player_advanced(games: list[dict], name_to_nba_id: dict) -> dict:
    """``fetch_all_player_advanced_stats``-shaped table, keyed by NBA PLAYER_ID.

    A player whose ESPN name does not resolve to exactly one NBA id is left
    out rather than guessed.
    """
    from nba_identity import player_name_key
    acc: dict[str, dict] = {}
    for game in games:
        teams = game["teams"]
        for line in game["players"]:
            team = teams.get(line["team"])
            if team is None or line["MIN"] <= 0:
                continue
            row = acc.setdefault(line["espn_id"] or line["name"], {"name": line["name"], **{
                k: 0.0 for k in ("MIN", "PTS", "FGM", "FGA", "FG3M", "FTA", "TOV", "AST",
                                 "usage_den", "ast_den", "tm_min")}})
            for key in ("MIN", "PTS", "FGM", "FGA", "FG3M", "FTA", "TOV", "AST"):
                row[key] += line[key]
            row["tm_min"] += team["MIN"]
            row["usage_den"] += (team["FGA"] + 0.44 * team["FTA"] + team["TOV"]) * line["MIN"] / (team["MIN"] / 5)
            row["ast_den"] += line["MIN"] / (team["MIN"] / 5) * team["FGM"] - line["FGM"]
    result = {}
    for row in acc.values():
        nba_id = name_to_nba_id.get(player_name_key(row["name"]))
        if nba_id is None:
            continue
        shots = row["FGA"] + 0.44 * row["FTA"]
        result[nba_id] = {
            "USG_PCT": round(100 * (shots + row["TOV"]) / row["usage_den"], 1) if row["usage_den"] > 0 else 0.0,
            "TS_PCT": round(100 * row["PTS"] / (2 * shots), 1) if shots > 0 else 0.0,
            "OFF_RATING": None,
            "DEF_RATING": None,
            "NET_RATING": None,
            "PACE": None,
            "PIE": None,
            "AST_PCT": round(100 * row["AST"] / row["ast_den"], 1) if row["ast_den"] > 0 else 0.0,
            "EFG_PCT": round(100 * (row["FGM"] + 0.5 * row["FG3M"]) / row["FGA"], 1) if row["FGA"] > 0 else 0.0,
            "source": SOURCE,
        }
    return result


def nba_name_index() -> dict:
    """{player_name_key: NBA id} from nba_api's offline player list (no request).

    Names shared by two players map to nothing, so they are dropped, not guessed.
    """
    from nba_api.stats.static import players
    from nba_identity import player_name_key
    index: dict = {}
    for player in players.get_players():
        key = player_name_key(player["full_name"])
        index[key] = None if key in index else player["id"]
    return {key: value for key, value in index.items() if value is not None}
