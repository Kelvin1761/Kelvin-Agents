#!/usr/bin/env python3
"""How long until the edge is provable -- and can the wait be shortened?

MEASUREMENT ONLY. Nothing reads this to decide a bet.

WHY THIS REPLACED "GET A BETTER PRICE"

The plan had a second price source as the structural lever: level with the
market plus a 7.5% takeout loses, level plus a 2-5% exchange commission is
marginally viable. Measured, that premise is wrong.

Flat-betting the model's own EV>0 selections on the tier-bettable population, at
Sportsbet's ACTUAL prices:

    Sportsbet (7.5% overround)        n=679  ROI  +4.76%  [ -5.42, +15.72]
    fair price less 5% commission     n=782       +6.36%  [ -3.60, +16.57]
    fair price less 2% commission     n=819       +7.76%  [ -1.91, +17.00]
    fair price, zero takeout          n=837       +8.14%  [ -1.15, +18.06]

Break-even commission is about 13%. So the price was never the binding
constraint -- an exchange buys roughly 3 points of ROI and changes nothing about
whether the number is real. Every interval still crosses zero.

The tier gate is what separates: tier-bettable +4.33% against non-bettable
-7.44%, and the input-completeness filter adds almost nothing on top (+4.76%),
so this is not an artefact of selecting on today's `rankings_history`.

WHAT BINDS INSTEAD

As of 2026-08-29 this script reports n=686, ROI +6.12%, CI [-5.12, +16.87], and
a per-bet standard deviation of 1.467. Against a fixed 5% assumed edge that
needs 3,306 bets, so 2,620 more -- about 9.4 months at August's rate of 280, and
the rate is climbing (57, 144, 205, 280).

That is the whole remaining question, so this script measures it directly and is
meant to be re-run monthly. It also asks whether the wait can be shortened:
required n scales with variance, and variance comes from the odds distribution.
Measured, it does, up to a point -- capping at odds 3.0 needs 1,626 bets against
3,306 unrestricted, which is 6.6 months against 9.4 even after the lost volume,
and above 3.0 the trade reverses.

The production odds gate is deliberately NOT tightened on that basis. Proving
the edge sooner is not the same as earning more -- the odds<=3.0 band's own ROI
(+4.80%) is below the unrestricted figure -- and nothing here justifies changing
what the card offers. Track both; change behaviour only for a measured gain.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/measure_edge_significance.py
    PYTHONPATH=src .venv/bin/python scripts/measure_edge_significance.py --json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import statistics
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

import sqlite3  # noqa: E402

from tennis_wc.props.daily import _tier_bettable  # noqa: E402

BOOTSTRAP_SEED = 20260829
BOOTSTRAP_RESAMPLES = 3000
MIN_SAMPLE = 40
Z_95 = 1.96

# Earliest snapshot per match: 2,925 snapshots were fetched after their match
# day and one selection ranged 1.26 to 41.0, so anything else prices the bet
# with the result partly known.
_SQL = """
WITH first_odds AS (
    SELECT match_id, MIN(id) AS snapshot_id
    FROM odds_snapshots
    WHERE match_id IS NOT NULL AND market = 'match_winner'
    GROUP BY match_id
)
SELECT p.id AS prediction_id, p.match_id, p.selection_player_id, p.model_probability,
       m.match_date, m.player_a_id, m.player_b_id, r.winner_player_id,
       o.player_a_odds, o.player_b_odds, t.name AS tournament_name,
       (SELECT tl.level FROM tournament_levels tl
         WHERE tl.tournament_id = m.tournament_id
         ORDER BY tl.id DESC LIMIT 1) AS level
FROM predictions p
JOIN matches m ON m.id = p.match_id
JOIN match_results r ON r.match_id = p.match_id
JOIN first_odds f ON f.match_id = p.match_id
JOIN odds_snapshots o ON o.id = f.snapshot_id
LEFT JOIN tournaments t ON t.id = m.tournament_id
WHERE p.model_probability IS NOT NULL AND r.winner_player_id IS NOT NULL
ORDER BY p.id
"""


def load(conn) -> list[dict]:
    """One bet per (match, selection): the model's EV>0 picks at the open."""
    latest: dict[tuple[int, int], sqlite3.Row] = {}
    for row in conn.execute(_SQL).fetchall():
        latest[(row["match_id"], row["selection_player_id"])] = row
    bets = []
    for row in latest.values():
        if not _tier_bettable(row["tournament_name"], row["level"]):
            continue
        selection = row["selection_player_id"]
        if selection == row["player_a_id"]:
            odds, opponent = row["player_a_odds"], row["player_b_odds"]
        elif selection == row["player_b_id"]:
            odds, opponent = row["player_b_odds"], row["player_a_odds"]
        else:
            continue
        if not odds or not opponent or odds <= 1 or opponent <= 1:
            continue
        if row["model_probability"] * odds - 1 <= 0:
            continue
        bets.append({
            "date": row["match_date"],
            "odds": float(odds),
            "pnl": (float(odds) - 1) if row["winner_player_id"] == selection else -1.0,
        })
    bets.sort(key=lambda b: b["date"])
    return bets


