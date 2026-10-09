#!/usr/bin/env python3
"""Walk-forward harness for the match-winner Elo backbone.

MEASUREMENT ONLY. Nothing reads this to decide a bet.

WHY THIS EXISTS (2026-10-09)

The backbone (0.65 surface Elo + 0.35 overall Elo, logit blend) is the only
part of the match model that carries independent information -- 164 of the
168 feature leaves are re-slices of past results -- and its K curve was tuned
on 11.5k matches when `player_match_history` now holds ~200k winner rows. Every
candidate change to it is judged here, against outcomes, on one corpus.

It also measures a defect found the same day. `elo_builder` stores the
PRE-match rating stamped with the match date, and `elo_history.rating_as_of`
returns the latest row STRICTLY BEFORE the date -- so production always reads
the rating from before the player's previous match. Today's R1 win is invisible
to tomorrow's R2 price, and a player with one prior match is priced at 1500.
`--variant lag` reproduces production; every other variant reads the rating at
the start of the match day, which is the correct as-of value.

DESIGN

* The corpus is extracted ONCE to a small SQLite file (`extract`). Long reads
  on the production database hold a shared lock that blocks the scheduler's
  writes; the 18:00 run was held up by exactly that on 2026-10-09.
* One chronological walk per variant. A match is scored only if both players
  have a prior match DATE -- the same population production would price -- so
  every variant is scored on the identical set of matches.
* Folds are pre-registered by year: dev 2019-2021 and 2022-2023, dev-confirm
  2024-2025, and 2026 reported separately. The live pre-match predictions since
  2026-08-28 are the holdout and are NOT read here.
* Paired bootstrap by match, seed 20260826, 4,000 resamples (tennis-v1 ruler).
  Positive delta = candidate is WORSE (higher logloss).

Usage:
    PYTHONPATH=src .venv/bin/python scripts/tune_elo_backbone.py extract --out CACHE.db
    PYTHONPATH=src .venv/bin/python scripts/tune_elo_backbone.py verify  --cache CACHE.db
    PYTHONPATH=src .venv/bin/python scripts/tune_elo_backbone.py compare --cache CACHE.db \\
        --baseline lag --candidate fixed
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from tennis_wc.features.elo import elo_probability  # noqa: E402
from tennis_wc.modelling.calibration import (  # noqa: E402
    ELO_K_BASE,
    ELO_K_EXPONENT,
    ELO_K_OFFSET,
)
from tennis_wc.modelling.elo_builder import ELO_PROVIDERS  # noqa: E402
from tennis_wc.modelling.probability_model import ELO_BACKBONE_WEIGHTS  # noqa: E402

BOOTSTRAP_SEED = 20260826
BOOTSTRAP_RESAMPLES = 4000
INITIAL_RATING = 1500.0
PROB_FLOOR, PROB_CEIL = 0.02, 0.98   # production clamp in _combine_components

FOLDS = {
    "dev_2019_2021": ("2019-01-01", "2022-01-01"),
    "dev_2022_2023": ("2022-01-01", "2024-01-01"),
    "confirm_2024_2025": ("2024-01-01", "2026-01-01"),
    "recent_2026": ("2026-01-01", "2027-01-01"),
}


@dataclass(frozen=True)
class Params:
    """One backbone configuration. Defaults reproduce production exactly."""
    lag: bool = True                       # production's one-match lag
    k_base: float = ELO_K_BASE
    k_offset: float = ELO_K_OFFSET
    k_exponent: float = ELO_K_EXPONENT
    w_surface: float = ELO_BACKBONE_WEIGHTS["surface_elo_edge"]
    # Pull a returning player's rating toward the mean: fraction of the gap to
    # INITIAL_RATING removed per 30 idle days beyond `layoff_grace_days`.
    layoff_decay_per_30d: float = 0.0
    layoff_grace_days: int = 60
    # Skip the update for a cross-provider duplicate of a match already walked
    # (same pair, same winner, different provider, within DEDUP_WINDOW_DAYS).
    dedup: bool = False

    def k(self, played: int) -> float:
        return self.k_base / ((played + self.k_offset) ** self.k_exponent)


VARIANTS = {
    "lag": Params(),
    "fixed": Params(lag=False),
    "lag_dedup": Params(dedup=True),
    "fixed_dedup": Params(lag=False, dedup=True),
}

# Sackmann/TennisMyLife stamp a match with its TOURNAMENT start date and
# TennisExplorer with the day it was played, so one match can appear twice up to
# a week apart. 2026: 7,078 such pairs, 99% with the same winner, against about
# 11,300 tour/challenger rows -- most of the bettable population updated twice.
DEDUP_WINDOW_DAYS = 7


@dataclass
class _Day:
    """Per-player (or per player-surface) state for as-of reads."""
    cur_date: str | None = None
    cur_first: float | None = None     # rating at the start of cur_date
    prev_first: float | None = None    # rating at the start of the previous date
    last_played: str | None = None


@dataclass
class WalkResult:
    keys: list = field(default_factory=list)     # (date, level, tour, surface)
    p_winner: list = field(default_factory=list)
    final_overall: dict = field(default_factory=dict)


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _days_between(a: str, b: str) -> int:
    from datetime import date
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def extract(db: str, out: str) -> int:
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    placeholders = ",".join("?" for _ in ELO_PROVIDERS)
    rows = src.execute(
        f"""
        SELECT source_provider, provider_match_id, player_id, opponent_id,
               match_date, surface, tournament_level, tour, format, round
        FROM player_match_history
        WHERE source_provider IN ({placeholders}) AND won = 1
        ORDER BY match_date, provider_match_id
        """,
        ELO_PROVIDERS,
    ).fetchall()
    players = src.execute("SELECT id, overall_elo, surface_elo_json FROM players").fetchall()
    src.close()
    Path(out).unlink(missing_ok=True)
    dst = sqlite3.connect(out)
    dst.executescript(
        """
        CREATE TABLE wins (seq INTEGER PRIMARY KEY, source_provider TEXT, provider_match_id TEXT,
            player_id INTEGER, opponent_id INTEGER, match_date TEXT, surface TEXT,
            tournament_level TEXT, tour TEXT, format TEXT, round TEXT);
        CREATE TABLE players (id INTEGER PRIMARY KEY, overall_elo REAL, surface_elo_json TEXT);
        """
    )
    dst.executemany(
        "INSERT INTO wins (source_provider, provider_match_id, player_id, opponent_id, match_date,"
        " surface, tournament_level, tour, format, round) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    dst.executemany("INSERT INTO players VALUES (?,?,?)", players)
    dst.commit()
    dst.close()
    print(f"extracted {len(rows):,} winner rows, {len(players):,} players -> {out}")
    return 0


def load(cache: str) -> list[tuple]:
    conn = sqlite3.connect(f"file:{cache}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT player_id, opponent_id, match_date, surface, tournament_level, tour,"
        " source_provider FROM wins ORDER BY seq").fetchall()
    conn.close()
    return rows


def cross_provider_duplicates(rows: list[tuple]) -> set[int]:
    """Indices of rows that repeat an EARLIER row of the same match from another
    provider. The earliest copy is kept, so neither the duplicate's update nor
    its score can carry the result into a read that precedes it."""
    from datetime import date as _date

    kept: dict[tuple, list[tuple]] = defaultdict(list)   # pair -> [(date, winner, provider)]
    dups: set[int] = set()
    for i, row in enumerate(rows):
        winner, loser, day, provider = row[0], row[1], row[2], row[6]
        pair = (min(winner, loser), max(winner, loser))
        d = _date.fromisoformat(day[:10])
        if any(prov != provider and w == winner and abs((d - kd).days) <= DEDUP_WINDOW_DAYS
               for kd, w, prov in kept[pair]):
            dups.add(i)
            continue
        kept[pair].append((d, winner, provider))
    return dups


def _norm_surface(value) -> str | None:
    return (str(value).strip().lower() or None) if value else None


def walk(rows: list[tuple], params: Params, duplicates: set[int] | None = None) -> WalkResult:
    """One chronological pass. Mirrors `elo_builder.build_sackmann_elo` for the
    updates and `feature_builder._elo_as_of` + `_combine_components` for the
    read, with the read switchable between production's lag and the start-of-day
    value."""
    overall: dict[int, float] = defaultdict(lambda: INITIAL_RATING)
    played: dict[int, int] = defaultdict(int)
    surf: dict[tuple, float] = {}
    surf_played: dict[tuple, int] = defaultdict(int)
    day: dict = defaultdict(_Day)
    out = WalkResult()

    def touch(key, date, current):
        d = day[key]
        if d.cur_date != date:
            d.prev_first = d.cur_first
            d.cur_date = date
            d.cur_first = current
        return d

    duplicates = duplicates if duplicates is not None else set()
    for i, (winner, loser, date, surface_raw, level, tour, *_rest) in enumerate(rows):
        surface = _norm_surface(surface_raw)
        is_dup = i in duplicates
        if is_dup and params.dedup:
            continue

        # Layoff decay applies to the live rating before anything reads it.
        if params.layoff_decay_per_30d > 0:
            for pid in (winner, loser):
                last = day[pid].last_played
                if last:
                    idle = _days_between(last, date) - params.layoff_grace_days
                    if idle > 0:
                        shrink = min(1.0, params.layoff_decay_per_30d * idle / 30)
                        overall[pid] -= shrink * (overall[pid] - INITIAL_RATING)

        dw = touch(winner, date, overall[winner])
        dl = touch(loser, date, overall[loser])
        # A player is priceable only with a prior DATE -- what production needs
        # for any as-of row. Identical across variants, so every variant scores
        # the same matches.
        # Duplicates are never scored, under any variant, so every variant is
        # judged on the same matches.
        eligible = dw.prev_first is not None and dl.prev_first is not None and not is_dup
        if eligible:
            ow = dw.prev_first if params.lag else dw.cur_first
            ol = dl.prev_first if params.lag else dl.cur_first
            p_overall = elo_probability(ow, ol)
            p = p_overall
            if surface:
                sw = _surface_read(day.get((winner, surface)), surf.get((winner, surface)),
                                   date, params.lag)
                sl = _surface_read(day.get((loser, surface)), surf.get((loser, surface)),
                                   date, params.lag)
                sw = ow if sw is None else sw
                sl = ol if sl is None else sl
                p_surface = elo_probability(sw, sl)
                logit = (params.w_surface * _logit(p_surface)
                         + (1 - params.w_surface) * _logit(p_overall))
                p = 1 / (1 + math.exp(-logit))
            p = min(max(p, PROB_FLOOR), PROB_CEIL)
            out.keys.append((date, level, tour, surface))
            out.p_winner.append(p)

        # --- update (identical to elo_builder) ---
        w_pre, l_pre = overall[winner], overall[loser]
        expected = elo_probability(w_pre, l_pre)
        overall[winner] = w_pre + params.k(played[winner]) * (1 - expected)
        overall[loser] = l_pre + params.k(played[loser]) * (0 - (1 - expected))
        if surface:
            kw, kl = (winner, surface), (loser, surface)
            ws_pre = surf.get(kw, w_pre)
            ls_pre = surf.get(kl, l_pre)
            touch(kw, date, ws_pre)
            touch(kl, date, ls_pre)
            se = elo_probability(ws_pre, ls_pre)
            surf[kw] = ws_pre + params.k(surf_played[kw]) * (1 - se)
            surf[kl] = ls_pre + params.k(surf_played[kl]) * (0 - (1 - se))
            surf_played[kw] += 1
            surf_played[kl] += 1
        played[winner] += 1
        played[loser] += 1
        day[winner].last_played = date
        day[loser].last_played = date

    out.final_overall = dict(overall)
    return out


def _surface_read(d: _Day | None, current: float | None, date: str, lag: bool) -> float | None:
    """As-of read of a surface rating on `date`, before any update on `date`.

    A surface key is only touched when it is updated, so on the first match of
    a new date its state still describes the previous date it was played on.
    """
    if d is None or d.cur_date is None:
        return None                 # no surface history: caller falls back to overall
    if d.cur_date == date:          # a second match on this surface today
        return d.prev_first if lag else d.cur_first
    # Last played on an earlier date. Production reads that date's first
    # pre-match rating; the start-of-day value is the live post-update rating.
    return d.cur_first if lag else current


def score(result: WalkResult) -> list[tuple[float, float]]:
    """(logloss, brier) per match. The winner always won."""
    return [(-math.log(p), (1 - p) ** 2) for p in result.p_winner]


def fold_of(date: str) -> str | None:
    for name, (lo, hi) in FOLDS.items():
        if lo <= date < hi:
            return name
    return None


def level_group(level: str | None) -> str:
    lvl = str(level or "").upper()
    if lvl in {"G", "GRAND_SLAM"}:
        return "slam"
    if lvl in {"M", "A", "F", "P", "PM", "I", "D", "ATP_1000", "ATP_500", "ATP_250",
               "WTA_1000", "WTA_500", "WTA_250", "TOUR", "O"}:
        return "tour"
    if "CHALL" in lvl or lvl == "C":
        return "challenger"
    if "ITF" in lvl or lvl.startswith(("M15", "M25", "W15", "W25", "W35", "W50", "W75", "W100")) or lvl in {"S", "15", "25"}:
        return "itf"
    return "other:" + (lvl or "blank")


def paired_delta(base: list[float], cand: list[float]) -> dict:
    """Mean paired difference and its percentile bootstrap CI (resampling matches)."""
    import numpy as np

    diffs = np.asarray(cand, dtype=float) - np.asarray(base, dtype=float)
    n = len(diffs)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = np.empty(BOOTSTRAP_RESAMPLES)
    chunk = max(1, 20_000_000 // max(n, 1))   # bound memory at ~160MB per chunk
    for lo in range(0, BOOTSTRAP_RESAMPLES, chunk):
        hi = min(BOOTSTRAP_RESAMPLES, lo + chunk)
        idx = rng.integers(0, n, size=(hi - lo, n))
        means[lo:hi] = diffs[idx].mean(axis=1)
    ci_lo, ci_hi = np.percentile(means, [2.5, 97.5])
    return {"n": n, "delta": float(diffs.mean()), "ci": (float(ci_lo), float(ci_hi))}


def _parse_params(spec: str) -> Params:
    """`fixed` or `fixed,k_base=140,w_surface=0.5` -- a named variant plus overrides."""
    name, *overrides = spec.split(",")
    params = VARIANTS[name]
    for item in overrides:
        key, value = item.split("=")
        current = getattr(params, key)
        params = replace(params, **{key: type(current)(value) if not isinstance(current, bool)
                                    else value.lower() in {"1", "true", "yes"}})
    return params


def compare(rows, baseline: Params, candidate: Params, by: str, quick: bool) -> dict:
    duplicates = cross_provider_duplicates(rows)
    base = walk(rows, baseline, duplicates)
    cand = walk(rows, candidate, duplicates)
    assert base.keys == cand.keys, "variants must score the identical match set"
    b_scores, c_scores = score(base), score(cand)
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, (date, level, tour, surface) in enumerate(base.keys):
        fold = fold_of(date)
        if fold is None:
            continue
        groups[(fold, "all")].append(i)
        if by in {"level", "all"}:
            groups[(fold, "level=" + level_group(level))].append(i)
        if by in {"surface", "all"}:
            groups[(fold, "surface=" + (surface or "unknown"))].append(i)
        if by in {"tour", "all"}:
            groups[(fold, "tour=" + str(tour))].append(i)
    report = {}
    global BOOTSTRAP_RESAMPLES
    saved = BOOTSTRAP_RESAMPLES
    if quick:
        BOOTSTRAP_RESAMPLES = 500
    try:
        for key in sorted(groups):
            idx = groups[key]
            if len(idx) < 200:
                continue
            ll = paired_delta([b_scores[i][0] for i in idx], [c_scores[i][0] for i in idx])
            br = paired_delta([b_scores[i][1] for i in idx], [c_scores[i][1] for i in idx])
            report[key] = {
                "n": ll["n"],
                "base_ll": sum(b_scores[i][0] for i in idx) / len(idx),
                "cand_ll": sum(c_scores[i][0] for i in idx) / len(idx),
                "d_ll": ll["delta"], "d_ll_ci": ll["ci"],
                "d_brier": br["delta"], "d_brier_ci": br["ci"],
            }
    finally:
        BOOTSTRAP_RESAMPLES = saved
    return report


def _verdict(entry: dict) -> str:
    lo, hi = entry["d_ll_ci"]
    if hi < 0:
        return "BETTER"
    if lo > 0:
        return "WORSE"
    return "level"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--db", default=str(PROJECT_DIR / "tennis_wc.db"))
    e.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--cache", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--cache", required=True)
    c.add_argument("--baseline", default="lag")
    c.add_argument("--candidate", required=True)
    c.add_argument("--by", choices=["none", "level", "surface", "tour", "all"], default="level")
    c.add_argument("--quick", action="store_true", help="500 resamples, for scanning only")
    c.add_argument("--json", action="store_true")
    h = sub.add_parser("holdout", help="final confirmation on live pre-match predictions")
    h.add_argument("--db", default=str(PROJECT_DIR / "tennis_wc.db"))
    h.add_argument("--cache", required=True)
    h.add_argument("--candidate", required=True)
    h.add_argument("--stored-components", action="store_true",
                   help="re-blend stored component probabilities (weight-only candidates)")
    args = parser.parse_args()

    if args.cmd == "extract":
        return extract(args.db, args.out)
    if args.cmd == "holdout":
        if args.stored_components:
            return run_holdout_stored(args.db, _parse_params(args.candidate))
        return run_holdout(args.db, args.cache, _parse_params(args.candidate))

    rows = load(args.cache)
    if args.cmd == "verify":
        return verify(args.cache, rows)

    baseline, candidate = _parse_params(args.baseline), _parse_params(args.candidate)
    report = compare(rows, baseline, candidate, args.by, args.quick)
    if args.json:
        print(json.dumps({f"{k[0]}|{k[1]}": v for k, v in report.items()}, indent=2))
        return 0
    print(f"baseline  {baseline}\ncandidate {candidate}")
    print("Δ = candidate − baseline; negative logloss Δ = candidate better\n")
    print(f"{'fold':20s} {'group':24s} {'n':>7s} {'base LL':>8s} {'ΔLL':>9s} {'95% CI':>22s} {'ΔBrier':>9s}  verdict")
    for (fold, group), r in report.items():
        lo, hi = r["d_ll_ci"]
        print(f"{fold:20s} {group:24s} {r['n']:7,d} {r['base_ll']:8.4f} {r['d_ll']:+9.5f} "
              f"[{lo:+.5f}, {hi:+.5f}] {r['d_brier']:+9.5f}  {_verdict(r)}")
    return 0


def verify(cache: str, rows) -> int:
    """Production params must reproduce the ratings the last build wrote.

    `players.overall_elo` is the final rating of the most recent build. If the
    corpus has grown since that build the tail will differ, so the check reports
    agreement rather than demanding all of it -- but a mismatch on most players
    means this walk is not production's walk and nothing it says can be trusted.
    """
    result = walk(rows, Params())
    conn = sqlite3.connect(f"file:{cache}?mode=ro", uri=True)
    stored = {pid: elo for pid, elo, _ in conn.execute("SELECT * FROM players") if elo is not None}
    conn.close()
    common = [pid for pid in stored if pid in result.final_overall]
    exact = sum(1 for pid in common if abs(stored[pid] - result.final_overall[pid]) < 0.01)
    close = sum(1 for pid in common if abs(stored[pid] - result.final_overall[pid]) < 1.0)
    share = exact / len(common) if common else 0.0
    print(f"players compared {len(common):,}: exact(<0.01) {exact:,} ({share:.1%}), "
          f"within 1 point {close:,} ({close / len(common):.1%})")
    print(f"scored matches (both players have a prior date): {len(result.p_winner):,}")
    if share < 0.90:
        print("VERIFY FAILED: this walk does not reproduce production's ratings")
        return 1
    print("VERIFY OK")
    return 0


# --------------------------------------------------------------------------- #
# Live holdout: swap the backbone inside stored pre-match predictions
# --------------------------------------------------------------------------- #
HOLDOUT_START = "2026-08-28"   # rank data + input gate landed; untouched by any fit

_HOLDOUT_SQL = """
WITH fo AS (SELECT match_id, MIN(id) AS sid FROM odds_snapshots
            WHERE match_id IS NOT NULL AND market = 'match_winner' AND source_provider != 'mock'
            GROUP BY match_id)
