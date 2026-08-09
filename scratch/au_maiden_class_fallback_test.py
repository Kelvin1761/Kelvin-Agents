#!/usr/bin/env python3
"""Research shadow test: maiden-aware class_weight fallback.

In maidens most runners have no official rating, so `class_weight`
(0.159 class + 0.70 rating + 0.141 weight) collapses toward 60 and the
dimension is near-dead weight. Candidate: when a horse's rating_score is the
60.0 default, redistribute the rating share proportionally to class_score and
weight_score. Everything else unchanged; ability recomputed through the live
matrix with only class_weight replaced. Baseline = plain reconstruction.

Gate: Phase-5 rules (good any-2 >= +1.5pp OOS, losses <= 0.5pp, miss
non-regression, Top3 fold stability >= 4/5).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")

from au_archive_calibrator import MATRIX_KEYS  # noqa: E402
from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
    metrics_for_races,
)
from scoring import MATRIX_WEIGHTS  # noqa: E402

CW = {"class_score": 0.159, "rating_score": 0.70, "weight_score": 0.141}
HEADERS = json.load(open("/Users/imac/Antigravity-repo/scratch/au_racecard_headers.json"))


def is_maiden(race: list[dict]) -> bool:
    header = HEADERS.get(f"{race[0]['meeting']}|{race[0]['race']}", "")
    return "MAIDEN" in header.upper() or "MDN" in header.upper()


def class_weight_value(row: dict, fallback: bool) -> float:
    rating = as_float(row.get("rating_score"), 60.0)
    if not fallback or abs(rating - 60.0) > 1e-9:
        return sum(w * as_float(row.get(k), 60.0) for k, w in CW.items())
    # redistribute the rating share to class + weight proportionally
    rest = CW["class_score"] + CW["weight_score"]
    total = sum(CW.values())
    return total * (
        as_float(row.get("class_score"), 60.0) * (CW["class_score"] / rest)
        + as_float(row.get("weight_score"), 60.0) * (CW["weight_score"] / rest)
    )


def reconstruction(row: dict, cw_value: float | None) -> float:
    score = 0.0
    for key in MATRIX_KEYS:
        value = cw_value if (key == "class_weight" and cw_value is not None) else as_float(
            row.get(f"mx_{key}"), 60.0)
        score += MATRIX_WEIGHTS.get(key, 0.0) * value
    return score


def scored(races, mode):
    out = []
    for race in races:
        maiden = is_maiden(race)
        rows = []
        for row in race:
            if mode == "baseline":
                cw = None
            elif mode == "all":
                cw = class_weight_value(row, fallback=True)
            else:  # maiden-only
                cw = class_weight_value(row, fallback=True) if maiden else None
            rows.append({**row, "_score": reconstruction(row, cw)})
        out.append(rows)
    return out


def fmt(m):
    return (f"{m['races']}R {m['gold']}G/{m['good']}g2/{m['good_positional']}gp/{m['miss']}M "
            f"Top3 {m['top3_precision']*100:.1f}% WinT3 {m['winner_in_top3']*100:.1f}% Top1 {m['top1_win']*100:.1f}%")


def main() -> int:
    races = group_races(materialize_dataset())
    folds = date_folds(races)
    valid = [race for _t, v in folds for race in v]
    maiden_valid = [race for race in valid if is_maiden(race)]
    print(f"OOS races {len(valid)}, maiden OOS races {len(maiden_valid)}")
    baseline = metrics_for_races(scored(valid, "baseline"))
    print(f"baseline     : {fmt(baseline)}")
    for mode in ("maiden-only", "all"):
        cand = metrics_for_races(scored(valid, mode))
        non_worse = 0
        for _t, v in folds:
            fb = metrics_for_races(scored(v, "baseline"))
            fc = metrics_for_races(scored(v, mode))
            non_worse += fc["top3_precision"] >= fb["top3_precision"]
        good_lift = (cand["good"] - baseline["good"]) / baseline["races"] * 100
        gp_lift = (cand["good_positional"] - baseline["good_positional"]) / baseline["races"] * 100
        mb = metrics_for_races(scored(maiden_valid, "baseline"))
        mc = metrics_for_races(scored(maiden_valid, mode))
        print(f"{mode:<13}: {fmt(cand)}")
        print(f"  lift: good {good_lift:+.2f}pp, good-pos {gp_lift:+.2f}pp, miss Δ {cand['miss']-baseline['miss']:+d}, "
              f"folds {non_worse}/{len(folds)} | maiden-only slice: "
              f"gp {mb['good_positional']}→{mc['good_positional']}, miss {mb['miss']}→{mc['miss']} (n={mb['races']})")
        passed = (good_lift >= 1.5 and cand["miss"] <= baseline["miss"] and non_worse >= 4
                  and (baseline["top1_win"] - cand["top1_win"]) * 100 <= 0.5
                  and (baseline["winner_in_top3"] - cand["winner_in_top3"]) * 100 <= 0.5
                  and (baseline["gold"] - cand["gold"]) / baseline["races"] * 100 <= 0.5)
        print(f"  DECISION: {'PASS' if passed else 'FAIL / HOLD'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
