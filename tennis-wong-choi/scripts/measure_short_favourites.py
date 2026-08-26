#!/usr/bin/env python3
"""Is the match model better than the market on short-priced favourites?

MEASUREMENT ONLY. This script never stakes anything and nothing reads its
output to decide a bet. It exists because that cohort is the only place the
model was not beaten, and a lead that small has to be watched rather than
believed.

WHY THIS COHORT AND NOTHING ELSE

Over 2,001 settled fixtures, scored against the de-vigged EARLIEST
`match_winner` snapshot per match:

    model   logloss 0.6567   AUC 0.6648
    market  logloss 0.5996   AUC 0.7042
    paired Delta logloss +0.0571, 95% CI [+0.0416, +0.0730]

The market wins decisively, and betting the model's own claimed edge gets worse
the larger that edge is (-3.42% at EV>0 falling to -5.23% at EV>0.20, average
odds rising 3.98 -> 4.96), which is what a model that cannot price longshots
looks like. Split by price, the whole deficit is on the long side:

    odds > 3     model 0.6139  market 0.4804   Delta +0.1335
    odds <= 1.6  model 0.6401  market 0.6514   Delta -0.0112   (model ahead)

and the market's own AUC on short favourites is 0.5686 against the model's
0.6537. So on this one slice the market is close to uninformative and the model
is not.

IT DOES NOT PASS A GATE, AND IS NOT MEANT TO YET

    odds <= 1.6            n=254  Delta -0.0112  CI [-0.0453, +0.0218]  P=0.754
    odds <= 1.8            n=379  Delta -0.0071  CI [-0.0325, +0.0172]  P=0.717
    odds <= 1.6 and ATP    n=177  Delta -0.0296  CI [-0.0713, +0.0109]  P=0.921

Every interval crosses zero. `--min-sample` therefore refuses to return a
verdict below a pre-registered size rather than reporting a direction on 177
observations, and the walk-forward split is fixed here rather than chosen per
run: picking the window after seeing the answer is the failure this file exists
to avoid.

A SECOND QUESTION THE HEADLINE NUMBER CANNOT ANSWER

Short favourites are also where the takeout is thinnest, so "the model beats
the market here" and "the market is barely trying here" produce the same
logloss gap. `--report-overround` prints the book's margin per price band so
the two can be told apart before anyone acts on this.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/measure_short_favourites.py
    PYTHONPATH=src .venv/bin/python scripts/measure_short_favourites.py \
        --max-odds 1.8 --tour ATP --json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

# Pre-registered. A verdict below this is not reported, because the cohort's
# whole history is 254 observations and a direction read off that is noise.
MIN_SAMPLE = 600
# Fixed so a rerun cannot open or close the finding by reshuffling.
BOOTSTRAP_SEED = 20260826
BOOTSTRAP_RESAMPLES = 4000
# The gap must beat this to count as more than measurement noise.
DECISIVE_PROBABILITY = 0.95

# Earliest snapshot per match. `check_odds_are_pre_match` counts 2,925
# snapshots fetched after their match day and one selection ranging 1.26 to
# 41.0 across its own history -- those are in-running prices, so anything but
# MIN(id) prices the cohort with the result already known.
_ROWS_SQL = """
WITH first_odds AS (
    SELECT match_id, MIN(id) AS snapshot_id
    FROM odds_snapshots
    WHERE match_id IS NOT NULL AND market = 'match_winner'
    GROUP BY match_id
)
SELECT p.match_id, p.selection_player_id, p.model_probability, p.decision,
       o.player_a_odds, o.player_b_odds,
       m.player_a_id, m.player_b_id, m.tour, m.match_date,
       r.winner_player_id, p.id AS prediction_id
FROM predictions p
JOIN matches m ON m.id = p.match_id
JOIN match_results r ON r.match_id = p.match_id
JOIN first_odds f ON f.match_id = p.match_id
JOIN odds_snapshots o ON o.id = f.snapshot_id
WHERE p.model_probability IS NOT NULL
  AND r.winner_player_id IS NOT NULL