SELECT p.id, p.match_id, p.pricing_json, p.created_at, m.match_date, m.start_time_utc,
       m.player_a_id, m.player_b_id, r.winner_player_id, o.player_a_odds, o.player_b_odds,
       (SELECT tl.level FROM tournament_levels tl WHERE tl.tournament_id = m.tournament_id
         ORDER BY tl.id DESC LIMIT 1) AS level
FROM predictions p
JOIN matches m ON m.id = p.match_id
JOIN match_results r ON r.match_id = p.match_id
JOIN fo ON fo.match_id = p.match_id
JOIN odds_snapshots o ON o.id = fo.sid
WHERE m.match_date >= ? AND m.start_time_utc IS NOT NULL AND m.start_time_utc != ''
  AND p.created_at < m.start_time_utc
ORDER BY p.id
"""


def load_holdout(db: str) -> list[dict]:
    """Latest PRE-MATCH prediction per match, with its earliest price."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    latest = {}
    for row in conn.execute(_HOLDOUT_SQL, (HOLDOUT_START,)):
        latest[row["match_id"]] = dict(row)
    conn.close()
    out = []
    for row in latest.values():
        model = (json.loads(row["pricing_json"] or "{}").get("pricing") or {}).get("model") or {}
        comps = {c.get("name"): c for c in model.get("components") or []}
        surf_c, over_c = comps.get("surface_elo_edge"), comps.get("overall_elo_edge")
        if not (surf_c and over_c and surf_c.get("active") and over_c.get("active")):
            continue   # no Elo backbone: production priced it on nudges alone
        if model.get("elo_base_logit") is None or model.get("total_nudge_logit") is None:
            continue
        a, b = row["player_a_odds"], row["player_b_odds"]
        if not a or not b or a <= 1 or b <= 1:
            continue
        row.update(
            stored_pa=float(model["player_a_probability"]),
            stored_surface_p=float(surf_c["probability"]),
            stored_overall_p=float(over_c["probability"]),
            nudge=float(model["total_nudge_logit"]),
            market_pa=(1 / a) / (1 / a + 1 / b),
            y=1 if row["winner_player_id"] == row["player_a_id"] else 0,
        )
        out.append(row)
    return out


