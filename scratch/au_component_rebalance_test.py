#!/usr/bin/env python3
"""Round-7: intra-dimension component rebalancing on refreshed evidence.

The component splits inside each matrix dimension were calibrated in the
blind era (form/trial/health ~100% default). Post-refresh per-feature audit
(2026-07-17b): pace_figure separates 6.49 when present but is default 67%
of the time (and holds 75.9% of pace_perf); jockey_horse_fit separates 0.47
yet holds 52% of jockey_trainer; weight_score separates NEGATIVELY (−0.41);
consistency (4.18) out-separates form (3.32) inside stability.

Candidates (each tested in isolation, per-fold train-only grid, standard gate):
  P1 pace_perf coverage-adaptive: when pace_figure is default, redistribute
     its 0.759 to sectional/trial; otherwise unchanged.
  S1 stability split grid: (form, consistency) ∈ {(.6,.4),(.5,.5),(.4,.6)}.
  J1 jockey_trainer grid: (jockey, trainer, fit) ∈ current / (.45,.25,.30) / (.40,.20,.40).
  C1 class_weight: drop weight_score → (class .186, rating .814, weight 0).

Recompute fidelity vs stored mx_* is validated before testing.
"""
from __future__ import annotations

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

CURRENT = {
    "stability": (("form_score", 0.60), ("consistency_score", 0.40)),
    "pace_perf": (("pace_figure_score", 0.759174), ("sectional_score", 0.193864), ("trial_score", 0.046962)),
    "jockey_trainer": (("jockey_score", 0.28), ("trainer_score", 0.20), ("jockey_horse_fit_score", 0.52)),
    "class_weight": (("class_score", 0.159), ("rating_score", 0.70), ("weight_score", 0.141)),
}

GRIDS = {
    "S1 stability": ("stability", [
        (("form_score", 0.60), ("consistency_score", 0.40)),
        (("form_score", 0.50), ("consistency_score", 0.50)),
        (("form_score", 0.40), ("consistency_score", 0.60)),
    ]),
    "J1 jockey_trainer": ("jockey_trainer", [
        (("jockey_score", 0.28), ("trainer_score", 0.20), ("jockey_horse_fit_score", 0.52)),
        (("jockey_score", 0.45), ("trainer_score", 0.25), ("jockey_horse_fit_score", 0.30)),
        (("jockey_score", 0.40), ("trainer_score", 0.20), ("jockey_horse_fit_score", 0.40)),
    ]),
    "C1 class_weight": ("class_weight", [
        (("class_score", 0.159), ("rating_score", 0.70), ("weight_score", 0.141)),
        (("class_score", 0.186), ("rating_score", 0.814), ("weight_score", 0.0)),
        (("class_score", 0.30), ("rating_score", 0.70), ("weight_score", 0.0)),
    ]),
}

PACE_FALLBACKS = [
    None,  # unchanged
    (("pace_figure_score", 0.0), ("sectional_score", 0.80), ("trial_score", 0.20)),
    (("pace_figure_score", 0.0), ("sectional_score", 0.60), ("trial_score", 0.40)),
]


def component_value(row, formula) -> float:
    return sum(w * as_float(row.get(name), 60.0) for name, w in formula)


def ability_with(row, dim: str, value: float) -> float:
    score = 0.0
    for key in MATRIX_KEYS:
        v = value if key == dim else as_float(row.get(f"mx_{key}"), 60.0)
        score += MATRIX_WEIGHTS.get(key, 0.0) * v
    return score


def fidelity_check(races) -> None:
    for dim, formula in CURRENT.items():
        checked = ok = 0
        for race in races[:150]:
            for row in race:
                recomputed = component_value(row, formula)
                stored = as_float(row.get(f"mx_{dim}"), 60.0)
                checked += 1
                ok += abs(recomputed - stored) < 0.75
        print(f"fidelity {dim}: {ok}/{checked} within 0.75 ({100*ok/max(1,checked):.1f}%)")


def run_gate(name, races, folds, variants, scorer_factory) -> None:
    all_base, all_cand, non_worse = [], [], 0
    for train, valid in folds:
        best, best_key = variants[0], -1.0
        for variant in variants:
            m = metrics_for_races(scorer_factory(train, variant))
            key = (m["good_positional"] + m["good"]) / max(1, m["races"])
            if key > best_key:
                best_key, best = key, variant
        vb = metrics_for_races(scorer_factory(valid, variants[0]))
        vc = metrics_for_races(scorer_factory(valid, best))
        non_worse += vc["top3_precision"] >= vb["top3_precision"]
        all_base.extend(scorer_factory(valid, variants[0]))
        all_cand.extend(scorer_factory(valid, best))
    base = metrics_for_races(all_base)
    cand = metrics_for_races(all_cand)
    gp = (cand["good_positional"] - base["good_positional"]) / base["races"] * 100
    g2 = (cand["good"] - base["good"]) / base["races"] * 100
    passed = (max(gp, g2) >= 1.5 and min(gp, g2) >= -0.5 and cand["miss"] <= base["miss"] and non_worse >= 4
              and (base["top1_win"] - cand["top1_win"]) * 100 <= 0.5
              and (base["winner_in_top3"] - cand["winner_in_top3"]) * 100 <= 0.5
              and (base["gold"] - cand["gold"]) / base["races"] * 100 <= 0.5)
    print(f"{name}: gp {gp:+.2f}pp g2 {g2:+.2f}pp gold {cand['gold']-base['gold']:+d} "
          f"miss Δ {cand['miss']-base['miss']:+d} top1 {(cand['top1_win']-base['top1_win'])*100:+.2f}pp "
          f"wT3 {(cand['winner_in_top3']-base['winner_in_top3'])*100:+.2f}pp folds {non_worse}/{len(folds)} "
          f"→ {'PASS' if passed else 'FAIL / HOLD'}")


def main() -> int:
    races = group_races(materialize_dataset())
    folds = date_folds(races)
    fidelity_check(races)

    # simple grids
    for name, (dim, variants) in GRIDS.items():
        def factory(subset, variant, dim=dim):
            return [[{**r, "_score": ability_with(r, dim, component_value(r, variant))} for r in race]
                    for race in subset]
        run_gate(name, races, folds, variants, factory)

    # P1 coverage-adaptive pace_perf
    def pace_factory(subset, fallback):
        out = []
        for race in subset:
            rows = []
            for r in race:
                pf = as_float(r.get("pace_figure_score"), 60.0)
                if fallback is not None and abs(pf - 60.0) < 1e-9:
                    value = component_value(r, fallback)
                else:
                    value = component_value(r, CURRENT["pace_perf"])
                rows.append({**r, "_score": ability_with(r, "pace_perf", value)})
            out.append(rows)
        return out
    run_gate("P1 pace_perf adaptive", races, folds, PACE_FALLBACKS, pace_factory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
