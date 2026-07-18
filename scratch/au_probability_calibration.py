#!/usr/bin/env python3
"""Round-7 Part 3: probability calibration + betting reference card.

Maps (model rank, confidence tier) → calibrated win% / top-3% with
walk-forward honesty: each fold's probabilities are estimated from TRAIN
races only and evaluated on the fold's valid races; the report shows both
the calibrated estimate and the OOS realization, plus fair odds (1/p).

Odds never enter the model — this table is for comparing against market
prices at bet time (value betting), and for race selection (which tiers and
ranks are worth playing at all).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
)

TIERS = ("tight", "medium", "clear")
RANKS = (1, 2, 3, 4, 5)


def tier_of(race) -> str:
    scores = sorted((as_float(r["ability_score"], 60.0) for r in race), reverse=True)
    gap = scores[0] - scores[2] if len(scores) >= 3 else 99.0
    return "tight" if gap < 2.0 else ("medium" if gap < 5.0 else "clear")


def tally(races) -> dict:
    counts = defaultdict(lambda: [0, 0, 0])  # (tier, rank) -> [n, wins, top3]
    for race in races:
        tier = tier_of(race)
        ranked = sorted(race, key=lambda r: (-as_float(r["ability_score"], 60.0), int(r["horse_number"])))
        for rank, row in enumerate(ranked[:5], 1):
            c = counts[(tier, rank)]
            c[0] += 1
            c[1] += int(row["actual_pos"]) == 1
            c[2] += int(row["actual_pos"]) <= 3
    return counts


def main() -> int:
    races = group_races(materialize_dataset())
    folds = date_folds(races)

    train_est = defaultdict(lambda: [0, 0, 0])
    valid_real = defaultdict(lambda: [0, 0, 0])
    for train, valid in folds:
        for key, (n, w, t3) in tally(train).items():
            agg = train_est[key]
            agg[0] += n; agg[1] += w; agg[2] += t3
        for key, (n, w, t3) in tally(valid).items():
            agg = valid_real[key]
            agg[0] += n; agg[1] += w; agg[2] += t3

    print("(train-calibrated vs OOS realized; fair odds = 1/train-win%)")
    print(f"{'tier':<8}{'rank':>5}{'n(OOS)':>8}{'win% cal':>9}{'win% OOS':>9}{'fairOdds':>9}{'top3% cal':>10}{'top3% OOS':>10}{'fairPlc':>8}")
    for tier in TIERS:
        for rank in RANKS:
            tn, tw, tt3 = train_est[(tier, rank)]
            vn, vw, vt3 = valid_real[(tier, rank)]
            if tn == 0 or vn == 0:
                continue
            wc, wt = tw / tn, tt3 / tn
            print(f"{tier:<8}{rank:>5}{vn:>8}{100*wc:>8.1f}%{100*vw/vn:>8.1f}%"
                  f"{(1/wc if wc else 0):>9.1f}{100*wt:>9.1f}%{100*vt3/vn:>9.1f}%{(1/wt if wt else 0):>8.1f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
