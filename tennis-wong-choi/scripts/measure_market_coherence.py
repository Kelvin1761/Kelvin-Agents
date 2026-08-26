#!/usr/bin/env python3
"""Does the book disagree with itself by more than its own margin?

MEASUREMENT ONLY. Nothing reads this to place a bet.

THE IDEA, AND WHY IT WAS WORTH TESTING

Every other approach here tries to predict better than Sportsbet, and every one
loses: the match model is behind by Delta log-loss +0.0571 (CI [+0.0416,
+0.0730]) over 2,001 fixtures, and 9 of 11 prop families fit a market weight of
0.0000. The one hypothesis that does not require beating the book is that the
book contradicts ITSELF -- several markets on the same match are bound by
arithmetic, so if two of them imply different probabilities, one is wrong
without anyone needing to know which player is better.

Two identities are checkable from stored prices:

    P(A wins)          == P(A 2-0) + P(A 2-1)        [Match Betting / Set Betting]
    P(both win a set)  == P(A 2-1) + P(B 2-1)        [Yes-No / Set Betting]

THE ANSWER: REJECTED, AND STRUCTURALLY SO

A disagreement is only tradeable if it exceeds the margin you pay to act on it.
Measured on simultaneous captures, it is an order of magnitude smaller:

    identity                       median |disagreement|   margin   ratio
    Match Betting vs Set Betting            0.0149         0.0749   0.20x
    Both-win-a-set vs Set Betting           0.0064         0.0891   0.07x

The book is internally coherent to within a fifth of its own overround, which
is what you would expect from markets priced off one internal model. More data
does not fix a ratio -- this is a structural rejection, not an underpowered one.

WHAT THE POOLED NUMBERS LOOKED LIKE BEFORE THE SPLIT-HALF

Worth recording, because two intermediate results were encouraging and both
were wrong:

  * De-vigged with a fitted power exponent, the Set Betting market really is
    better informed than Match Betting: Delta log-loss -0.00517, 95% CI
    [-0.01021, -0.00067], P(SB better) = 0.990. Under PROPORTIONAL de-vig the
    same comparison reads P = 0.853 and does not clear. Power is the right
    method a priori for a 4-way market at 14% overround -- not chosen because
    it won -- but the pair is worth reporting together.
  * Split by date, the whole effect is in the earlier half: first half
    -0.01047 (CI [-0.01864, -0.00319], P=1.000), second half **+0.00012**
    (CI [-0.00508, +0.00509], P=0.470). A decayed edge, exactly the shape
    `prop_roi_report` grew its recency window for.

And the trade never had a sample: over 1,092 matches it fires on 33, because
the markets agree to 1.5pp while the margin is 7.5pp.

ONE MEASUREMENT TRAP THIS SCRIPT EXISTS TO AVOID

Comparing each market's EARLIEST snapshot suggests the Set Betting price is
captured ~22 hours later than Match Betting, which would make "better informed"
a time-travel artefact. It is not: Set Betting simply enters the scrape later in
a match's life, and once you look for an occasion carrying BOTH markets, all
1,092 matches have one within a minute. Pair by `fetched_at` occasion, never by
per-market MIN(id).

Usage:
    PYTHONPATH=src .venv/bin/python scripts/measure_market_coherence.py
    PYTHONPATH=src .venv/bin/python scripts/measure_market_coherence.py --json
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import random
import re
import sqlite3
import statistics
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

BOOTSTRAP_SEED = 20260826
BOOTSTRAP_RESAMPLES = 4000
# A disagreement below this fraction of the margin cannot be acted on whatever
# the sample size, which is the finding rather than a tuning knob.
TRADEABLE_RATIO = 1.0
_SCORELINE = re.compile(r"\d-\d\s*$")
_CLOSE_SCORELINE = re.compile(r"2-1\s*$")


def power_devig(odds: list[float]) -> list[float]:
    """Solve sum((1/o)^k) = 1 -- the margin model that fits a real book.

    Proportional de-vig (divide by the overround) assumes the margin is spread
    evenly, which it is not: it is loaded onto longshots. On a 4-way market at
    14% overround that mis-states the tail badly enough to invent a signal --
    under proportional de-vig this comparison selects 326 bets at average odds
    5.79, and under the power form it selects 69 at 3.77.
    """
    raw = [1.0 / o for o in odds]
    low, high = 0.5, 3.0
    for _ in range(120):
        k = (low + high) / 2
        if sum(r ** k for r in raw) > 1.0:
            low = k
        else:
            high = k
    k = (low + high) / 2
    return [r ** k for r in raw]


def _occasions(conn, market_names: tuple[str, ...]) -> dict:
    """Prices grouped by match and by SCRAPE OCCASION.

    Grouping by occasion rather than by per-market MIN(id) is the whole point;
    see the module docstring.
    """
    grouped: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    placeholders = ",".join("?" for _ in market_names)
    rows = conn.execute(
        f"""SELECT match_id, market_name, selection_name, selection_side, odds,
                   fetched_at
            FROM market_odds_snapshots
            WHERE match_id IS NOT NULL AND market_name IN ({placeholders})
            ORDER BY id""",
        market_names,
    ).fetchall()
    for row in rows:
        grouped[row["match_id"]][row["fetched_at"]][row["market_name"]].append(
            (row["selection_name"], row["selection_side"], row["odds"])
        )
    return grouped


def _results(conn) -> dict:
    return {
        row["match_id"]: row
        for row in conn.execute(
            """SELECT r.match_id, r.winner_player_id, m.player_a_id, m.match_date
               FROM match_results r JOIN matches m ON m.id = r.match_id
               WHERE r.winner_player_id IS NOT NULL"""
        ).fetchall()
    }


def _set_betting_legs(entries):
    """(player_a legs, player_b legs) for a Set Betting occasion, or None."""
    a = [(n, o) for n, s, o in entries if s == "player_a" and _SCORELINE.search(n or "")]
    b = [(n, o) for n, s, o in entries if s == "player_b" and _SCORELINE.search(n or "")]
    if not a or len(a) != len(b) or len(a) + len(b) not in (4, 6):
        return None
    return a, b


def match_versus_set_betting(conn) -> dict:
    """P(A wins) from Match Betting against P(A 2-0) + P(A 2-1)."""
    grouped = _occasions(conn, ("Match Betting", "Set Betting"))
    results = _results(conn)
    out = []
    for match_id, times in grouped.items():
        result = results.get(match_id)
        if not result:
            continue
        for stamp in sorted(times):
            markets = times[stamp]
            if "Match Betting" not in markets or "Set Betting" not in markets:
                continue
            winner = {s: o for _, s, o in markets["Match Betting"]
                      if s in ("player_a", "player_b")}
            if set(winner) != {"player_a", "player_b"}:
                continue
            legs = _set_betting_legs(markets["Set Betting"])
            if not legs:
                continue
            a_legs, b_legs = legs
            odds = [winner["player_a"], winner["player_b"]] + \
                [o for _, o in a_legs + b_legs]
            if min(odds) <= 1.0:
                continue
            p_match = power_devig([winner["player_a"], winner["player_b"]])[0]
            derived = power_devig([o for _, o in a_legs + b_legs])
            out.append({
                "match_id": match_id,
                "won": 1 if result["winner_player_id"] == result["player_a_id"] else 0,
                "anchor": p_match,
                "derived": sum(derived[:len(a_legs)]),
                "margin": 1.0 / winner["player_a"] + 1.0 / winner["player_b"] - 1.0,
                "odds_a": winner["player_a"],
                "odds_b": winner["player_b"],
                "match_date": result["match_date"],
            })
            break
    return {"name": "Match Betting vs Set Betting", "rows": out}


def both_win_a_set_versus_set_betting(conn) -> dict:
    """P(both win a set) against P(A 2-1) + P(B 2-1).

    No outcome column is graded here -- this identity is about coherence only,
    and `both players won a set` is not stored as a settled field.
    """
    name = "Both Players to win a Set (Yes/No)"
    grouped = _occasions(conn, (name, "Set Betting"))
    out = []
    for match_id, times in grouped.items():
        for stamp in sorted(times):
            markets = times[stamp]
            if name not in markets or "Set Betting" not in markets:
                continue
            yes_no = markets[name]
            if len(yes_no) != 2:
                continue
            try:
                yes = next(o for n, _, o in yes_no if "yes" in (n or "").lower())
                no = next(o for n, _, o in yes_no if "no" in (n or "").lower())
            except StopIteration:
                continue
            legs = _set_betting_legs(markets["Set Betting"])
            if not legs:
                continue
            a_legs, b_legs = legs
            every = [yes, no] + [o for _, o in a_legs + b_legs]
            if min(every) <= 1.0:
                continue
            fair = power_devig([o for _, o in a_legs + b_legs])
            close = sum(p for (leg_name, _), p in zip(a_legs + b_legs, fair)
                        if _CLOSE_SCORELINE.search(leg_name or ""))
            if close <= 0:
                continue
            out.append({
                "match_id": match_id,
                "won": None,
                "anchor": power_devig([yes, no])[0],
                "derived": close,
                "margin": 1.0 / yes + 1.0 / no - 1.0,
                "odds_a": None, "odds_b": None, "match_date": None,
            })
            break
    return {"name": "Both-win-a-set vs Set Betting", "rows": out}


def _log_loss(probability: float, won: int) -> float:
    p = min(max(probability, 1e-9), 1 - 1e-9)
    return -(won * math.log(p) + (1 - won) * math.log(1 - p))


def _paired(diffs: list[float], rng: random.Random) -> dict:
    n = len(diffs)
    if not n:
        return {"n": 0}
    means = sorted(sum(rng.choice(diffs) for _ in range(n)) / n
                   for _ in range(BOOTSTRAP_RESAMPLES))
    return {
        "n": n,
        "delta_logloss": round(sum(diffs) / n, 5),
        "ci_low": round(means[int(0.025 * BOOTSTRAP_RESAMPLES)], 5),
        "ci_high": round(means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1], 5),
        "probability_derived_better": round(
            sum(1 for m in means if m < 0) / len(means), 4),
    }


def coherence(identity: dict) -> dict:
    """The only number that decides this: disagreement against the margin."""
    rows = identity["rows"]
    if not rows:
        return {"identity": identity["name"], "n": 0}
    gaps = sorted(abs(r["derived"] - r["anchor"]) for r in rows)
    median_gap = gaps[len(gaps) // 2]
    margin = statistics.mean(r["margin"] for r in rows)
    report = {
        "identity": identity["name"],
        "n": len(rows),
        "median_disagreement": round(median_gap, 5),
        "p99_disagreement": round(gaps[int(0.99 * len(gaps)) - 1], 5),
        "mean_margin": round(margin, 5),
        "ratio_to_margin": round(median_gap / margin, 3) if margin else None,
    }
    report["tradeable"] = bool(
        report["ratio_to_margin"] and report["ratio_to_margin"] >= TRADEABLE_RATIO)
    graded = [r for r in rows if r["won"] is not None]
    if graded:
        rng = random.Random(BOOTSTRAP_SEED)
        diffs = [_log_loss(r["derived"], r["won"]) - _log_loss(r["anchor"], r["won"])
                 for r in graded]
        report["pooled"] = _paired(diffs, rng)
        dated = sorted((r for r in graded if r["match_date"]),
                       key=lambda r: r["match_date"])
        if len(dated) >= 200:
            half = len(dated) // 2
            for label, part in (("first_half", dated[:half]),
                                ("second_half", dated[half:])):
                report[label] = _paired(
                    [_log_loss(r["derived"], r["won"]) - _log_loss(r["anchor"], r["won"])
                     for r in part], random.Random(BOOTSTRAP_SEED))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(PROJECT_DIR / "tennis_wc.db"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    reports = [coherence(match_versus_set_betting(conn)),
               coherence(both_win_a_set_versus_set_betting(conn))]
    conn.close()

    if args.json:
        print(json.dumps(reports, indent=2))
        return 0

    print("Does the book disagree with itself by more than its own margin?\n")
    for report in reports:
        if not report.get("n"):
            print(f"  {report['identity']}: no paired captures")
            continue
        print(f"  {report['identity']}  (n={report['n']})")
        print(f"    median |disagreement| {report['median_disagreement']:.4f}"
              f"   p99 {report['p99_disagreement']:.4f}")
        print(f"    margin to beat        {report['mean_margin']:.4f}")
        print(f"    ratio                 {report['ratio_to_margin']:.2f}x"
              f"   tradeable={report['tradeable']}")
        if "pooled" in report:
            for label in ("pooled", "first_half", "second_half"):
                block = report.get(label)
                if not block or not block.get("n"):
                    continue
                print(f"    {label:12s} n={block['n']:4d} "
                      f"delta {block['delta_logloss']:+.5f} "
                      f"CI [{block['ci_low']:+.5f}, {block['ci_high']:+.5f}] "
                      f"P={block['probability_derived_better']:.3f}")
        print()
    print("  A disagreement smaller than the margin cannot be acted on at any")
    print("  sample size. Both identities sit at a fifth of it or less.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
