#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
from collections import Counter
from pathlib import Path

from au_cached_walkforward_ml import (
    DATASET_CSV,
    as_float,
    date_folds,
    fmt_metrics,
    group_races,
    materialize_dataset,
    metrics_for_races,
    score_baseline,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
OUTPUT_MD = PROJECT_ROOT / "2026-06-07 AU ML Weight Gate.md"

MATRIX_FEATURES = (
    "mx_stability",
    "mx_sectional",
    "mx_race_shape",
    "mx_jockey_trainer",
    "mx_class_weight",
    "mx_track",
    "mx_form_line",
)

CURRENT_WEIGHTS = {
    "mx_stability": 0.330,
    "mx_sectional": 0.105,
    "mx_race_shape": 0.234,
    "mx_jockey_trainer": 0.214,
    "mx_class_weight": 0.050,
    "mx_track": 0.067,
    "mx_form_line": 0.000,
}


def normalise(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {key: max(0.0, float(weights.get(key, 0.0))) for key in MATRIX_FEATURES}
    total = sum(cleaned.values()) or 1.0
    return {key: value / total for key, value in cleaned.items()}


def score_row(row: dict, weights: dict[str, float]) -> float:
    return sum(as_float(row.get(key), 60.0) * weights[key] for key in MATRIX_FEATURES)


def score_races(races: list[list[dict]], weights: dict[str, float]) -> list[list[dict]]:
    output = []
    for race in races:
        output.append([{**row, "_score": score_row(row, weights)} for row in race])
    return output


def objective(metrics: dict) -> float:
    races = metrics["races"] or 1
    pass_rate = metrics["pass"] / races
    good_rate = metrics["good"] / races
    gold_rate = metrics["gold"] / races
    miss_rate = metrics["miss"] / races
    return (
        metrics["top3_precision"] * 3.0
        + metrics["winner_in_top3"] * 1.2
        + pass_rate * 0.8
        + good_rate * 0.6
        + gold_rate * 0.4
        - miss_rate * 1.4
    )


def random_near_current(rng: random.Random, spread: float) -> dict[str, float]:
    weights = {}
    for key, value in CURRENT_WEIGHTS.items():
        jitter = rng.uniform(-spread, spread)
        weights[key] = max(0.0, value + jitter)
    return normalise(weights)


def random_simplex(rng: random.Random) -> dict[str, float]:
    values = [rng.gammavariate(1.2, 1.0) for _ in MATRIX_FEATURES]
    total = sum(values) or 1.0
    return {key: value / total for key, value in zip(MATRIX_FEATURES, values)}


def candidate_weights(rng: random.Random, iterations: int) -> list[dict[str, float]]:
    candidates = [
        normalise(CURRENT_WEIGHTS),
        normalise({key: 1.0 for key in MATRIX_FEATURES}),
        normalise({
            "mx_stability": 0.25,
            "mx_sectional": 0.12,
            "mx_race_shape": 0.25,
            "mx_jockey_trainer": 0.20,
            "mx_class_weight": 0.06,
            "mx_track": 0.10,
            "mx_form_line": 0.02,
        }),
    ]
    for _ in range(iterations):
        if rng.random() < 0.65:
            candidates.append(random_near_current(rng, spread=0.08))
        else:
            candidates.append(random_simplex(rng))
    return candidates


def train_weights(train_races: list[list[dict]], rng: random.Random, iterations: int) -> tuple[dict[str, float], dict]:
    baseline = metrics_for_races(score_baseline(train_races, "ability_score"))
    best_weights = normalise(CURRENT_WEIGHTS)
    best_metrics = metrics_for_races(score_races(train_races, best_weights))
    best_score = objective(best_metrics)
    for weights in candidate_weights(rng, iterations):
        metrics = metrics_for_races(score_races(train_races, weights))
        if metrics["miss"] > baseline["miss"] + 2:
            continue
        score = objective(metrics)
        if score > best_score:
            best_score = score
            best_weights = weights
            best_metrics = metrics
    return best_weights, best_metrics


def aggregate_weight_rows(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    return {key: sum(row[key] for row in rows) / len(rows) for key in MATRIX_FEATURES}


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def delta_text(base: dict, cand: dict) -> str:
    return (
        f"Gold {cand['gold'] - base['gold']:+d}, Good {cand['good'] - base['good']:+d}, "
        f"Pass {cand['pass'] - base['pass']:+d}, Miss {cand['miss'] - base['miss']:+d}, "
        f"Top3 {(cand['top3_precision'] - base['top3_precision']) * 100:+.1f}pp, "
        f"W-in-T3 {(cand['winner_in_top3'] - base['winner_in_top3']) * 100:+.1f}pp"
    )


def render_report(
    races: list[list[dict]],
    validation_races: list[list[dict]],
    baseline_metrics: dict,
    current_weight_metrics: dict,
    ml_metrics: dict,
    fold_rows: list[dict],
    avg_weights: dict[str, float],
) -> str:
    gate_passed = (
        ml_metrics["top3_precision"] > baseline_metrics["top3_precision"]
        and ml_metrics["winner_in_top3"] >= baseline_metrics["winner_in_top3"]
        and ml_metrics["miss"] <= baseline_metrics["miss"]
    )
    lines = [
        "# AU ML Weight Gate",
        "",
        "## Dataset",
        "",
        f"- Races: **{len(races)}**",
        f"- Validation races: **{len(validation_races)}**",
        f"- Horses: **{sum(len(race) for race in races)}**",
        f"- Cache: `{DATASET_CSV}`",
        "",
        "## Walk-Forward Result",
        "",
        "| Model | Result | Delta vs ability baseline |",
        "|---|---|---|",
        f"| Current ability baseline | {fmt_metrics(baseline_metrics)} | - |",
        f"| Current 7D weights only | {fmt_metrics(current_weight_metrics)} | {delta_text(baseline_metrics, current_weight_metrics)} |",
        f"| ML optimised 7D weights | {fmt_metrics(ml_metrics)} | {delta_text(baseline_metrics, ml_metrics)} |",
        "",
        "## Average ML Weights",
        "",
        "| Matrix | Current | ML avg | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key in MATRIX_FEATURES:
        current = normalise(CURRENT_WEIGHTS)[key]
        ml = avg_weights.get(key, 0.0)
        lines.append(f"| `{key}` | {pct(current)} | {pct(ml)} | {pct(ml - current)} |")
    lines.extend([
        "",
        "## Fold Detail",
        "",
        "| Fold | Train races | Validation races | Train best | Validation ML | Validation delta |",
        "|---:|---:|---:|---|---|---|",
    ])
    for row in fold_rows:
        lines.append(
            f"| {row['fold']} | {row['train_races']} | {row['valid_races']} | "
            f"{fmt_metrics(row['train_best'])} | {fmt_metrics(row['valid_ml'])} | {delta_text(row['valid_baseline'], row['valid_ml'])} |"
        )
    lines.extend([
        "",
        "## Gate",
        "",
        "PASSED" if gate_passed else "FAILED",
        "",
    ])
    if gate_passed:
        lines.append("- ML weights beat current ability baseline out-of-sample. Candidate can move to shadow/live review.")
    else:
        lines.append("- Do not replace current AU scoring weights. Current `ability_score` baseline remains stronger out-of-sample.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and gate AU 7D ML matrix weights by date walk-forward.")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--iterations", type=int, default=2500)
    parser.add_argument("--seed", type=int, default=20260607)
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    rows = materialize_dataset(rebuild=args.rebuild_cache)
    races = group_races(rows)
    folds = date_folds(races)
    validation_races = [race for _, valid in folds for race in valid]
    baseline_scored = score_baseline(validation_races, "ability_score")
    current_weight_scored = score_races(validation_races, normalise(CURRENT_WEIGHTS))
    ml_scored = []
    weight_rows = []
    fold_rows = []
    for fold_idx, (train, valid) in enumerate(folds, 1):
        weights, train_best = train_weights(train, rng, args.iterations)
        weight_rows.append(weights)
        valid_ml = score_races(valid, weights)
        ml_scored.extend(valid_ml)
        fold_rows.append(
            {
                "fold": fold_idx,
                "train_races": len(train),
                "valid_races": len(valid),
                "train_best": train_best,
                "valid_baseline": metrics_for_races(score_baseline(valid, "ability_score")),
                "valid_ml": metrics_for_races(valid_ml),
            }
        )

    baseline_metrics = metrics_for_races(baseline_scored)
    current_weight_metrics = metrics_for_races(current_weight_scored)
    ml_metrics = metrics_for_races(ml_scored)
    avg_weights = aggregate_weight_rows(weight_rows)
    args.output.write_text(
        render_report(
            races,
            validation_races,
            baseline_metrics,
            current_weight_metrics,
            ml_metrics,
            fold_rows,
            avg_weights,
        ),
        encoding="utf-8",
    )
    print(f"Races: {len(races)}")
    print(f"Validation races: {len(validation_races)}")
    print(f"Current ability baseline: {fmt_metrics(baseline_metrics)}")
    print(f"Current 7D weights only: {fmt_metrics(current_weight_metrics)}")
    print(f"ML optimised 7D weights: {fmt_metrics(ml_metrics)}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
