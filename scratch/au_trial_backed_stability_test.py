#!/usr/bin/env python3
"""Research shadow test: trial-backed stability compensation for lightly-raced horses.

Forensics (2026-07-17): market favourites that place but get ranked >3 by the
model lose to our picks on consistency (−11.0), stability (−9.9) and form
(−9.1) while WINNING on trial_score (+4.2) and jockey_score (+3.4) — i.e.
lightly-raced horses with strong trials are punished for having no history.

Candidate: for horses with formal_count <= F and trial_score > 60,
  mx_stability' = mx_stability + β · (trial_score − 60), capped at +C pts.
Ability recomputed through the live matrix weights. (β, C, F) selected per
fold on train positional-Good + any-2 Good; expanding-date walk-forward gate.
"""
from __future__ import annotations

import json
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

COUNTS = json.load(open("/Users/imac/Antigravity-repo/scratch/au_formal_count_map.json"))
BETAS = (0.2, 0.4, 0.6)
CAPS = (4.0, 8.0)
FORMALS = (1, 2)


def formal_count(row) -> int | None:
    key = f"{row['meeting']}|{row['race']}|{int(row['horse_number'])}"
    value = (COUNTS.get(key) or {}).get("formal")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def candidate_score(row, beta, cap, formal_max):
    stability = as_float(row.get("mx_stability"), 60.0)
    fc = formal_count(row)
    trial = as_float(row.get("trial_score"), 60.0)
    if fc is not None and fc <= formal_max and trial > 60.0:
        stability = stability + min(cap, beta * (trial - 60.0))
    score = 0.0
    for key in MATRIX_KEYS:
        value = stability if key == "stability" else as_float(row.get(f"mx_{key}"), 60.0)
        score += MATRIX_WEIGHTS.get(key, 0.0) * value
    return score


def baseline_score(row):
    return sum(MATRIX_WEIGHTS.get(key, 0.0) * as_float(row.get(f"mx_{key}"), 60.0) for key in MATRIX_KEYS)


def scored(races, scorer):
    return [[{**row, "_score": scorer(row)} for row in race] for race in races]


def main() -> int:
    races = group_races(materialize_dataset())
    folds = date_folds(races)

    # trigger support
    trig = 0
    for race in races:
        for row in race:
            fc = formal_count(row)
            if fc is not None and fc <= 2 and as_float(row.get("trial_score"), 60.0) > 60.0:
                trig += 1
    print(f"trigger support (formal<=2 & trial>60): {trig} horses across archive")

    all_base, all_cand = [], []
    report, non_worse = [], 0
    for idx, (train, valid) in enumerate(folds, 1):
        best, best_key = None, -1.0
        for beta in BETAS:
            for cap in CAPS:
                for fm in FORMALS:
                    m = metrics_for_races(scored(train, lambda r, b=beta, c=cap, f=fm: candidate_score(r, b, c, f)))
                    key = (m["good_positional"] + m["good"]) / max(1, m["races"])
                    if key > best_key:
                        best_key, best = key, (beta, cap, fm)
        beta, cap, fm = best
        vb = metrics_for_races(scored(valid, baseline_score))
        vc = metrics_for_races(scored(valid, lambda r: candidate_score(r, beta, cap, fm)))
        non_worse += vc["top3_precision"] >= vb["top3_precision"]
        report.append((idx, best, vb, vc))
        all_base.extend(scored(valid, baseline_score))
        all_cand.extend(scored(valid, lambda r: candidate_score(r, beta, cap, fm)))

    base = metrics_for_races(all_base)
    cand = metrics_for_races(all_cand)

    def fmt(m):
        return (f"{m['races']}R {m['gold']}G/{m['good']}g2/{m['good_positional']}gp/{m['miss']}M "
                f"Top3 {m['top3_precision']*100:.1f}% WinT3 {m['winner_in_top3']*100:.1f}% Top1 {m['top1_win']*100:.1f}%")

    for idx, params, vb, vc in report:
        print(f"fold {idx}: β,cap,formal={params} | gp {vb['good_positional']}→{vc['good_positional']} "
              f"g2 {vb['good']}→{vc['good']} miss {vb['miss']}→{vc['miss']}")
    print(f"baseline : {fmt(base)}")
    print(f"candidate: {fmt(cand)}")
    gp = (cand["good_positional"] - base["good_positional"]) / base["races"] * 100
    g2 = (cand["good"] - base["good"]) / base["races"] * 100
    print(f"lift: good-pos {gp:+.2f}pp, good-any2 {g2:+.2f}pp, miss Δ {cand['miss']-base['miss']:+d}, "
          f"folds {non_worse}/{len(folds)}")
    passed = (max(gp, g2) >= 1.5 and min(gp, g2) >= -0.5 and cand["miss"] <= base["miss"] and non_worse >= 4
              and (base["top1_win"] - cand["top1_win"]) * 100 <= 0.5
              and (base["winner_in_top3"] - cand["winner_in_top3"]) * 100 <= 0.5
              and (base["gold"] - cand["gold"]) / base["races"] * 100 <= 0.5)
    print("DECISION:", "PASS" if passed else "FAIL / HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