def ratings_as_of(rows: list[tuple], params: Params, queries: set[tuple[int, str]],
                  duplicates: set[int] | None = None) -> dict:
    """{(player, date): (overall, {surface: rating})} as production would read it
    on `date` under `params` -- `lag` gives production's read, otherwise the
    start-of-day rating."""
    by_date: dict[str, list[int]] = defaultdict(list)
    for player, day in queries:
        by_date[day].append(player)
    pending = sorted(by_date)
    answers: dict = {}
    overall: dict[int, float] = defaultdict(lambda: INITIAL_RATING)
    played: dict[int, int] = defaultdict(int)
    surf: dict[tuple, float] = {}
    surf_played: dict[tuple, int] = defaultdict(int)
    first_of_last_date: dict = {}     # key -> (date, first pre-rating that date)
    duplicates = duplicates if duplicates is not None else set()

    def answer_through(limit: str | None):
        while pending and (limit is None or pending[0] <= limit):
            day = pending.pop(0)
            for player in by_date[day]:
                if params.lag:
                    rec = first_of_last_date.get(player)
                    ov = rec[1] if rec else None
                    srf = {k[1]: v[1] for k, v in first_of_last_date.items()
                           if isinstance(k, tuple) and k[0] == player}
                else:
                    ov = overall[player] if player in played else None
                    srf = {k[1]: v for k, v in surf.items() if k[0] == player}
                answers[(player, day)] = (ov, srf)

    for i, (winner, loser, date, surface_raw, *_rest) in enumerate(rows):
        answer_through_before = date
        # every query dated on or before this row's date is answered before it
        while pending and pending[0] <= answer_through_before:
            answer_through(pending[0])
        if params.dedup and i in duplicates:
            continue
        surface = _norm_surface(surface_raw)
        for key, value in ((winner, overall[winner]), (loser, overall[loser])):
            rec = first_of_last_date.get(key)
            if rec is None or rec[0] != date:
                first_of_last_date[key] = (date, value)
        w_pre, l_pre = overall[winner], overall[loser]
        e = elo_probability(w_pre, l_pre)
        overall[winner] = w_pre + params.k(played[winner]) * (1 - e)
        overall[loser] = l_pre + params.k(played[loser]) * (0 - (1 - e))
        if surface:
            kw, kl = (winner, surface), (loser, surface)
            ws_pre, ls_pre = surf.get(kw, w_pre), surf.get(kl, l_pre)
            for key, value in ((kw, ws_pre), (kl, ls_pre)):
                rec = first_of_last_date.get(key)
                if rec is None or rec[0] != date:
                    first_of_last_date[key] = (date, value)
            se = elo_probability(ws_pre, ls_pre)
            surf[kw] = ws_pre + params.k(surf_played[kw]) * (1 - se)
            surf[kl] = ls_pre + params.k(surf_played[kl]) * (0 - (1 - se))
            surf_played[kw] += 1
            surf_played[kl] += 1
        played[winner] += 1
        played[loser] += 1
    answer_through(None)
    return answers


