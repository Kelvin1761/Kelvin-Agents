#!/usr/bin/env python3
"""Test simple AU matrix architectures on the fixed current-runtime snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean, pstdev

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_runtime_micro_ablation import (
    build_report,
    metric_delta,
    metrics_for_scored_races,
    render_markdown,
    select_indices,
)
from io_utils import write_json_atomic, write_text_atomic
from scoring import MATRIX_WEIGHTS, clip_score


VARIANTS = (
    "revised_current",
    "drop_weight_leaf",
    "replace_weight_with_distance",
    "fill_neutral_with_distance",
    "rating70_distance30",
    "rating70_distance_high30",
    "rating70_distance_extreme30",
    "fill_neutral_with_distance_high",
    "threshold_track",
    "threshold_track_plus_distance_high",
    "distance_high_from_track_02",
    "distance_high_conditional_01",
    "distance_high_conditional_02",
    "distance_high_conditional_04",
    "distance_extreme_conditional_01",
    "distance_extreme_conditional_02",
    "distance_from_track_01",
    "distance_from_track_02",
    "distance_from_track_04",
    "distance_from_shape_01",
    "distance_from_shape_02",
    "distance_from_shape_04",
    "distance_from_track_shape_02",
    "distance_from_track_shape_04",
    "drop_weight_plus_track_shape_02",
)


def neutral_formula(components: tuple[tuple[float, float], ...]) -> float:
    return clip_score(
        60.0 + sum((float(value) - 60.0) * weight for value, weight in components)
    )


def architecture_score(row: dict, variant: str) -> float:
    if variant == "revised_current":
        return float(row["score"])
    features = row["feature_scores"]
    matrices = row["matrix_scores"]
    score = float(row["score"])
    old_class = float(matrices["class_weight"])
    rating = float(features.get("rating_score", 60.0))
    weight = float(features.get("weight_score", 60.0))
    distance = float(features.get("distance_score", 60.0))
    distance_high = distance if distance >= 65.0 else 60.0
    distance_extreme = (
        distance if distance >= 65.0 or distance <= 54.0 else 60.0
    )

    class_components = None
    if variant == "drop_weight_leaf":
        class_components = ((rating, 0.70),)
    elif variant == "replace_weight_with_distance":
        class_components = ((rating, 0.70), (distance, 0.141))
    elif variant == "fill_neutral_with_distance":
        class_components = (
            (rating, 0.70),
            (weight, 0.141),
            (distance, 0.159),
        )
    elif variant == "rating70_distance30":
        class_components = ((rating, 0.70), (distance, 0.30))
    elif variant == "rating70_distance_high30":
        class_components = ((rating, 0.70), (distance_high, 0.30))
    elif variant == "rating70_distance_extreme30":
        class_components = ((rating, 0.70), (distance_extreme, 0.30))
    elif variant == "fill_neutral_with_distance_high":
        class_components = (
            (rating, 0.70),
            (weight, 0.141),
            (distance_high, 0.159),
        )

    if class_components is not None:
        new_class = neutral_formula(class_components)
        score += MATRIX_WEIGHTS["class_weight"] * (new_class - old_class)

    transfers = {
        "distance_from_track_01": (0.01, 0.01, 0.0),
        "distance_from_track_02": (0.02, 0.02, 0.0),
        "distance_from_track_04": (0.04, 0.04, 0.0),
        "distance_from_shape_01": (0.01, 0.0, 0.01),
        "distance_from_shape_02": (0.02, 0.0, 0.02),
        "distance_from_shape_04": (0.04, 0.0, 0.04),
        "distance_from_track_shape_02": (0.02, 0.01, 0.01),
        "distance_from_track_shape_04": (0.04, 0.02, 0.02),
        "drop_weight_plus_track_shape_02": (0.02, 0.01, 0.01),
        "distance_high_from_track_02": (0.02, 0.02, 0.0),
    }
    if variant in transfers:
        distance_weight, track_weight, shape_weight = transfers[variant]
        distance_signal = (
            distance_high
            if variant == "distance_high_from_track_02"
            else distance
        )
        score += distance_weight * (distance_signal - 60.0)
        score -= track_weight * (
            float(matrices["track"]) - 60.0
        )
        score -= shape_weight * (
            float(matrices["race_shape"]) - 60.0
        )
        if variant == "drop_weight_plus_track_shape_02":
            new_class = neutral_formula(((rating, 0.70),))
            score += MATRIX_WEIGHTS["class_weight"] * (
                new_class - old_class
            )
    if variant in {
        "threshold_track",
        "threshold_track_plus_distance_high",
    }:
        track = float(matrices["track"])
        threshold_track = (
            track if track < 60.0 or track >= 70.0 else 60.0
        )
        score += MATRIX_WEIGHTS["track"] * (threshold_track - track)
        if variant == "threshold_track_plus_distance_high":
            new_class = neutral_formula(
                ((rating, 0.70), (distance_high, 0.30))
            )
            score += MATRIX_WEIGHTS["class_weight"] * (
                new_class - old_class
            )
    conditional_distance_weights = {
        "distance_high_conditional_01": (0.01, distance_high),
        "distance_high_conditional_02": (0.02, distance_high),
        "distance_high_conditional_04": (0.04, distance_high),
        "distance_extreme_conditional_01": (0.01, distance_extreme),
        "distance_extreme_conditional_02": (0.02, distance_extreme),
    }
    if variant in conditional_distance_weights:
        signal_weight, signal = conditional_distance_weights[variant]
        score += signal_weight * (signal - 60.0)
    return round(score, 4)


def scored_races(dataset: dict, variant: str) -> list[list[dict]]:
    output = []
    for race in dataset["races"]:
        output.append(
            [
                {
                    **row,
                    "score": architecture_score(row, variant),
                }
                for row in race["rows"]
            ]
        )
    return output


def separation(races: list[list[dict]]) -> dict:
    standard_deviations = []
    top_gaps = []
    contender_gaps = []
    for race in races:
        scores = sorted((float(row["score"]) for row in race), reverse=True)
        standard_deviations.append(pstdev(scores))
        top_gaps.append(scores[0] - scores[2])
        if len(scores) >= 5:
            contender_gaps.append(scores[2] - scores[4])
    return {
        "mean_within_race_sd": mean(standard_deviations),
        "compressed_rate_sd_lt_2": sum(
            value < 2 for value in standard_deviations
        )
        / len(standard_deviations),
        "mean_top1_top3_gap": mean(top_gaps),
        "mean_top3_top5_gap": mean(contender_gaps),
    }


def render(report: dict) -> str:
    lines = render_markdown(report).rstrip().splitlines()
    lines.extend(
        [
            "",
            "## Architecture cohorts and separation",
            "",
            "| Variant | 13+ Comp R@5 Δ | 13+ NDCG Δ | Sprint NDCG Δ | Staying NDCG Δ | SD Δ | Compressed Δ |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    base_sep = report["architecture"]["revised_current"]["separation"]
    for name in VARIANTS:
        row = report["architecture"][name]
        large = row["cohorts"]["large_field_13_plus"]["delta_vs_current"]
        sprint = row["cohorts"]["sprint_1000_1399"]["delta_vs_current"]
        staying = row["cohorts"]["staying_1800_plus"]["delta_vs_current"]
        sep = row["separation"]
        lines.append(
            f"| {name} | {large.get('competitive_recall_at5', 0) * 100:.2f}% | "
            f"{large.get('ndcg_at5', 0) * 100:.2f}% | "
            f"{sprint.get('ndcg_at5', 0) * 100:.2f}% | "
            f"{staying.get('ndcg_at5', 0) * 100:.2f}% | "
            f"{sep['mean_within_race_sd'] - base_sep['mean_within_race_sd']:+.3f} | "
            f"{(sep['compressed_rate_sd_lt_2'] - base_sep['compressed_rate_sd_lt_2']) * 100:+.2f}% |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument("--holdout-fraction", type=float, default=0.15)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/private/tmp/au_architecture_audit.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("/private/tmp/au_architecture_audit.md"),
    )
    args = parser.parse_args()
    dataset = json.loads(args.dataset_json.read_text(encoding="utf-8"))
    scored = {
        variant: scored_races(dataset, variant) for variant in VARIANTS
    }
    race_dates = [
        race["metadata"]["date"] for race in dataset["races"]
    ]
    report = build_report(
        [(variant, []) for variant in VARIANTS],
        scored,
        race_dates,
        {},
        holdout_fraction=args.holdout_fraction,
    )

    large_indices = {
        index
        for index, race in enumerate(dataset["races"])
        if int(race["metadata"]["field_size"]) >= 13
    }
    sprint_indices = {
        index
        for index, race in enumerate(dataset["races"])
        if 1000 <= int(race["metadata"]["distance"] or 0) <= 1399
    }
    staying_indices = {
        index
        for index, race in enumerate(dataset["races"])
        if int(race["metadata"]["distance"] or 0) >= 1800
    }
    cohorts = {
        "large_field_13_plus": large_indices,
        "sprint_1000_1399": sprint_indices,
        "staying_1800_plus": staying_indices,
    }
    baseline_cohorts = {
        name: metrics_for_scored_races(
            select_indices(scored["revised_current"], indices)
        )
        for name, indices in cohorts.items()
    }
    report["architecture"] = {}
    for variant in VARIANTS:
        variant_cohorts = {}
        for name, indices in cohorts.items():
            metrics = metrics_for_scored_races(
                select_indices(scored[variant], indices)
            )
            variant_cohorts[name] = {
                "races": len(indices),
                "metrics": metrics,
                "delta_vs_current": metric_delta(
                    metrics,
                    baseline_cohorts[name],
                ),
            }
        report["architecture"][variant] = {
            "separation": separation(scored[variant]),
            "cohorts": variant_cohorts,
        }
    report["design"]["weight_invariant"] = (
        "Distance top-level candidates transfer exactly the same weight from "
        "track/race_shape; total matrix weight remains 1.0."
    )
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render(report))
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
