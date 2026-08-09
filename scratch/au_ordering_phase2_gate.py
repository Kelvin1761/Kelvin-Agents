#!/usr/bin/env python3
"""Ordering-features Phase 2: walk-forward gate for the surviving features.

Candidate (Option B): stage-2 re-rank of the ability top-K by
    score2 = ability + λ · (F2_last + β · F1_h2h)
with (λ, β, K) selected per fold on train positional-Good only.
F3/F4 killed in Phase 1 (no stable OOS delta).

Gate: positional Good >= +1.5pp OOS aggregate, any-2 Good >= -0.5pp, Miss
non-regression, Gold/Top1/W-in-T3 >= -0.5pp, Top3 fold stability >= 4/5.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo/scratch")
import au_ordering_phase1 as p1  # noqa: E402  (reuses RAW, h2h_and_quality, decay)

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
    metrics_for_races,
)

LAMBDAS = (0.0, 0.2, 0.5, 1.0)
BETAS = (0.0, 0.5, 1.0)
K = 4


def annotate(races):
    """Precompute F1/F2 per horse for its race context (top-4 rivals)."""
    for race in races:
        meeting_date = str(race[0]["date"])
        ranked = sorted(race, key=lambda r: (-as_float(r["ability_score"], 60.0), int(r["horse_number"])))
        top4 = ranked[:4]
        names = {}
        for r in top4:
            key = f"{r['meeting']}|{r['race']}|{int(r['horse_number'])}"
            info = p1.RAW.get(key) or {}
            if info.get("name"):
                names[info["name"]] = r
        for r in race:
            key = f"{r['meeting']}|{r['race']}|{int(r['horse_number'])}"
            f1, f2, _f4 = p1.h2h_and_quality(key, meeting_date, names)
            r["_f1"], r["_f2"] = f1, f2
    return races


def scored(races, lam, beta):
    out = []
    for race in races:
        ranked = sorted(race, key=lambda r: (-as_float(r["ability_score"], 60.0), int(r["horse_number"])))
        shortlist, rest = ranked[:K], ranked[K:]
        shortlist = sorted(
            shortlist,
            key=lambda r: (-(as_float(r["ability_score"], 60.0) + lam * (r["_f2"] + beta * r["_f1"])),
                           int(r["horse_number"])),
        )
        order = shortlist + rest
        n = len(order)
        out.append([{**row, "_score": float(n - idx)} for idx, row in enumerate(order)])
    return out


def main() -> int:
    races = annotate(group_races(materialize_dataset()))
    folds = date_folds(races)
    all_base, all_cand, non_worse, report = [], [], 0, []
    for idx, (train, valid) in enumerate(folds, 1):
        best, best_gp = (0.0, 0.0), -1.0
        for lam in LAMBDAS:
            for beta in BETAS:
                m = metrics_for_races(scored(train, lam, beta))
                gp = m["good_positional"] / max(1, m["races"])
                if gp > best_gp:
                    best_gp, best = gp, (lam, beta)
        lam, beta = best
        vb = metrics_for_races(scored(valid, 0.0, 0.0))
        vc = metrics_for_races(scored(valid, lam, beta))
        non_worse += vc["top3_precision"] >= vb["top3_precision"]
        report.append((idx, lam, beta, vb, vc))
        all_base.extend(scored(valid, 0.0, 0.0))
        all_cand.extend(scored(valid, lam, beta))

    base = metrics_for_races(all_base)
    cand = metrics_for_races(all_cand)

    def fmt(m):
        return (f"{m['races']}R {m['gold']}G/{m['good']}g2/{m['good_positional']}gp/{m['miss']}M "
                f"Top3 {m['top3_precision']*100:.1f}% WinT3 {m['winner_in_top3']*100:.1f}% Top1 {m['top1_win']*100:.1f}%")

    for idx, lam, beta, vb, vc in report:
        print(f"fold {idx}: λ={lam} β={beta} | gp {vb['good_positional']}→{vc['good_positional']} "
              f"g2 {vb['good']}→{vc['good']} miss {vb['miss']}→{vc['miss']} "
              f"top1 {vb['top1_win']*100:.1f}%→{vc['top1_win']*100:.1f}%")
    print(f"baseline : {fmt(base)}")
    print(f"candidate: {fmt(cand)}")
    gp = (cand["good_positional"] - base["good_positional"]) / base["races"] * 100
    g2 = (cand["good"] - base["good"]) / base["races"] * 100
    print(f"lift: good-pos {gp:+.2f}pp, good-any2 {g2:+.2f}pp, miss Δ {cand['miss']-base['miss']:+d}, "
          f"top1 Δ {(cand['top1_win']-base['top1_win'])*100:+.2f}pp, folds {non_worse}/{len(folds)}")
    passed = (gp >= 1.5 and g2 >= -0.5 and cand["miss"] <= base["miss"] and non_worse >= 4
              and (base["top1_win"] - cand["top1_win"]) * 100 <= 0.5
              and (base["winner_in_top3"] - cand["winner_in_top3"]) * 100 <= 0.5
              and (base["gold"] - cand["gold"]) / base["races"] * 100 <= 0.5)
    print("DECISION:", "PASS" if passed else "FAIL / HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