def backbone_probability(ra, rb, surface: str | None, w_surface: float) -> float | None:
    """`_combine_components` backbone for player A (no clamp, no nudge)."""
    (oa, sa), (ob, sb) = ra, rb
    if oa is None or ob is None:
        return None
    p_over = elo_probability(oa, ob)
    s_a = sa.get(surface, oa) if surface else oa
    s_b = sb.get(surface, ob) if surface else ob
    p_surf = elo_probability(s_a, s_b)
    logit = w_surface * _logit(p_surf) + (1 - w_surface) * _logit(p_over)
    return 1 / (1 + math.exp(-logit))


def run_holdout_stored(db: str, candidate: Params) -> int:
    """Re-blend the STORED surface/overall component probabilities with the
    candidate's `w_surface`. Exact for a weight-only change: no Elo replay, so
    none of the replay's problems (late-arriving rows stamped with tournament
    start dates, stale `player_elo_history` rows) can reach it. Cannot test
    anything that changes the ratings themselves."""
    preds = load_holdout(db)
    groups: dict[str, list[tuple]] = defaultdict(list)
    for r in preds:
        logit = (candidate.w_surface * _logit(r["stored_surface_p"])
                 + (1 - candidate.w_surface) * _logit(r["stored_overall_p"]))
        p_new = min(max(1 / (1 + math.exp(-(logit + r["nudge"]))), PROB_FLOOR), PROB_CEIL)
        y = r["y"]
        ll = lambda p: -(y * math.log(p) + (1 - y) * math.log(1 - p))
        entry = (ll(r["stored_pa"]), ll(p_new), ll(r["market_pa"]))
        lvl = str(r["level"] or "").upper()
        tier = ("itf_utr" if ("ITF" in lvl or "UTR" in lvl) else
                "challenger" if "CHALL" in lvl else "unknown" if not lvl or lvl == "UNKNOWN" else "tour")
        groups["all"].append(entry)
        groups["tier=" + tier].append(entry)
        groups["bettable" if tier in {"tour", "challenger"} else "not_bettable"].append(entry)
    _print_holdout(groups, candidate)
    return 0


