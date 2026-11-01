"""On-court lineups from ESPN play-by-play (2026-11-01).

Player offensive/defensive rating and on-court pace need to know which ten
players were on the floor for each possession. stats.nba.com computed them
from its own play-by-play; since it blocked this machine (2026-10-29) the
fields were ``None`` (``nba_espn_league.player_advanced``). ESPN's
``summary?event=`` carries the whole play-by-play with substitutions
(``participants``: [entering, leaving]), so the lineups can be rebuilt:

* Period 1 starts with the box score's five ``starter`` per team.
* Later periods: substitutions between periods are not logged. A player who
  acts in the period (any participant) or leaves it before he has entered it
  was on court at the start. Players who never act until they are subbed are
  found the same way; one who plays a whole period without touching the
  play log is carried over from the previous period's closing five.
  A period whose start cannot be resolved to exactly five a side is not used
  (its possessions are counted in ``quality``, never guessed).
* A possession ends on a made field goal (unless an and-one free throw
  follows), the last free throw of a trip, a defensive rebound, a turnover,
  or the end of a period -- the nba.com definition. Points and possessions
  are credited to the ten players on court at that moment.

Possession counting, not the box-score estimate, is what nba.com uses: team
totals land at 0.976 of ``FGA + 0.44 FTA - OREB + TOV``, and team ratings
within 0.8 of nba.com (median). Player parity against stored nba.com values
(EXP-20261101-01, held-out windows): DEF/OFF rating median |error| 1.5,
PACE 1.1, r 0.98; 0.9 for players with 100+ on-court minutes.

Every summary goes through ``nba_espn_http.get_json`` with ``fresh_after``
the closing time of its US day, so a finished game is fetched once, ever. The
compact per-game result is cached beside it (``lineups/<event>.json``).
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nba_schedule import canonical_team_abbr

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
US_EASTERN = ZoneInfo("America/New_York")
SOURCE = "espn_pbp"
PARSER_VERSION = 4
# nba.com credits players with ~1.6% more possessions than the ten on court at
# each possession end (team totals agree within 0.5 pace). Fitted on the
# 10-21..10-24 windows, checked on 10-25..10-27 (EXP-20261101-01). Crediting
# every player present during a possession over-shoots (-2.0 rating bias);
# crediting free-throw trips to the lineup at the foul changes nothing.
PLAYER_POSSESSION_SCALE = 1.016
# Actions that name players who need not be on court.
OFF_COURT_TYPES = re.compile(r"technical|ejection|timeout|challenge|review|delay|coach", re.I)
NON_TURNOVER_TYPES = re.compile(r"foul|kicked ball|jump ball|jumpball", re.I)
TURNOVER_WORDS = re.compile(r"turnover|traveling|double dribble|discontinued dribble|"
                            r"backcourt|back court|3-second|three second|5-second|8-second|"
                            r"shot clock|palming|offensive goaltending|lane violation turnover", re.I)
FREE_THROW = re.compile(r"free throw", re.I)
FT_OF = re.compile(r"(\d+)\s+of\s+(\d+)", re.I)
NO_POSSESSION_FT = re.compile(r"technical|flagrant|clear path|away from play", re.I)


def cache_root() -> Path:
    override = os.environ.get("WC_NBA_ESPN_LINEUP_DIR")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "wongchoi" / "espn_lineups"


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


def day_close(day: date) -> datetime:
    """06:00 US Eastern the next day: every game of ``day`` is final by then."""
    return datetime.combine(day + timedelta(days=1), datetime.min.time(), US_EASTERN) + timedelta(hours=6)


def fetch_summary(event_id: str, day: date, *, get=None) -> dict:
    """The raw summary; finished days are cached for good by ``nba_espn_http``."""
    import nba_espn_http
    url = f"{SITE}/summary?event={event_id}"
    if get is not None:
        return nba_espn_http.get_json(url, get=get, timeout=20)
    closes = day_close(day)
    fresh = closes if datetime.now(US_EASTERN) >= closes else None
    return nba_espn_http.get_json(url, timeout=20, fresh_after=fresh)


def espn_position(abbreviation) -> str:
    """ESPN position -> the one G/F/C scale (nba.com's 'G-F' style is not used)."""
    text = str(abbreviation or "").upper()
    if text in ("PG", "SG", "G"):
        return "G"
    if text in ("SF", "PF", "F"):
        return "F"
    return "C" if text == "C" else ""


def _clock_seconds(display, period: int) -> float:
    """Seconds elapsed in the period from ESPN's clock ('8:11' or '45.3')."""
    length = 720.0 if period <= 4 else 300.0
    text = str(display or "")
    try:
        if ":" in text:
            minutes, seconds = text.split(":", 1)
            remaining = 60 * int(minutes) + float(seconds)
        else:
            remaining = float(text)
    except ValueError:
        return 0.0
    return max(0.0, min(length, length - remaining))


def _participants(play) -> list[str]:
    return [str(((p or {}).get("athlete") or {}).get("id") or "") for p in play.get("participants") or []
            if ((p or {}).get("athlete") or {}).get("id")]


def _type(play) -> str:
    return str(((play.get("type") or {}).get("text")) or "")


def _is_turnover(play) -> bool:
    text = _type(play)
    return bool(TURNOVER_WORDS.search(text)) and not (NON_TURNOVER_TYPES.search(text)
                                                       and "turnover" not in text.lower())


def _free_throw(play):
    """(n, of) for a possession free throw, else None."""
    text = _type(play)
    if not FREE_THROW.search(text) or NO_POSSESSION_FT.search(text):
        return None
    match = FT_OF.search(text)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _period_starters(plays, team_of, previous_end, first_period_starters, period):
    """{team: set(five)} on court at the start of ``period``, or None per team if unresolved."""
    if period == 1:
        return {team: set(players) for team, players in first_period_starters.items()}
    found = {team: [] for team in first_period_starters}
    entered = set()
    for play in plays:
        ids = _participants(play)
        if _type(play) == "Substitution" and len(ids) >= 2:
            incoming, outgoing = ids[0], ids[1]
            team = team_of.get(outgoing)
            if team and outgoing not in entered and outgoing not in found[team]:
                found[team].append(outgoing)
            entered.add(incoming)
            continue
        if OFF_COURT_TYPES.search(_type(play)):
            continue
        for player in ids:
            team = team_of.get(player)
            if team and player not in entered and player not in found[team]:
                found[team].append(player)
    result = {}
    for team, players in found.items():
        lineup = set(players)
        if len(lineup) < 5:
            # Silent for a whole period: carry over from the previous closing five,
            # unless the play log shows him entering this period first.
            for player in sorted(previous_end.get(team) or ()):
                if len(lineup) == 5:
                    break
                if player not in entered:
                    lineup.add(player)
        result[team] = lineup if len(lineup) == 5 else None
    return result


def parse_game(payload: dict) -> dict | None:
    """Per-player on-court totals for one final game, plus parse quality.

    Returns ``{"teams": [a, b], "players": {espn_id: {...}}, "quality": {...}}``
    or None when the summary has no box score or no plays.
    """
    box = payload.get("boxscore") or {}
    plays = payload.get("plays") or []
    team_of, names, starters, id_to_abbr, positions = {}, {}, {}, {}, {}
    for side in box.get("players") or []:
        team = side.get("team") or {}
        abbr = canonical_team_abbr(team.get("abbreviation") or "")
        id_to_abbr[str(team.get("id") or "")] = abbr
        starters[abbr] = []
        for block in side.get("statistics") or []:
            for athlete in block.get("athletes") or []:
                person = athlete.get("athlete") or {}
                pid = str(person.get("id") or "")
                if not pid:
                    continue
                team_of[pid] = abbr
                names[pid] = str(person.get("displayName") or "")
                positions[pid] = espn_position((person.get("position") or {}).get("abbreviation"))
                if athlete.get("starter"):
                    starters[abbr].append(pid)
    if len(starters) != 2 or not plays:
        return None
    teams = sorted(starters)
    first = {team: players for team, players in starters.items()}
    quality = {"periods": 0, "bad_periods": [], "possessions": 0, "possessions_skipped": 0,
               "subs": 0, "subs_unmatched": 0, "starters_ok": all(len(v) == 5 for v in first.values())}

    def blank():
        return {"seconds": 0.0, "off_poss": 0, "def_poss": 0, "pts_for": 0, "pts_against": 0}
    totals: dict[str, dict] = {}
    by_period: dict[int, list] = {}
    for play in plays:
        by_period.setdefault(int(((play.get("period") or {}).get("number")) or 0), []).append(play)
    previous_end: dict[str, set] = {}
    for period in sorted(p for p in by_period if p > 0):
        quality["periods"] += 1
        period_plays = by_period[period]
        on = _period_starters(period_plays, team_of, previous_end, first, period)
        valid = all(on.get(team) for team in teams)
        if not valid:
            quality["bad_periods"].append(period)
        lineup = {team: set(on.get(team) or ()) for team in teams}
        last_clock = 0.0
        offense = None          # team holding the ball, if known
        pending_and_one = None  # team whose made FG may get an and-one
        for index, play in enumerate(period_plays):
            kind = _type(play)
            clock = _clock_seconds(((play.get("clock") or {}).get("displayValue")), period)
            if valid and clock > last_clock:
                for team in teams:
                    for player in lineup[team]:
                        totals.setdefault(player, blank())["seconds"] += clock - last_clock
            last_clock = max(last_clock, clock)
            actor = id_to_abbr.get(str(((play.get("team") or {}).get("id")) or ""))
            other = next((t for t in teams if t != actor), None) if actor else None
            ids = _participants(play)
            if kind == "Substitution" and len(ids) >= 2:
                quality["subs"] += 1
                incoming, outgoing = ids[0], ids[1]
                team = team_of.get(outgoing) or team_of.get(incoming)
                if team in lineup:
                    if outgoing in lineup[team] and incoming not in lineup[team]:
                        lineup[team].discard(outgoing)
                        lineup[team].add(incoming)
                    else:
                        quality["subs_unmatched"] += 1
                continue

            def end_possession(team):
                if team not in teams:
                    return
                quality["possessions"] += 1
                if not valid or any(len(lineup[t]) != 5 for t in teams):
                    quality["possessions_skipped"] += 1
                    return
                defence = next(t for t in teams if t != team)
                for player in lineup[team]:
                    totals.setdefault(player, blank())["off_poss"] += 1
                for player in lineup[defence]:
                    totals.setdefault(player, blank())["def_poss"] += 1

            points = int(play.get("scoreValue") or 0) if play.get("scoringPlay") else 0
            if points and actor in teams and valid and all(len(lineup[t]) == 5 for t in teams):
                for player in lineup[actor]:
                    totals.setdefault(player, blank())["pts_for"] += points
                for player in lineup[other]:
                    totals.setdefault(player, blank())["pts_against"] += points
            free_throw = _free_throw(play)
            if pending_and_one and ("foul" in kind.lower() or OFF_COURT_TYPES.search(kind)) \
                    and not FREE_THROW.search(kind):
                continue   # the and-one foul (or a timeout) sits between basket and free throw
            if pending_and_one and not (free_throw and free_throw == (1, 1) and actor == pending_and_one):
                end_possession(pending_and_one)
                offense = next((t for t in teams if t != pending_and_one), None)
            if pending_and_one and free_throw == (1, 1) and actor == pending_and_one:
                pending_and_one = None
                if points:
                    end_possession(actor)
                    offense = other
                continue
            pending_and_one = None
            if FREE_THROW.search(kind):
                if free_throw and free_throw[0] == free_throw[1] and points:
                    end_possession(actor)
                    offense = other
                continue
            if kind.lower().startswith("end period") or kind.lower().startswith("end game"):
                if offense:
                    end_possession(offense)
                offense = None
                continue
            if "defensive rebound" in kind.lower() and actor in teams:
                end_possession(other)
                offense = actor
            elif "offensive rebound" in kind.lower() and actor in teams:
                offense = actor
            elif _is_turnover(play) and actor in teams:
                end_possession(actor)
                offense = other
            elif play.get("shootingPlay") and actor in teams:
                offense = actor
                if points:
                    pending_and_one = actor
        if pending_and_one:
            end_possession(pending_and_one)
        previous_end = {team: set(players) for team, players in lineup.items()}
    players = {}
    for pid, row in totals.items():
        if pid not in team_of:
            continue
        players[pid] = {"name": names.get(pid, ""), "team": team_of[pid], "position": positions.get(pid, ""),
                        "minutes": round(row["seconds"] / 60, 2), **{k: row[k] for k in
                        ("off_poss", "def_poss", "pts_for", "pts_against")}}
    return {"teams": teams, "players": players, "quality": quality, "parser": PARSER_VERSION}


def game_lineups(event_id: str, day: date, *, get=None) -> dict | None:
    """``parse_game`` for one event, cached once the day is closed."""
    path = cache_root() / f"{event_id}.json"
    cached = _read(path)
    if cached is not None and cached.get("parser") == PARSER_VERSION:
        return cached
    game = parse_game(fetch_summary(event_id, day, get=get))
    if game is not None and datetime.now(US_EASTERN) >= day_close(day):
        _write(path, game)
    return game


def season_lineups(season: str, date_to, *, get=None, season_types=(2,)) -> list[dict]:
    """Parsed lineups of final games of ``season`` on or before ``date_to`` (US Eastern).

    Point-in-time by construction: the same day walk as
    ``nba_espn_league.season_games``.
    """
    import nba_espn_league
    last = nba_espn_league._window_day(date_to) if not isinstance(date_to, date) else date_to
    if last is None:
        return []
    day = date(int(str(season)[:4]), 10, 1)
    games = []
    while day <= last:
        for event in nba_espn_league._scoreboard_events(day, get=get):
            if event["season_type"] in season_types and event["final"]:
                game = game_lineups(event["id"], day, get=get)
                if game is not None:
                    games.append(game)
        day += timedelta(days=1)
    return games


def player_ratings(games: list[dict], name_to_nba_id: dict | None = None,
                   possession_scale: float = PLAYER_POSSESSION_SCALE) -> dict:
    """Season OFF/DEF/NET rating and on-court PACE per player (ratio of totals).

    Keyed by NBA PLAYER_ID when ``name_to_nba_id`` is given (unresolved names
    dropped, never guessed), else by ESPN athlete id.
    """
    from nba_identity import player_name_key
    acc: dict[str, dict] = {}
    for game in games:
        for pid, row in game["players"].items():
            item = acc.setdefault(pid, {"name": row["name"], "minutes": 0.0, "off_poss": 0,
                                        "def_poss": 0, "pts_for": 0, "pts_against": 0, "gp": 0})
            for key in ("minutes", "off_poss", "def_poss", "pts_for", "pts_against"):
                item[key] += row[key]
            item["gp"] += 1
    result = {}
    for pid, row in acc.items():
        key = pid
        if name_to_nba_id is not None:
            key = name_to_nba_id.get(player_name_key(row["name"]))
            if key is None:
                continue
        off_poss = row["off_poss"] * possession_scale
        def_poss = row["def_poss"] * possession_scale
        if off_poss <= 0 or def_poss <= 0 or row["minutes"] <= 0:
            continue
        off = 100 * row["pts_for"] / off_poss
        defence = 100 * row["pts_against"] / def_poss
        result[key] = {
            "OFF_RATING": round(off, 1),
            "DEF_RATING": round(defence, 1),
            "NET_RATING": round(off - defence, 1),
            "PACE": round(48 * (off_poss + def_poss) / 2 / row["minutes"], 2),
            "ON_COURT_POSS": round((off_poss + def_poss) / 2, 1),
            "ON_COURT_MIN": round(row["minutes"], 1),
            "source": SOURCE,
        }
    return result
