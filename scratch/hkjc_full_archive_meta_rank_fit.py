#!/usr/bin/env python3
"""Fit a conservative full-field HKJC competitiveness calibration layer.

The historical published order is treated as the dominant prior and converted
to a race-relative score.  Five pre-race evidence dimensions can only earn
weight through development-meeting CV.  The model is a single positive linear
formula applied to every runner, never a boundary swap.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing"))
from eval_metrics import race_metrics, summarize_races  # noqa: E402


REPLAY = ROOT / "scratch" / "hkjc_prerace_replay.csv"
DIMENSIONS = ROOT / "scratch" / "hkjc_rebuilt_dimensions.csv"
OUTPUT = ROOT / "scratch" / "hkjc_full_archive_meta_rank_fit.json"
REPORT = ROOT / "scratch" / "hkjc_full_archive_meta_rank_fit_report.md"
FEATURES = (
    "published_prior",
    "stability",
    "trainer_signal",
    "class_rating_experience",
    "speed_engine",
    "recent_mean_finish",
)
CURRENT = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=float)
REGULARIZATIONS = (0.5, 1.0, 2.0, 4.0, 8.0)
TEMPERATURE = 3.0


def as_float(value: Any, default: float | None = 0.0) -> float | None:
    if value in (None, ""):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(number) else number


def as_int(value: Any, default: int = 0) -> int:
    number = as_float(value, None)
    return int(number) if number is not None else default


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def horse_key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(row["dataset"]),
        str(row["meeting"]),
        as_int(row["race_number"]),
        as_int(row["horse_number"]),
    )


def race_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return horse_key(row)[:3]


def relative(
    rows: list[dict[str, Any]],
    getter,
    *,
    higher_is_better: bool = True,
) -> dict[int, float]:
    values = {as_int(row["horse_number"]): getter(row) for row in rows}
    valid = {horse: value for horse, value in values.items() if value is not None}
    if len(valid) < 2:
        return {horse: 60.0 for horse in values}
    output = {}
    denominator = len(valid) - 1
    for horse, value in values.items():
        if value is None:
            output[horse] = 60.0
            continue
        others = [item for other, item in valid.items() if other != horse]
        worse = (
            sum(item < value for item in others)
            if higher_is_better
            else sum(item > value for item in others)
        )
        ties = sum(item == value for item in others)
        output[horse] = 50.0 + 20.0 * (worse + 0.5 * ties) / denominator
    return output


def prepare() -> list[dict[str, Any]]:
    dimension_rows = {horse_key(row): row for row in read_csv(DIMENSIONS)}
    grouped: defaultdict[tuple[str, str, int], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(REPLAY):
        grouped[race_key(row)].append(row)
    races = []
    for current_race, rows in grouped.items():
        prior = relative(
            rows,
            lambda row: -float(as_int(row["reference_original_rank"])),
        )
        rating = relative(rows, lambda row: as_float(row.get("card_rating"), None))
        experience = relative(rows, lambda row: as_float(row.get("starts"), None))
        mean_finish = relative(
            rows,
            lambda row: as_float(row.get("last6_mean_finish"), None),
            higher_is_better=False,
        )
        feature_rows = []
        horses = []
        positions = []
        for row in rows:
            horse = as_int(row["horse_number"])
            dim = dimension_rows[horse_key(row)]
            feature_rows.append(
                [
                    prior[horse],
                    float(dim["dim_stability"]),
                    float(dim["dim_trainer_signal"]),
                    0.80 * rating[horse] + 0.20 * experience[horse],
                    float(dim["dim_speed_engine"]),
                    mean_finish[horse],
                ]
            )
            horses.append(horse)
            positions.append(as_int(row["label_finish_position"], 99))
        field = len(rows)
        cutoff = min(5, max(3, math.ceil(field / 3)))
        relevance = np.array(
            [
                1.20 if position == 1
                else 1.00 if position <= 3
                else 0.20 if position <= cutoff
                else 0.0
                for position in positions
            ],
            dtype=float,
        )
        races.append(
            {
                "key": current_race,
                "meeting": current_race[1],
                "date": rows[0]["date"],
                "split": rows[0]["split"],
                "horses": np.array(horses, dtype=int),
                "positions": np.array(positions, dtype=int),
                "features": np.array(feature_rows, dtype=float),
                "relevance": relevance,
            }
        )
    return sorted(races, key=lambda race: (race["date"], race["meeting"], race["key"][2]))


def softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp = np.exp(shifted)
    return exp / np.sum(exp)


def pairwise_loss(weights: np.ndarray, races: list[dict[str, Any]]) -> float:
    total = pairs = 0.0
    for race in races:
        scores = race["features"] @ weights
        relevance = race["relevance"]
        for left in range(len(scores)):
            for right in range(len(scores)):
                gap = relevance[left] - relevance[right]
                if gap <= 0:
                    continue
                total += gap * float(np.logaddexp(0.0, -(scores[left] - scores[right]) / TEMPERATURE))
                pairs += gap
    return total / max(pairs, 1.0)


def objective(logits: np.ndarray, races: list[dict[str, Any]], regularization: float) -> float:
    weights = softmax(logits)
    return pairwise_loss(weights, races) + regularization * float(np.sum((weights - CURRENT) ** 2))


def fit(races: list[dict[str, Any]], regularization: float) -> np.ndarray:
    start = np.log(np.clip(CURRENT + np.array([0.0, 1e-4, 1e-4, 1e-4, 1e-4, 1e-4]), 1e-9, None))
    result = minimize(
        objective,
        start,
        args=(races, regularization),
        method="L-BFGS-B",
        options={"maxiter": 300},
    )
    return softmax(result.x)


def select_regularization(races: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    development = [race for race in races if race["split"] == "archive_development"]
    meetings = sorted({race["meeting"] for race in development})
    results = {}
    for regularization in REGULARIZATIONS:
        losses = []
        weights_by_fold = []
        for held in meetings:
            train = [race for race in development if race["meeting"] != held]
            validation = [race for race in development if race["meeting"] == held]
            weights = fit(train, regularization)
            losses.append(pairwise_loss(weights, validation))
            weights_by_fold.append(weights)
        results[str(regularization)] = {
            "mean_validation_pairwise_loss": round(float(np.mean(losses)), 6),
            "weight_sd": {
                feature: round(float(np.std([weights[idx] for weights in weights_by_fold])), 6)
                for idx, feature in enumerate(FEATURES)
            },
        }
    selected = min(
        REGULARIZATIONS,
        key=lambda value: (results[str(value)]["mean_validation_pairwise_loss"], -value),
    )
    return selected, results


def evaluate(races: list[dict[str, Any]], weights: np.ndarray) -> dict[str, Any]:
    metrics = []
    for race in races:
        scores = race["features"] @ weights
        order = sorted(range(len(scores)), key=lambda idx: (-scores[idx], int(race["horses"][idx])))
        picks = [int(race["horses"][idx]) for idx in order]
        positions = {
            int(race["horses"][idx]): int(race["positions"][idx])
            for idx in range(len(scores))
        }
        actual_top3 = [horse for horse, position in positions.items() if position <= 3]
        metrics.append(
            race_metrics(picks, actual_top3, actual_pos=positions, field_size=len(scores))
        )
    summary = summarize_races(metrics)
    comp = summary["competitiveness"]
    distribution = Counter(metric["top2_hits"] for metric in metrics)
    return {
        "races": len(metrics),
        "zero_hit": distribution[0],
        "one_hit": distribution[1],
        "two_hit": distribution[2],
        "top2_total_hits": sum(metric["top2_hits"] for metric in metrics),
        "top3_capture_at5": round(comp["mean_top3_capture_at5"], 6),
        "top3_all_within_top5": round(comp["top3_all_within_top5"]["rate"], 6),
        "competitive_recall_at5": round(comp["mean_competitive_recall_at5"], 6),
        "ndcg_at5": round(comp["mean_ndcg_at5"], 6),
        "winner_in_top5": round(summary["rates"]["winner_in_top5"], 6),
        "mrr": round(summary["mrr"], 6),
    }


def delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(candidate[key] - baseline[key], 6)
        for key in candidate
        if key != "races"
    }


def main() -> int:
    races = prepare()
    selected_reg, cv = select_regularization(races)
    development = [race for race in races if race["split"] == "archive_development"]
    learned = fit(development, selected_reg)
    slices = {
        "archive_development": development,
        "archive_temporal_holdout": [
            race for race in races if race["split"] == "archive_temporal_holdout"
        ],
        "independent_recent": [
            race for race in races if race["split"] == "independent_recent"
        ],
        "external_2026_07_15": [
            race for race in races if race["split"] == "external_2026_07_15"
        ],
        "all": races,
    }
    results = {}
    for name, current_races in slices.items():
        baseline = evaluate(current_races, CURRENT)
        candidate = evaluate(current_races, learned)
        results[name] = {
            "baseline": baseline,
            "candidate": candidate,
            "delta": delta(candidate, baseline),
        }
    holdout_names = (
        "archive_temporal_holdout",
        "independent_recent",
        "external_2026_07_15",
    )
    no_harm = all(
        results[name]["delta"]["zero_hit"] <= 0
        and results[name]["delta"]["top2_total_hits"] >= 0
        and results[name]["delta"]["top3_capture_at5"] >= 0
        and results[name]["delta"]["competitive_recall_at5"] >= 0
        and results[name]["delta"]["ndcg_at5"] >= 0
        and results[name]["delta"]["winner_in_top5"] >= 0
        and results[name]["delta"]["mrr"] >= -0.005
        for name in holdout_names
    )
    total = results["all"]["delta"]
    meaningful = (
        total["zero_hit"] <= -2
        and total["top2_total_hits"] >= 2
        and total["top3_capture_at5"] >= 0.005
        and total["competitive_recall_at5"] >= 0.005
        and total["ndcg_at5"] >= 0.002
    )
    passes = no_harm and meaningful
    payload = {
        "method": {
            "full_archive": True,
            "development_cv": "leave-one-meeting-out",
            "full_field_linear_formula": True,
            "micro_tiebreak": False,
            "blind_swap": False,
            "outcome_features_in_score": False,
        },
        "coverage": {
            "meetings": len({race["meeting"] for race in races}),
            "races": len(races),
            "runners": sum(len(race["horses"]) for race in races),
        },
        "selected_regularization": selected_reg,
        "cv": cv,
        "features": FEATURES,
        "weights": {
            feature: round(float(learned[idx]), 6)
            for idx, feature in enumerate(FEATURES)
        },
        "results": results,
        "passes": passes,
        "recommendation": "PROMOTE_TO_RICH_LIVE_GATE" if passes else "HOLD",
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# HKJC Full-Archive Competitiveness Calibration",
        "",
        f"- Coverage: {payload['coverage']['meetings']} meetings / {payload['coverage']['races']} races / {payload['coverage']['runners']} runners",
        f"- Selected regularization: {selected_reg}",
        f"- Recommendation: **{payload['recommendation']}**",
        "",
        "| Feature | Weight |",
        "|---|---:|",
    ]
    for feature, weight in payload["weights"].items():
        lines.append(f"| {feature} | {weight:.4f} |")
    lines.extend(
        [
            "",
            "| Slice | 0-hit Δ | Top2 hits Δ | Top3@5 Δ | Competitive recall@5 Δ | NDCG@5 Δ | Winner@5 Δ | MRR Δ |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name in slices:
        item = results[name]["delta"]
        lines.append(
            f"| {name} | {item['zero_hit']:+.0f} | {item['top2_total_hits']:+.0f} | "
            f"{item['top3_capture_at5']:+.4f} | {item['competitive_recall_at5']:+.4f} | "
            f"{item['ndcg_at5']:+.4f} | {item['winner_in_top5']:+.4f} | {item['mrr']:+.4f} |"
        )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "coverage": payload["coverage"],
                "weights": payload["weights"],
                "recommendation": payload["recommendation"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