def _print_holdout(groups, candidate):
    print(f"candidate {candidate}")
    print(f"{'group':16s} {'n':>6s} {'stored LL':>9s} {'cand LL':>8s} {'market':>7s} "
          f"{'Δ cand−stored':>14s} {'95% CI':>22s} {'gap to market: stored → cand':>30s}")
    for name in sorted(groups):
        g = groups[name]
        if len(g) < 30:
            continue
        d = paired_delta([e[0] for e in g], [e[1] for e in g])
        n = len(g)
        st, ca, mk = (sum(e[i] for e in g) / n for i in range(3))
        print(f"{name:16s} {n:6d} {st:9.4f} {ca:8.4f} {mk:7.4f} {d['delta']:+14.5f} "
              f"[{d['ci'][0]:+.5f}, {d['ci'][1]:+.5f}]   {st - mk:+.4f} → {ca - mk:+.4f}")


def run_holdout(db: str, cache: str, candidate: Params) -> int:
    """Final confirmation on live pre-match predictions. NOT for choosing values.

    Step 1 re-derives production's stored surface/overall component
    probabilities from a `lag` walk; if they do not match, the swap below would
    be measuring a different backbone and nothing is reported.
    """
    rows = load(cache)
    preds = load_holdout(db)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    surface_of = {}
    for mid, surface in conn.execute(
            "SELECT m.id, (SELECT LOWER(tl.surface) FROM tournament_levels tl"
            " WHERE tl.tournament_id = m.tournament_id AND tl.tour = m.tour"
            " ORDER BY (tl.source_provider = 'curated_tournament_metadata') DESC,"
            " (tl.level != 'UNKNOWN') DESC, (tl.surface IS NOT NULL) DESC, tl.id DESC LIMIT 1)"
            " FROM matches m WHERE m.match_date >= ?", (HOLDOUT_START,)):
        surface_of[mid] = surface
    conn.close()
    queries = {(r[k], r["match_date"]) for r in preds for k in ("player_a_id", "player_b_id")}

    prod = ratings_as_of(rows, Params(), queries)
    agree = 0
    for r in preds:
        ra, rb = prod[(r["player_a_id"], r["match_date"])], prod[(r["player_b_id"], r["match_date"])]
        p = None if ra[0] is None or rb[0] is None else elo_probability(ra[0], rb[0])
        r["replica_ok"] = p is not None and abs(p - r["stored_overall_p"]) < 0.01
        agree += r["replica_ok"]
    print(f"holdout predictions with an Elo backbone: {len(preds):,}")
    print(f"production overall-Elo component reproduced within 0.01: {agree:,} "
          f"({agree / max(len(preds), 1):.1%})")
    if agree / max(len(preds), 1) < 0.80:
        print("HOLDOUT ABORTED: the lag walk does not reproduce production's stored components")
        return 1

    cand = ratings_as_of(rows, candidate, queries, cross_provider_duplicates(rows))
    groups: dict[str, list[tuple]] = defaultdict(list)
    for r in preds:
        if not r["replica_ok"]:
            continue
        ra, rb = cand[(r["player_a_id"], r["match_date"])], cand[(r["player_b_id"], r["match_date"])]
        p_bb = backbone_probability(ra, rb, surface_of.get(r["match_id"]), candidate.w_surface)
        if p_bb is None:
            continue
        p_new = min(max(1 / (1 + math.exp(-(_logit(p_bb) + r["nudge"]))), PROB_FLOOR), PROB_CEIL)
        y = r["y"]
        ll = lambda p: -(y * math.log(p) + (1 - y) * math.log(1 - p))
        entry = (ll(r["stored_pa"]), ll(p_new), ll(r["market_pa"]))
        lvl = str(r["level"] or "").upper()
        tier = ("itf_utr" if ("ITF" in lvl or "UTR" in lvl) else
                "challenger" if "CHALL" in lvl else "unknown" if not lvl or lvl == "UNKNOWN" else "tour")
        groups["all"].append(entry)
        groups["tier=" + tier].append(entry)
        groups["bettable" if tier in {"tour", "challenger"} else "not_bettable"].append(entry)
    print(f"\ncandidate {candidate}")
    print(f"{'group':16s} {'n':>6s} {'stored LL':>9s} {'cand LL':>8s} {'market':>7s} "
          f"{'Δ cand−stored':>14s} {'95% CI':>22s} {'gap to market: stored → cand':>30s}")
    for name in sorted(groups):
        g = groups[name]
        if len(g) < 30:
            continue
        d = paired_delta([e[0] for e in g], [e[1] for e in g])
        n = len(g)
        st, ca, mk = (sum(e[i] for e in g) / n for i in range(3))
        print(f"{name:16s} {n:6d} {st:9.4f} {ca:8.4f} {mk:7.4f} {d['delta']:+14.5f} "
              f"[{d['ci'][0]:+.5f}, {d['ci'][1]:+.5f}]   {st - mk:+.4f} → {ca - mk:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