# The effect size `required_n` is computed against, fixed here rather than read
# from each subset's own ROI.
#
# The first version used the subset's observed mean, and `(1.96 sd / mean)^2` is
# so sensitive to a noisy mean that the table became unreadable: odds<=5.0 came
# out needing 839 bets ("one month!") while odds<=3.0 -- a subset of it --
# needed 1,766. That is not a finding about variance, it is each band's ROI
# noise squared and inverted, and it invites exactly the cherry-picking this
# file exists to prevent. With the effect fixed, bands differ only by variance,
# which is the actual question.
ASSUMED_ROI = 0.05


def summarise(bets: list[dict], assumed_roi: float = ASSUMED_ROI) -> dict:
    """ROI, its interval, and the sample size that would make it provable.

    `required_n` assumes `assumed_roi`, not the observed mean. Even so it is a
    floor on the wait rather than a forecast: an effect estimated on a small
    sample is more often overstated than understated, so a 5% assumption may
    already be generous.
    """
    n = len(bets)
    if n < MIN_SAMPLE:
        return {"n": n}
    pnl = [b["pnl"] for b in bets]
    mean = sum(pnl) / n
    sd = statistics.pstdev(pnl)
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(
        sum(rng.choice(pnl) for _ in range(n)) / n
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    lo = means[int(0.025 * BOOTSTRAP_RESAMPLES)]
    hi = means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]
    required = (Z_95 * sd / assumed_roi) ** 2 if assumed_roi > 0 else None
    return {
        "n": n,
        "roi_pct": round(mean * 100, 3),
        "ci_low_pct": round(lo * 100, 3),
        "ci_high_pct": round(hi * 100, 3),
        "significant": bool(lo > 0),
        "per_bet_sd": round(sd, 4),
        "mean_odds": round(sum(b["odds"] for b in bets) / n, 3),
        "assumed_roi_pct": round(assumed_roi * 100, 2),
        "required_n": None if required is None else round(required),
        "bets_still_needed": None if required is None else max(0, round(required) - n),
    }


def monthly_rate(bets: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for b in bets:
        counts[b["date"][:7]] = counts.get(b["date"][:7], 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(PROJECT_DIR / "tennis_wc.db"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    bets = load(conn)
    conn.close()

    rate = monthly_rate(bets)
    latest_rate = list(rate.values())[-1] if rate else 0
    report = {
        "monthly_bets": rate,
        "all": summarise(bets),
        "by_odds_ceiling": {},
    }
    # Variance, not edge, is what sets the wait. A shorter-odds subset bets less
    # often and each bet carries less variance, so it can prove itself sooner.
    for ceiling in (1.5, 1.8, 2.2, 3.0, 5.0, 99.0):
        report["by_odds_ceiling"][str(ceiling)] = summarise(
            [b for b in bets if b["odds"] <= ceiling]
        )

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    a = report["all"]
    print(f"tier-bettable, model EV>0, earliest price: n={a['n']}")
    print(f"  ROI {a['roi_pct']:+.2f}%  95% CI [{a['ci_low_pct']:+.2f}, "
          f"{a['ci_high_pct']:+.2f}]  {'SIGNIFICANT' if a['significant'] else 'crosses zero'}")
    print(f"  per-bet SD {a['per_bet_sd']}  mean odds {a['mean_odds']}")
    print(f"  monthly: " + "  ".join(f"{k} {v}" for k, v in rate.items()))
    print()
    print(f"  restricting the odds trades bet volume for variance."
          f"  `need n` assumes a fixed {ASSUMED_ROI:.0%} edge in every band,")
    print("  so the bands differ only by variance rather than by their own ROI noise:")
    print(f"  {'odds <=':>8s} {'n':>5s} {'ROI':>8s} {'SD':>6s} {'need n':>8s} "
          f"{'still need':>11s} {'months at last rate':>20s}")
    for ceiling, r in report["by_odds_ceiling"].items():
        if "roi_pct" not in r:
            print(f"  {ceiling:>8s} {r['n']:5d}   too few")
            continue
        share = (r["n"] / a["n"]) if a["n"] else 0
        month_rate = latest_rate * share
        months = (r["bets_still_needed"] / month_rate) if (
            r["bets_still_needed"] and month_rate > 0) else 0
        need = r["required_n"] if r["required_n"] is not None else 0
        print(f"  {ceiling:>8s} {r['n']:5d} {r['roi_pct']:+8.2f} {r['per_bet_sd']:6.3f} "
              f"{need:8,d} {r['bets_still_needed'] or 0:11,d} {months:20.1f}")
    print()
    print(f"  a {ASSUMED_ROI:.0%} assumption is already generous: a small-sample effect is")
    print("  more often overstated than understated, so these are floors on the wait.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
