#!/usr/bin/env python3
"""Expanding walk-forward gate for a simple explainable AU linear ranker.

Each model is trained only on races before its validation dates.  The target
is the observed competitive tier (leading third, bounded to 3-5 runners), not
exact Top 3 order.  Result/SP fields remain labels and are never model inputs.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from au_runtime_micro_ablation import (
    metric_delta,
    metrics_for_scored_races,
)
from au_racing_engine.io_utils import write_json_atomic, write_text_atomic


FEATURE_SETS = {
    "matrix_6": (
        "mx_stability",
        "mx_pace_perf",
        "mx_race_shape",
        "mx_jockey_trainer",
        "mx_class_weight",
        "mx_track",
    ),
    "matrix_6_plus_distance": (
        "mx_stability",
        "mx_pace_perf",
        "mx_race_shape",
        "mx_jockey_trainer",
        "mx_class_weight",
        "mx_track",
        "distance_score",
    ),
    "compact_7": (
        "form_score",
        "consistency_score",
        "trainer_score",
        "rating_score",
        "jockey_score",
        "distance_score",
        "pace_figure_score",
    ),
    "core_10": (
        "form_score",
        "consistency_score",
        "trainer_score",
        "rating_score",
        "jockey_score",
        "distance_score",
        "pace_figure_score",
        "trial_score",
        "pace_map_score",
        "track_score",
    ),
}
PRIORITY_METRICS = (
    "good_positional",
    "top3_all_within_top4",
    "competitive_recall_at5",
    "ndcg_at5",
    "winner_top5",
    "zero_hit",
)


def feature_value(row: dict, name: str) -> float:
    if name.startswith("mx_"):
        key = name[3:]
        return float(row["matrix_scores"].get(key, 60.0))
    return float(row["feature_scores"].get(name, 60.0))


def competitive_cutoff(field_size: int) -> int:
    return min(5, max(3, math.ceil(field_size / 3)))


def standardizer(
    races: list[dict],
    feature_names: tuple[str, ...],
) -> tuple[dict[str, float], dict[str, float]]:
    rows = [row for race in races for row in race["rows"]]
    means = {}
    scales = {}
    for name in feature_names:
        values = [feature_value(row, name) for row in rows]
        avg = mean(values)
        variance = mean((value - avg) ** 2 for value in values)
        means[name] = avg
        scales[name] = math.sqrt(variance) or 1.0
    return means, scales


def standardised_vector(
    row: dict,
    feature_names: tuple[str, ...],
    means: dict[str, float],
    scales: dict[str, float],
) -> tuple[float, ...]:
    return tuple(
        (feature_value(row, name) - means[name]) / scales[name]
        for name in feature_names
    )


def pair_vectors(
    races: list[dict],
    feature_names: tuple[str, ...],
    means: dict[str, float],
    scales: dict[str, float],
) -> list[tuple[float, ...]]:
    pairs = []
    for race in races:
        rows = race["rows"]
        cutoff = competitive_cutoff(len(rows))
        positives = [row for row in rows if int(row["actual_pos"]) <= cutoff]
        negatives = [row for row in rows if int(row["actual_pos"]) > cutoff]
        for positive in positives:
            pos = standardised_vector(
                positive, feature_names, means, scales
            )
            for negative in negatives:
                neg = standardised_vector(
                    negative, feature_names, means, scales
                )
                pairs.append(tuple(a - b for a, b in zip(pos, neg)))
    return pairs


def sigmoid(value: float) -> float:
    if value <= -40:
        return 0.0
    if value >= 40:
        return 1.0
    return 1.0 / (1.0 + math.exp(-value))


def train_pairwise(
    races: list[dict],
    feature_names: tuple[str, ...],
    *,
    epochs: int = 35,
    learning_rate: float = 0.012,
    l2: float = 0.002,
    seed: int = 20260730,
) -> dict:
    means, scales = standardizer(races, feature_names)
    pairs = pair_vectors(races, feature_names, means, scales)
    if not pairs:
        raise ValueError("No competitive/non-competitive training pairs.")
    weights = [0.0] * len(feature_names)
    rng = random.Random(seed)
    for _epoch in range(epochs):
        rng.shuffle(pairs)
        for vector in pairs:
            prediction = sigmoid(
                sum(weight * value for weight, value in zip(weights, vector))
            )
            error = prediction - 1.0
            for index, value in enumerate(vector):
                weights[index] -= learning_rate * (
                    error * value + l2 * weights[index]
                )
    return {
        "feature_names": feature_names,
        "weights": dict(zip(feature_names, weights)),
        "means": means,
        "scales": scales,
        "training_pairs": len(pairs),
    }


def predict(model: dict, row: dict) -> float:
    return sum(
        model["weights"][name]
        * (
            (feature_value(row, name) - model["means"][name])
            / model["scales"][name]
        )
        for name in model["feature_names"]
    )


def score_races(model: dict, races: list[dict]) -> list[list[dict]]:
    return [
        [
            {**row, "score": predict(model, row)}
            for row in race["rows"]
        ]
        for race in races
    ]


def baseline_races(races: list[dict]) -> list[list[dict]]:
    return [[dict(row) for row in race["rows"]] for race in races]


def date_partitions(
    dataset: dict,
    *,
    holdout_fraction: float = 0.15,
    folds: int = 5,
    initial_train_fraction: float = 0.40,
) -> tuple[list[tuple[list[dict], list[dict]]], list[dict], list[dict]]:
    races = sorted(
        dataset["races"],
        key=lambda race: (
            race["metadata"]["date"],
            race["metadata"]["track"],
            race["metadata"]["race_number"],
        ),
    )
    dates = sorted({race["metadata"]["date"] for race in races})
    holdout_count = max(1, math.ceil(len(dates) * holdout_fraction))
    holdout_dates = set(dates[-holdout_count:])
    dev_dates = dates[:-holdout_count]
    initial_count = max(1, math.floor(len(dev_dates) * initial_train_fraction))
    validation_dates = dev_dates[initial_count:]
    fold_size = max(1, math.ceil(len(validation_dates) / folds))
    fold_date_sets = [
        set(validation_dates[index : index + fold_size])
        for index in range(0, len(validation_dates), fold_size)
    ]
    expanding = []
    for valid_dates in fold_date_sets:
        first_valid = min(valid_dates)
        train = [
            race
            for race in races
            if race["metadata"]["date"] < first_valid
            and race["metadata"]["date"] not in holdout_dates
        ]
        valid = [
            race
            for race in races
            if race["metadata"]["date"] in valid_dates
        ]
        if train and valid:
            expanding.append((train, valid))
    dev = [
        race
        for race in races
        if race["metadata"]["date"] not in holdout_dates
    ]
    terminal = [
        race
        for race in races
        if race["metadata"]["date"] in holdout_dates
    ]
    return expanding, dev, terminal


def model_metrics(
    model: dict,
    races: list[dict],
) -> tuple[dict, dict, dict]:
    candidate = metrics_for_scored_races(score_races(model, races))
    baseline = metrics_for_scored_races(baseline_races(races))
    return candidate, baseline, metric_delta(candidate, baseline)


def gate(
    fold_deltas: list[dict],
    terminal_delta: dict,
) -> dict:
    mean_deltas = {
        metric: mean(fold.get(metric, 0.0) for fold in fold_deltas)
        for metric in PRIORITY_METRICS
    }
    nonnegative = {
        metric: sum(
            (
                fold.get(metric, 0.0) >= 0
                if metric != "zero_hit"
                else fold.get(metric, 0.0) <= 0
            )
            for fold in fold_deltas
        )
        for metric in PRIORITY_METRICS
    }
    fold_pass = (
        mean_deltas["good_positional"] >= 0
        and mean_deltas["top3_all_within_top4"] >= 0
        and mean_deltas["competitive_recall_at5"] > 0
        and mean_deltas["ndcg_at5"] > 0
        and mean_deltas["winner_top5"] >= 0
        and mean_deltas["zero_hit"] <= 0
        and all(count >= max(1, len(fold_deltas) - 1) for count in nonnegative.values())
    )
    terminal_pass = (
        terminal_delta.get("good_positional", 0.0) >= 0
        and terminal_delta.get("top3_all_within_top4", 0.0) >= 0
        and terminal_delta.get("competitive_recall_at5", 0.0) > 0
        and terminal_delta.get("ndcg_at5", 0.0) > 0
        and terminal_delta.get("winner_top5", 0.0) >= 0
        and terminal_delta.get("zero_hit", 0.0) <= 0
    )
    material = (
        mean_deltas["competitive_recall_at5"] >= 0.005
        or mean_deltas["ndcg_at5"] >= 0.005
    ) and (
        terminal_delta.get("competitive_recall_at5", 0.0) >= 0.005
        or terminal_delta.get("ndcg_at5", 0.0) >= 0.005
    )
    return {
        "mean_fold_deltas": mean_deltas,
        "nonnegative_fold_counts": nonnegative,
        "fold_pass": fold_pass,
        "terminal_pass": terminal_pass,
        "material_improvement": material,
        "promote": fold_pass and terminal_pass and material,
    }


def run_audit(
    dataset: dict,
    *,
    holdout_fraction: float = 0.15,
    seed: int = 20260730,
) -> dict:
    folds, dev, terminal = date_partitions(
        dataset,
        holdout_fraction=holdout_fraction,
    )
    results = {}
    for set_index, (name, feature_names) in enumerate(FEATURE_SETS.items()):
        fold_results = []
        for fold_index, (train, valid) in enumerate(folds):
            model = train_pairwise(
                train,
                feature_names,
                seed=seed + set_index * 100 + fold_index,
            )
            candidate, baseline, delta = model_metrics(model, valid)
            fold_results.append(
                {
                    "train_races": len(train),
                    "validation_races": len(valid),
                    "candidate": candidate,
                    "baseline": baseline,
                    "delta": delta,
                    "weights": model["weights"],
                    "training_pairs": model["training_pairs"],
                }
            )
        terminal_model = train_pairwise(
            dev,
            feature_names,
            seed=seed + set_index * 100 + 99,
        )
        terminal_candidate, terminal_baseline, terminal_delta = model_metrics(
            terminal_model,
            terminal,
        )
        decision = gate(
            [fold["delta"] for fold in fold_results],
            terminal_delta,
        )
        results[name] = {
            "features": feature_names,
            "folds": fold_results,
            "terminal": {
                "train_races": len(dev),
                "validation_races": len(terminal),
                "candidate": terminal_candidate,
                "baseline": terminal_baseline,
                "delta": terminal_delta,
                "weights": terminal_model["weights"],
                "training_pairs": terminal_model["training_pairs"],
            },
            "gate": decision,
        }
    promoted = [
        name for name, result in results.items() if result["gate"]["promote"]
    ]
    return {
        "design": {
            "aligned_races": len(dataset["races"]),
            "expanding_folds": len(folds),
            "fold_train_validation_races": [
                [len(train), len(valid)] for train, valid in folds
            ],
            "terminal_train_validation_races": [len(dev), len(terminal)],
            "target": "observed competitive tier; leading third capped at 3-5",
            "outcome_only_fields": ["actual_pos", "result_sp_label"],
            "selection": (
                "Four feature sets declared before evaluation. "
                "Every fold trains only on earlier dates."
            ),
        },
        "promoted_candidates": promoted,
        "recommendation": (
            promoted[0]
            if len(promoted) == 1
            else (
                "manual simplicity comparison required"
                if promoted
                else "retain current production architecture"
            )
        ),
        "models": results,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# AU Pairwise Ranker Walk-Forward Audit",
        "",
        f"- Aligned races: {report['design']['aligned_races']}",
        f"- Expanding folds: {report['design']['expanding_folds']}",
        f"- Terminal train / validation: {report['design']['terminal_train_validation_races']}",
        f"- Promoted: {', '.join(report['promoted_candidates']) or 'none'}",
        f"- Recommendation: {report['recommendation']}",
        "",
        "| Model | Promote | Mean fold Good Δ | Mean fold T3@4 Δ | "
        "Mean fold Comp Δ | Mean fold NDCG Δ | Mean fold W@5 Δ | "
        "Mean fold 0-hit Δ | Terminal Good Δ | Terminal T3@4 Δ | "
        "Terminal Comp Δ | Terminal NDCG Δ | Terminal W@5 Δ | Terminal 0-hit Δ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    pct = lambda value: f"{value * 100:+.2f}%"
    for name, result in report["models"].items():
        fold = result["gate"]["mean_fold_deltas"]
        terminal = result["terminal"]["delta"]
        lines.append(
            f"| {name} | {result['gate']['promote']} | "
            f"{pct(fold['good_positional'])} | "
            f"{pct(fold['top3_all_within_top4'])} | "
            f"{pct(fold['competitive_recall_at5'])} | "
            f"{pct(fold['ndcg_at5'])} | "
            f"{pct(fold['winner_top5'])} | "
            f"{pct(fold['zero_hit'])} | "
            f"{pct(terminal.get('good_positional', 0))} | "
            f"{pct(terminal.get('top3_all_within_top4', 0))} | "
            f"{pct(terminal.get('competitive_recall_at5', 0))} | "
            f"{pct(terminal.get('ndcg_at5', 0))} | "
            f"{pct(terminal.get('winner_top5', 0))} | "
            f"{pct(terminal.get('zero_hit', 0))} |"
        )
    lines.extend(["", "## Terminal weights", ""])
    for name, result in report["models"].items():
        weights = sorted(
            result["terminal"]["weights"].items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )
        lines.append(f"- **{name}:** " + ", ".join(
            f"{feature}={weight:+.3f}" for feature, weight in weights
        ))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument("--holdout-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/private/tmp/au_pairwise_ranker_audit.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("/private/tmp/au_pairwise_ranker_audit.md"),
    )
    args = parser.parse_args()
    dataset = json.loads(args.dataset_json.read_text(encoding="utf-8"))
    report = run_audit(
        dataset,
        holdout_fraction=args.holdout_fraction,
        seed=args.seed,
    )
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
