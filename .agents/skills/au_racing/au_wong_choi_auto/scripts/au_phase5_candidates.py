#!/usr/bin/env python3
"""AU Wong Choi Phase-5 candidate shadow tests (2026-07-17 review).

Research-only harness — never writes Logic files or live weights. Tests the
three candidate families that Phase-4 cohort/attribution evidence supports:

1. Reliability shrinkage — pull horses with thin feature evidence toward the
   field median before ranking (candidate for the 12+ field deficit, where
   thin-evidence horses leak into the top 2).
2. Field-size-conditional shrinkage — same rule, applied only in 12+ fields.
3. Weight micro-recalibration — stability x0.8 and/or jockey_trainer x1.2
   (renormalized), the only perturbations that lifted positional Good in-sample.

Every candidate is evaluated out-of-sample on expanding-date folds
(`date_folds`) with the canonical metrics, against the promotion gate:
Good(any-2) >= +1.5pp, no loss > 0.5pp on Gold / Top1 / winner-in-Top3,
Miss non-regression, and stability in >= 4/5 folds. Positional Good is also
reported since it is the cross-engine headline metric.

Usage:
    python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_phase5_candidates.py \
        [--report-date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import median

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(PROJECT_ROOT / ".agents" / "skills" / "shared_racing"))

from au_archive_calibrator import MATRIX_KEYS, normalize_condition_bucket  # noqa: E402
from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
    metrics_for_races,
)
from au_failure_cohorts import FEATURE_KEYS_FOR_COVERAGE, field_band  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402

GATE = {
    "good_lift_pp": 1.5,       # any-2 Good, the historical AU gate metric
    "max_loss_pp": 0.5,        # gold / top1 / winner-in-top3
    "fold_stability": 4,       # of 5 folds non-worse on top3 precision
}


def default_fraction(row: dict) -> float:
    values = [as_float(row.get(key), 60.0) for key in FEATURE_KEYS_FOR_COVERAGE]
    return sum(1 for value in values if abs(value - 60.0) < 1e-9) / len(values)


def production_score(row: dict) -> float:
    return as_float(row["ability_score"], 60.0)


def reconstruction_score(row: dict, weights: dict[str, float]) -> float:
    total = sum(weights.values()) or 1.0
    scale = sum(MATRIX_WEIGHTS.values()) / total
    return scale * sum(weights.get(key, 0.0) * as_float(row.get(f"mx_{key}"), 60.0) for key in MATRIX_KEYS)


def score_races(races: list[list[dict]], scorer) -> list[list[dict]]:
    return [[{**row, "_score": float(scorer(row, race))} for row in race] for race in races]


def shrinkage_scorer(lam: float, min_field: int = 0):
    """score' = field_median + (1 - lam * default_frac) * (score - field_median)."""

    def scorer(row: dict, race: list[dict]) -> float:
        if len(race) < min_field:
            return production_score(row)
        field_median = median(production_score(other) for other in race)
        shrink = 1.0 - lam * default_fraction(row)
        return field_median + shrink * (production_score(row) - field_median)

    return scorer


def weight_scorer(multipliers: dict[str, float]):
    weights = {key: MATRIX_WEIGHTS.get(key, 0.0) * multipliers.get(key, 1.0) for key in MATRIX_KEYS}

    def scorer(row: dict, race: list[dict]) -> float:
        return reconstruction_score(row, weights)

    return scorer


def baseline_production(row: dict, race: list[dict]) -> float:
    return production_score(row)


def baseline_reconstruction(row: dict, race: list[dict]) -> float:
    return reconstruction_score(row, dict(MATRIX_WEIGHTS))


def oos_window(races: list[list[dict]]) -> list[list[dict]]:
    return [race for _train, valid in date_folds(races) for race in valid]


def fold_rows(races: list[list[dict]], baseline_scorer, candidate_scorer) -> list[dict]:
    rows = []
    for idx, (_train, valid) in enumerate(date_folds(races), 1):
        rows.append(
            {
                "fold": idx,
                "baseline": metrics_for_races(score_races(valid, baseline_scorer)),
                "candidate": metrics_for_races(score_races(valid, candidate_scorer)),
            }
        )
    return rows


def slice_metrics(races: list[list[dict]], scorer) -> dict[str, dict]:
    groups: dict[str, list[list[dict]]] = defaultdict(list)
    for race in races:
        groups[field_band(len(race))].append(race)
        groups[f"going {normalize_condition_bucket(str(race[0].get('condition_bucket') or ''))}"].append(race)
    return {name: metrics_for_races(score_races(members, scorer)) for name, members in sorted(groups.items())}


def affected_races(races: list[list[dict]], baseline_scorer, candidate_scorer) -> int:
    changed = 0
    for race in races:
        base = [row["horse_number"] for row in sorted(
            score_races([race], baseline_scorer)[0], key=lambda r: (-r["_score"], int(r["horse_number"])))][:3]
        cand = [row["horse_number"] for row in sorted(
            score_races([race], candidate_scorer)[0], key=lambda r: (-r["_score"], int(r["horse_number"])))][:3]
        changed += base != cand
    return changed


def rate(metrics: dict, key: str) -> float:
    if key in ("winner_in_top3", "top1_win", "top3_precision"):
        return metrics[key]
    return metrics[key] / max(1, metrics["races"])


