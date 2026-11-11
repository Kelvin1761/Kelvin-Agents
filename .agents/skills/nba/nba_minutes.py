"""Minutes model v2 (EXP-20261111-03): the pre-game facts and the fitted adjustment.

The price-free model S projects minutes with a half-life-3 weighted average of the player's
own games. v2 keeps that as its base and corrects it with what is known before the game:

  rest      back-to-back, more than 7 days since the player's last game, missed the team's last game
  spread    the pre-game handicap (starters lose minutes in lopsided games, the bench gains)
  role      started the previous game / share of the last five games started
  absences  minutes of regulars who missed the team's previous game

Every feature uses games strictly before the game's US date. The coefficients were fitted on
the first 60% of the 2025-26 regular season and are frozen in nba_engine/config.json
(`minutes_v2`). This is a SHADOW input: it feeds `p_s2`, never `p_final`.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path

HALF_LIFE = 3.0
MIN_GAMES = 5            # the fitted population: at least five games this season ...
MIN_BASE = 15.0          # ... and a base projection of at least 15 minutes
STARTER, BENCH = 28.0, 22.0
REGULAR_MINUTES, REGULAR_GAMES, REGULAR_DAYS = 15.0, 3, 14
RATIO_CLIP = (0.5, 1.6)
FEATURE_NAMES = (
    "const", "m_hl", "season_minus_hl", "last_minus_hl", "l10_minus_hl", "over_32",
    "b2b", "b2b_starter", "gap_over_7", "missed_prev",
    "spread_starter", "spread_bench", "spread", "spread_over_8_starter", "favourite_spread_starter",
    "started_prev", "start_share", "role_change",
    "pool_prev", "pool_prev_bench",
)


def _starters_path(event_id: str) -> Path:
    import nba_espn_league
    return nba_espn_league.cache_root() / "starters" / f"{event_id}.json"


def starters(event_id: str, day: date, *, get=None) -> set[str]:
    """ESPN athlete ids that started one final game; cached for good once read."""
    path = _starters_path(str(event_id))
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    import nba_espn_lineups
    summary = nba_espn_lineups.fetch_summary(str(event_id), day, get=get)
    found = sorted({str((a.get("athlete") or {}).get("id") or "")
                    for side in (summary.get("boxscore") or {}).get("players") or []
                    for a in ((side.get("statistics") or [{}])[0].get("athletes") or [])
                    if a.get("starter")} - {""})
    if found:                       # a summary with no starters is not a final box score: do not cache it
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".tmp{os.getpid()}")
            tmp.write_text(json.dumps(found), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass
    return set(found)


def team_features(games: list[dict], team: str, game_day: date, starters_of) -> dict[str, dict]:
    """{espn_id: features} for every player of `team` with enough history before `game_day`.

    `games` are `nba_espn_league.season_games` rows of the current season; `starters_of(game)`
    returns the set of ids that started that game.
    """
    past = sorted((g for g in games if date.fromisoformat(g["date"]) < game_day),
                  key=lambda g: (g["date"], str(g.get("event_id"))))
    history = defaultdict(list)                 # id -> [(day, team, minutes, started)], oldest first
    team_games = []                             # [(day, {ids that played})]
    for game in past:
        started = None
        played = set()
        for p in game["players"]:
            if not p.get("espn_id") or p["MIN"] <= 0:
                continue
            if started is None:
                started = starters_of(game)
            history[p["espn_id"]].append((game["date"], p["team"], p["MIN"], p["espn_id"] in started))
            if p["team"] == team:
                played.add(p["espn_id"])
        if team in game["teams"]:
            team_games.append((game["date"], played))
    previous = team_games[-1] if team_games else None

    def team_average(pid):
        mins = [m for _, t, m, _ in history[pid][-10:] if t == team]
        return sum(mins) / len(mins) if len(mins) >= REGULAR_GAMES else 0.0

    pool_prev = 0.0
    if previous is not None:
        prev_day = date.fromisoformat(previous[0])
        for pid, rows in history.items():
            if (rows[-1][1] == team and team_average(pid) >= REGULAR_MINUTES
                    and (prev_day - date.fromisoformat(rows[-1][0])).days <= REGULAR_DAYS
                    and pid not in previous[1]):
                pool_prev += team_average(pid)

    out = {}
    for pid, rows in history.items():
        if rows[-1][1] != team or len(rows) < MIN_GAMES:
            continue
        mins = [r[2] for r in rows][::-1]       # newest first
        weights = [0.5 ** (i / HALF_LIFE) for i in range(len(mins))]
        last_five = [r[3] for r in rows][-5:]
        out[pid] = {
            "m_hl": sum(w * m for w, m in zip(weights, mins)) / sum(weights),
            "m_season": sum(mins) / len(mins), "m_l10": sum(mins[:10]) / len(mins[:10]), "m_last": mins[0],
            "games": len(mins), "started_prev": bool(rows[-1][3]),
            "start_share": sum(last_five) / len(last_five),
            "rest": (game_day - date.fromisoformat(previous[0])).days if previous else 9,
            "gap_last": (game_day - date.fromisoformat(rows[-1][0])).days,
            "missed_prev": previous is not None and pid not in previous[1],
            "pool_prev": pool_prev,
        }
    return out


def feature_vector(f: dict, spread: float, favourite: bool) -> list[float]:
    starter = 1.0 if f["m_hl"] >= STARTER else 0.0
    bench = 1.0 if f["m_hl"] < BENCH else 0.0
    sp = min(abs(float(spread)), 16.0)
    b2b = 1.0 if f["rest"] == 1 else 0.0
    started = 1.0 if f["started_prev"] else 0.0
    return [
        1.0, f["m_hl"], f["m_season"] - f["m_hl"], f["m_last"] - f["m_hl"], f["m_l10"] - f["m_hl"],
        max(f["m_hl"] - 32.0, 0.0),
        b2b, b2b * starter, 1.0 if f["gap_last"] > 7 else 0.0, 1.0 if f["missed_prev"] else 0.0,
        sp * starter, sp * bench, sp, max(sp - 8.0, 0.0) * starter, (1.0 if favourite else 0.0) * sp * starter,
        started, f["start_share"], started - f["start_share"],
        f["pool_prev"], f["pool_prev"] * bench,
    ]


def minutes_ratio(f: dict | None, spread, favourite: bool, coefficients: list[float]) -> float | None:
    """v2 minutes / base minutes, or None when the player is outside the fitted population."""
    if not f or spread is None or f.get("games", 0) < MIN_GAMES or f.get("m_hl", 0.0) < MIN_BASE:
        return None
    try:
        vector = feature_vector(f, float(spread), favourite)
    except (KeyError, TypeError, ValueError):
        return None
    if len(vector) != len(coefficients):
        return None
    predicted = sum(c * v for c, v in zip(coefficients, vector))
    return min(max(predicted / f["m_hl"], RATIO_CLIP[0]), RATIO_CLIP[1])


def game_context(season: str, date_to: str, game_day: date, teams, *, get=None) -> dict:
    """`package["minutes_context"]`: {team: {espn_id: features}} for both sides of one game."""
    import nba_espn_league
    games = nba_espn_league.season_games(season, date_to, get=get)
    cache: dict[str, set] = {}

    def starters_of(game):
        key = str(game["event_id"])
        if key not in cache:
            cache[key] = starters(key, date.fromisoformat(game["date"]), get=get)
        return cache[key]

    wanted = set(teams)
    relevant = [g for g in games if wanted & set(g["teams"])]
    # A player's history may include games for another team (a trade); those games are in
    # `games` too, but only games of these two teams need starter flags fetched eagerly.
    return {"status": "available", "contract": 1, "season": season, "history_date_to": date_to,
            "teams": {team: team_features(_with_history(games, relevant, team), team, game_day, starters_of)
                      for team in teams}}


def _with_history(games, relevant, team):
    """Games of `team`, plus every other game its current players appeared in (trades)."""
    ids = {p["espn_id"] for g in relevant if team in g["teams"] for p in g["players"] if p["team"] == team}
    return [g for g in games if team in g["teams"] or any(p["espn_id"] in ids for p in g["players"])]
