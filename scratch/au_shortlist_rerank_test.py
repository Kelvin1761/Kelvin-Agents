#!/usr/bin/env python3
"""Research shadow test: two-stage shortlist re-rank.

Stage 1 (unchanged): rank by production ability_score, take top-K shortlist.
Stage 2: re-rank the shortlist by ability + λ · (d̂ · centered matrix scores),
where the direction d̂ is learned PER FOLD from train races only (mean matrix
deltas of placegetters vs non-placegetters within the train top-4s), and
(K, λ) are selected per fold by train positional-Good. Honest expanding-date
walk-forward: nothing from the valid window leaks into the choice.

Motivation: 40% of races have >=2 placegetters inside the model top-4 but not
as picks 1+2; within the top-4 the placegetters win on class_weight /
race_shape / jockey_trainer and lose on stability.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

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

LAMBDAS = (0.0, 0.05, 0.10, 0.20, 0.30, 0.50)
KS = (4, 5)


def ability_ranked(race):
    return sorted(race, key=lambda r: (-as_float(r["ability_score"], 60.0), int(r["horse_number"])))


def learn_direction(train_races) -> dict[str, float]:
    deltas = defaultdict(list)
    for race in train_races:
        top4 = ability_ranked(race)[:4]
        hit = [r for r in top4 if int(r["actual_pos"]) <= 3]
        non = [r for r in top4 if int(r["actual_pos"]) > 3]
        if len(hit) < 2 or not non:
            continue
        for key in MATRIX_KEYS:
            deltas[key].append(
                mean(as_float(r.get(f"mx_{key}"), 60.0) for r in hit)
                - mean(as_float(r.get(f"mx_{key}"), 60.0) for r in non)
            )
    direction = {key: mean(values) for key, values in deltas.items() if values}
    norm = sum(abs(v) for v in direction.values()) or 1.0
    return {key: value / norm for key, value in direction.items()}


def rerank_race(race, direction, lam, k):
    ranked = ability_ranked(race)
    shortlist, rest = ranked[:k], ranked[k:]
    def stage2(row):
        adj = sum(direction.get(key, 0.0) * (as_float(row.get(f"mx_{key}"), 60.0) - 60.0)
                  for key in MATRIX_KEYS)
        return as_float(row["ability_score"], 60.0) + lam * adj
    shortlist = sorted(shortlist, key=lambda r: (-stage2(r), int(r["horse_number"])))
    return shortlist + rest


def scored_with(races, direction, lam, k):
    out = []
    for race in races:
        order = rerank_race(race, direction, lam, k)
        n = len(order)
        out.append([{**row, "_score": float(n - idx)} for idx, row in enumerate(order)])
    return out


def scored_baseline(races):
    return [[{**row, "_score": as_float(row["ability_score"], 60.0)} for row in race] for race in races]


def gp_rate(m):
    return m["good_positional"] / max(1, m["races"])


def main() -> int:
    races = group_races(materialize_dataset())
    folds = date_folds(races)

    all_valid_base, all_valid_cand = [], []
    fold_report = []
    for idx, (train, valid) in enumerate(folds, 1):
        direction = learn_direction(train)
        best, best_score = (0.0, 4), -1.0
        for lam in LAMBDAS:
            for k in KS:
                m = metrics_for_races(scored_with(train, direction, lam, k))
                score = gp_rate(m)
                if score > best_score:
                    best_score, best = score, (lam, k)
        lam, k = best
        vb = metrics_for_races(scored_baseline(valid))
        vc = metrics_for_races(scored_with(valid, direction, lam, k))
        fold_report.append((idx, lam, k, vb, vc))
        all_valid_base.extend(scored_baseline(valid))
        all_valid_cand.extend(scored_with(valid, direction, lam, k))

    base = metrics_for_races(all_valid_base)
    cand = metrics_for_races(all_valid_cand)

    def fmt(m):
        return (f"{m['races']}R {m['gold']}G/{m['good']}g2/{m['good_positional']}gp/{m['miss']}M "
                f"Top3 {m['top3_precision']*100:.1f}% WinT3 {m['winner_in_top3']*100:.1f}% Top1 {m['top1_win']*100:.1f}%")

    print("per-fold (train-selected λ, K):")
    non_worse = 0
    for idx, lam, k, vb, vc in fold_report:
        non_worse += vc["top3_precision"] >= vb["top3_precision"]
        print(f"  fold {idx}: λ={lam:.2f} K={k} | gp {vb['good_positional']}→{vc['good_positional']} "
              f"| miss {vb['miss']}→{vc['miss']} | top1 {vb['top1_win']*100:.1f}%→{vc['top1_win']*100:.1f}%")
    print(f"baseline : {fmt(base)}")
    print(f"candidate: {fmt(cand)}")
    gp_lift = (cand["good_positional"] - base["good_positional"]) / base["races"] * 100
    g2_lift = (cand["good"] - base["good"]) / base["races"] * 100
    print(f"lift: good-pos {gp_lift:+.2f}pp, good-any2 {g2_lift:+.2f}pp, miss Δ {cand['miss']-base['miss']:+d}, "
          f"top1 Δ {(cand['top1_win']-base['top1_win'])*100:+.2f}pp, folds top3 non-worse {non_worse}/{len(folds)}")
    passed = (gp_lift >= 1.5 and g2_lift >= -0.5 and cand["miss"] <= base["miss"] and non_worse >= 4
              and (base["top1_win"] - cand["top1_win"]) * 100 <= 0.5
              and (base["winner_in_top3"] - cand["winner_in_top3"]) * 100 <= 0.5
              and (base["gold"] - cand["gold"]) / base["races"] * 100 <= 0.5)
    print("DECISION:", "PASS" if passed else "FAIL / HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
