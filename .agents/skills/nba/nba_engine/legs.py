"""Sportsbet milestone lines + the ESPN game package -> one scored row per leg.

A leg is "player X records at least N of stat S" (Sportsbet's integer milestone ladder;
decimal O/U lines are not milestones). Every number the selector or the report uses is
computed here, once.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from nba_availability import classify_injury_status
from nba_identity import player_name_key
from nba_schedule import canonical_team_abbr

from . import model

CATEGORY = {"points": "PTS", "rebounds": "REB", "assists": "AST", "threes_made": "FG3M"}
LABEL = {"PTS": "PTS", "REB": "REB", "AST": "AST", "FG3M": "3PM"}
MARKET = {"PTS": "pts", "REB": "reb", "AST": "ast", "FG3M": "fg3m"}
MIN_HISTORY_GAMES = 5      # below this the leg is outside C's fitted population
BENCH_MINUTES = 25.0       # L10 average minutes under this = bench role
EARLY_PREVIOUS_GAMES = 6   # EXP-20261026-06: L10 mostly last season -> AST/3PM unreliable
NEW_TEAM_MIN_GAMES = 5


@dataclass
class Leg:
    player: str
    team: str
    opponent: str
    stat: str                    # PTS / REB / AST / FG3M
    line: float                  # milestone N, i.e. stat >= N
    price: float
    l10: list[float]
    minutes_l10: float
    hit_l10: float               # fractions, 0..1
    hit_l5: float
    hit_l3: float
    avg: float
    median: float
    l3_avg: float
    cov: float
    market: float                # 1/price
    p_c: float | None            # C layer
    p_s: float | None            # season-rate model, price-free
    p_ms: float | None           # market + S: the published probability
    availability: str            # ok / dtd   (out players never become legs)
    flags: list[str] = field(default_factory=list)

    @property
    def p_final(self) -> float | None:
        return self.p_ms if self.p_ms is not None else self.p_c

    @property
    def label(self) -> str:
        return LABEL[self.stat]

    @property
    def desc(self) -> str:
        return f"{self.player} ({self.team}) {self.label} {self.line:g}+"

    def to_dict(self) -> dict:
        return {**asdict(self), "p_final": self.p_final, "label": self.label, "desc": self.desc}


def _rate(values, line):
    return sum(v >= line for v in values) / len(values) if values else 0.0


def _stats(values):
    """(mean, median, coefficient of variation)."""
    n = len(values)
    if not n:
        return 0.0, 0.0, 0.0
    avg = sum(values) / n
    s = sorted(values)
    median = (s[n // 2 - 1] + s[n // 2]) / 2 if n % 2 == 0 else s[n // 2]
    sd = math.sqrt(sum((v - avg) ** 2 for v in values) / n)
    return avg, median, (sd / avg if avg else 0.0)


def _find(players, name):
    key = player_name_key(name)
    matches = [p for p in players if player_name_key(p.get("name", "")) == key]
    return matches[0] if len(matches) == 1 else None


def _injury(injuries, team, name):
    statuses = (injuries or {}).get(team) or {}
    key = player_name_key(name)
    return next((s for n, s in statuses.items() if player_name_key(n) == key), "")


def _flags(stat, gamelog, team, season, minutes):
    flags = []
    if minutes < BENCH_MINUTES:
        flags.append("bench_minutes")
    seasons = gamelog.get("l10_seasons") or []
    if stat in ("AST", "FG3M") and season and sum(s != season for s in seasons) >= EARLY_PREVIOUS_GAMES:
        flags.append("l10_mostly_previous_season")
    teams = [canonical_team_abbr(str(m).split()[0]) for m in gamelog.get("l10_matchups") or [] if str(m).split()]
    if teams and any(t != canonical_team_abbr(team) for t in teams) and teams.count(canonical_team_abbr(team)) < NEW_TEAM_MIN_GAMES:
        flags.append("new_team")
    return flags


def build_legs(odds: dict, package: dict) -> tuple[list[Leg], dict]:
    """All scoreable milestone legs of one game, plus counts of what was skipped and why."""
    away, home = odds["away_team"], odds["home_team"]
    season = (package.get("meta") or {}).get("roster_season")
    players = package.get("players") or {}
    skipped: dict[str, int] = {}
    legs = []
    for category, by_player in (odds.get("player_props") or {}).items():
        stat = CATEGORY.get(category)
        if stat is None:
            continue
        for name, entry in by_player.items():
            team = next((t for t in (away, home) if _find(players.get(t, []), name)), None)
            if team is None:
                skipped["unmatched_roster"] = skipped.get("unmatched_roster", 0) + 1
                continue
            p = _find(players[team], name)
            level = classify_injury_status(_injury(package.get("injuries"), team, name) or p.get("status"))
            if level == "out":
                skipped["out"] = skipped.get("out", 0) + 1
                continue
            gamelog = p.get("gamelog") or {}
            l10 = [float(v) for v in gamelog.get(stat) or []]
            if len(l10) < MIN_HISTORY_GAMES:
                skipped["short_history"] = skipped.get("short_history", 0) + 1
                continue
            mins = [float(m) for m in gamelog.get("MIN") or []]
            minutes = sum(mins) / len(mins) if mins else 0.0
            avg, median, cov = _stats(l10)
            l3 = l10[:3]
            opponent = home if team == away else away
            opp_ctx = (package.get("opponent_context") or {}).get(team)
            flags = _flags(stat, gamelog, team, season, minutes)
            if stat == "FG3M" and round(cov, 3) > 0.5:
                flags.append("volatile_3pm")
            for line_text, price_text in (entry.get("lines") or {}).items():
                line, price = float(line_text), float(price_text)
                if not line.is_integer() or price < 1.01:
                    continue
                hit10 = _rate(l10, line)
                p_s = model.s_prob(gamelog.get("season_log"), stat, line, opp_ctx, season, team)
                legs.append(Leg(
                    player=name, team=team, opponent=opponent, stat=stat, line=line, price=price,
                    l10=l10, minutes_l10=round(minutes, 1), hit_l10=hit10, hit_l5=_rate(l10[:5], line),
                    hit_l3=_rate(l3, line), avg=round(avg, 2), median=median, l3_avg=round(sum(l3) / len(l3), 2),
                    cov=round(cov, 3), market=1.0 / price,
                    p_c=model.c_prob(stat, price, hit10),
                    p_s=p_s, p_ms=model.ms_prob(stat, price, p_s),
                    availability=level, flags=list(flags)))
    return legs, skipped