ORDER BY p.id
"""


def _load(conn) -> list[dict]:
    """One row per (match, selection), keeping the LATEST prediction for it.

    Several predictions exist per selection as the card is rebuilt; the newest
    is the one that would have been acted on.
    """
    latest: dict[tuple[int, int], sqlite3.Row] = {}
    for row in conn.execute(_ROWS_SQL).fetchall():
        latest[(row["match_id"], row["selection_player_id"])] = row
    out = []
    for row in latest.values():
        selection = row["selection_player_id"]
        if selection == row["player_a_id"]:
            odds, opponent_odds = row["player_a_odds"], row["player_b_odds"]
        elif selection == row["player_b_id"]:
            odds, opponent_odds = row["player_b_odds"], row["player_a_odds"]
        else:
            continue
        if not odds or not opponent_odds or odds <= 1.0 or opponent_odds <= 1.0:
            continue
        implied = (1 / odds) / ((1 / odds) + (1 / opponent_odds))
        out.append({
            "match_date": row["match_date"],
            "tour": row["tour"],
            "odds": float(odds),
            "overround": (1 / odds) + (1 / opponent_odds),
            "model": float(row["model_probability"]),
            "market": implied,
            "won": 1 if row["winner_player_id"] == selection else 0,
        })
    out.sort(key=lambda r: (r["match_date"] or "", r["odds"]))
    return out


def _log_loss(probability: float, won: int) -> float:
    p = min(max(probability, 1e-9), 1 - 1e-9)
    return -(won * math.log(p) + (1 - won) * math.log(1 - p))


def _paired_gap(rows: list[dict]) -> dict:
    """Paired bootstrap of (model log-loss - market log-loss).

    Paired because both compete on the same fixtures: an unpaired comparison
    would attribute the cohort's own difficulty to whichever side it landed on.
    Negative means the model is better.
    """
    diffs = [_log_loss(r["model"], r["won"]) - _log_loss(r["market"], r["won"])
             for r in rows]
    n = len(diffs)
    if not n:
        return {"n": 0}
    rng = random.Random(BOOTSTRAP_SEED)
    means = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        means.append(sum(rng.choice(diffs) for _ in range(n)) / n)
    means.sort()
    lo = means[int(0.025 * BOOTSTRAP_RESAMPLES)]
    hi = means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]
    better = sum(1 for m in means if m < 0) / len(means)
    return {
        "n": n,
        "delta_logloss": round(sum(diffs) / n, 5),
        "ci_low": round(lo, 5),
        "ci_high": round(hi, 5),
        "probability_model_better": round(better, 4),
        "model_logloss": round(
            sum(_log_loss(r["model"], r["won"]) for r in rows) / n, 5),
        "market_logloss": round(
            sum(_log_loss(r["market"], r["won"]) for r in rows) / n, 5),
    }


def _verdict(result: dict, min_sample: int = MIN_SAMPLE) -> str:
    """Deliberately refuses to answer on a small sample.

    "The direction is right on 177 observations" is how a cohort gap becomes a
    shipped feature that loses money.

    Decided on whether the interval clears zero, not on the tail probability
    alone. Those agree on real data and part on a dead heat: with the model and
    the market identical, every resampled mean is exactly 0.0, so
    `probability_model_better` is 0.0 and a probability test reads a perfect tie
    as MARKET AHEAD. A CI of [0, 0] is undecided, which is what a tie is -- and
    it matches the standard used everywhere else here, where an interval
    crossing zero is not evidence.
    """
    n = result.get("n", 0)
    if n < min_sample:
        return f"NOT ENOUGH DATA (n={n}, need {min_sample})"
    if result["ci_high"] < 0 and result["probability_model_better"] >= DECISIVE_PROBABILITY:
        return "MODEL AHEAD -- worth a staking proposal, with a walk-forward check"
    if result["ci_low"] > 0 and result["probability_model_better"] <= 1 - DECISIVE_PROBABILITY:
        return "MARKET AHEAD -- close the lead"
    return "UNDECIDED -- keep measuring, do not stake"


def _walk_forward(rows: list[dict], split_date: str) -> dict:
    """Fit nothing, but score the two halves separately.

    There is no coefficient here to overfit; what this catches is a gap that
    exists only in the earlier period, which is what a decayed edge looks like
    and what a single pooled number cannot distinguish from a live one.
    """
    early = [r for r in rows if (r["match_date"] or "") < split_date]
    late = [r for r in rows if (r["match_date"] or "") >= split_date]
    return {
        "split_date": split_date,
        "before": _paired_gap(early),
        "after": _paired_gap(late),
    }


def _overround_by_band(rows: list[dict]) -> list[dict]:
    """The book's margin per price band.

    "We are better here" and "the book is barely trying here" show up as the
    same log-loss gap, and short favourites are exactly where the margin is
    thinnest. Print it rather than let the ambiguity ride.
    """
    bands = ((1.0, 1.4), (1.4, 1.6), (1.6, 1.8), (1.8, 2.2), (2.2, 3.0),
             (3.0, 99.0))
    out = []
    for low, high in bands:
        band = [r for r in rows if low <= r["odds"] < high]
        if not band:
            continue
        out.append({
            "band": f"{low:g}-{high:g}",
            "n": len(band),
            "mean_overround": round(sum(r["overround"] for r in band) / len(band), 4),
            "hit_rate": round(sum(r["won"] for r in band) / len(band), 4),
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(PROJECT_DIR / "tennis_wc.db"))
    parser.add_argument("--max-odds", type=float, default=1.6,
                        help="cohort ceiling; 1.6 is where the gap was found")
    parser.add_argument("--tour", default=None, help="ATP / WTA; omit for all")
    parser.add_argument("--split-date", default="2026-07-15",
                        help="walk-forward boundary, fixed rather than tuned")
    parser.add_argument("--min-sample", type=int, default=MIN_SAMPLE)
    parser.add_argument("--report-overround", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    everything = _load(conn)
    conn.close()

    cohort = [r for r in everything if r["odds"] <= args.max_odds]
    if args.tour:
        cohort = [r for r in cohort if (r["tour"] or "") == args.tour]

    pooled = _paired_gap(cohort)
    report = {
        "cohort": {"max_odds": args.max_odds, "tour": args.tour or "ALL"},
        "corpus_total": len(everything),
        "pooled": pooled,
        "verdict": _verdict(pooled, args.min_sample),
        "walk_forward": _walk_forward(cohort, args.split_date),
        "baseline_all_prices": _paired_gap(everything),
    }
    if args.report_overround:
        report["overround_by_band"] = _overround_by_band(everything)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"cohort: odds <= {args.max_odds}, tour={args.tour or 'ALL'}")
    print(f"corpus: {len(everything)} settled fixtures, {pooled.get('n', 0)} in cohort")
    print()
    for label, block in (("cohort", pooled),
                         ("all prices (baseline)", report["baseline_all_prices"])):
        if not block.get("n"):
            continue
        print(f"  {label}")
        print(f"    model  log-loss {block['model_logloss']}")
        print(f"    market log-loss {block['market_logloss']}")
        print(f"    delta {block['delta_logloss']:+.5f} "
              f"CI [{block['ci_low']:+.5f}, {block['ci_high']:+.5f}] "
              f"P(model better)={block['probability_model_better']:.3f}")
    print()
    wf = report["walk_forward"]
    print(f"  walk-forward at {wf['split_date']}")
    for half in ("before", "after"):
        block = wf[half]
        if block.get("n"):
            print(f"    {half:6s} n={block['n']:4d} delta {block['delta_logloss']:+.5f} "
                  f"P={block['probability_model_better']:.3f}")
        else:
            print(f"    {half:6s} n=0")
    if args.report_overround:
        print()
        print("  book overround by price band (thin margin mimics a real edge)")
        for band in report["overround_by_band"]:
            print(f"    {band['band']:>8s} n={band['n']:4d} "
                  f"overround {band['mean_overround']:.4f} hit {band['hit_rate']:.3f}")
    print()
    print(f"  VERDICT: {report['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