def evaluate_candidate(name: str, races: list[list[dict]], baseline_scorer, candidate_scorer) -> dict:
    valid = oos_window(races)
    baseline = metrics_for_races(score_races(valid, baseline_scorer))
    candidate = metrics_for_races(score_races(valid, candidate_scorer))
    folds = fold_rows(races, baseline_scorer, candidate_scorer)
    top3_non_worse = sum(row["candidate"]["top3_precision"] >= row["baseline"]["top3_precision"] for row in folds)

    good_lift = (rate(candidate, "good") - rate(baseline, "good")) * 100
    good_pos_lift = (rate(candidate, "good_positional") - rate(baseline, "good_positional")) * 100
    losses = {
        "gold": (rate(baseline, "gold") - rate(candidate, "gold")) * 100,
        "top1": (baseline["top1_win"] - candidate["top1_win"]) * 100,
        "winner_in_top3": (baseline["winner_in_top3"] - candidate["winner_in_top3"]) * 100,
    }
    passed = (
        good_lift >= GATE["good_lift_pp"]
        and all(loss <= GATE["max_loss_pp"] for loss in losses.values())
        and candidate["miss"] <= baseline["miss"]
        and top3_non_worse >= GATE["fold_stability"]
    )
    return {
        "name": name,
        "oos_races": len(valid),
        "affected_top3_changes": affected_races(valid, baseline_scorer, candidate_scorer),
        "baseline": baseline,
        "candidate": candidate,
        "good_lift_pp": round(good_lift, 2),
        "good_positional_lift_pp": round(good_pos_lift, 2),
        "losses_pp": {key: round(value, 2) for key, value in losses.items()},
        "miss_delta": candidate["miss"] - baseline["miss"],
        "folds": folds,
        "top3_non_worse_folds": f"{top3_non_worse}/{len(folds)}",
        "slices": slice_metrics(valid, candidate_scorer),
        "passed": passed,
    }


def fmt(metrics: dict) -> str:
    return (
        f"{metrics['races']} races; {metrics['gold']} Gold / {metrics['good']} Good-any2 "
        f"({metrics['good_positional']} Good-pos) / {metrics['pass']} Pass / {metrics['miss']} Miss; "
        f"Top3 {metrics['top3_precision'] * 100:.1f}%; W-in-T3 {metrics['winner_in_top3'] * 100:.1f}%; "
        f"Top1 {metrics['top1_win'] * 100:.1f}%"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="AU Phase-5 candidate shadow tests")
    parser.add_argument("--report-date", default=date.today().isoformat())
    args = parser.parse_args()

    races = group_races(materialize_dataset())

    candidates = []
    for lam in (0.15, 0.30, 0.50):
        candidates.append((f"reliability shrinkage λ={lam:.2f} (all fields)",
                           baseline_production, shrinkage_scorer(lam)))
        candidates.append((f"reliability shrinkage λ={lam:.2f} (12+ fields only)",
                           baseline_production, shrinkage_scorer(lam, min_field=12)))
    candidates.append(("weights: stability x0.8", baseline_reconstruction,
                       weight_scorer({"stability": 0.8})))
    candidates.append(("weights: jockey_trainer x1.2", baseline_reconstruction,
                       weight_scorer({"jockey_trainer": 1.2})))
    candidates.append(("weights: stability x0.8 + jockey_trainer x1.2", baseline_reconstruction,
                       weight_scorer({"stability": 0.8, "jockey_trainer": 1.2})))

    results = [evaluate_candidate(name, races, base, cand) for name, base, cand in candidates]

    lines = [
        f"# AU Wong Choi Phase-5 Candidate Shadow Tests ({args.report_date})",
        "",
        "> Research-only. Cached 710-race archive, expanding-date OOS folds.",
        f"> Gate: Good(any-2) ≥ +{GATE['good_lift_pp']}pp, losses ≤ {GATE['max_loss_pp']}pp "
        f"(Gold/Top1/W-in-T3), Miss non-regression, Top3 stability ≥ {GATE['fold_stability']}/5 folds.",
        "",
    ]
    for result in results:
        lines += [
            f"## {result['name']}",
            "",
            f"- Baseline:  {fmt(result['baseline'])}",
            f"- Candidate: {fmt(result['candidate'])}",
            f"- Good(any-2) lift: **{result['good_lift_pp']:+.2f}pp**; Good(positional) lift: "
            f"{result['good_positional_lift_pp']:+.2f}pp; losses (pp): {result['losses_pp']}; "
            f"Miss Δ: {result['miss_delta']:+d}",
            f"- Races with a changed Top3: {result['affected_top3_changes']} / {result['oos_races']}; "
            f"fold stability: {result['top3_non_worse_folds']}",
            f"- Decision: **{'PASS' if result['passed'] else 'FAIL / HOLD'}**",
            "",
        ]
    passed = [result["name"] for result in results if result["passed"]]
    lines += [
        "## Summary",
        "",
        ("Candidates clearing the gate: **" + ", ".join(passed) + "**.") if passed
        else "**No candidate cleared the promotion gate.** Keep the current model; "
             "the Phase-4 evidence (zero-hit winners losing on every matrix dimension) "
             "points to missing raw evidence, not mis-weighting — improvement work should "
             "target data enrichment (sectionals/trials coverage, venue-specific evidence) "
             "rather than global score arithmetic.",
        "",
    ]
    report = "\n".join(lines)
    out_md = PROJECT_ROOT / f"{args.report_date} AU Phase5 Candidate Shadow Tests.md"
    out_json = PROJECT_ROOT / "scratch" / "au_phase5_candidates.json"
    out_md.write_text(report, encoding="utf-8")
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    print()
    for result in results:
        print(f"{'PASS' if result['passed'] else 'HOLD'}  {result['name']}: "
              f"good {result['good_lift_pp']:+.2f}pp, good-pos {result['good_positional_lift_pp']:+.2f}pp, "
              f"miss Δ {result['miss_delta']:+d}, folds {result['top3_non_worse_folds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
