#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
import argparse

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from train_hkjc_7d_ml_weights import (  # noqa: E402
    CURRENT_MATRIX_FORMULAS,
    CURRENT_MATRIX_WEIGHTS,
    SECTIONS,
    TRAINABLE_SECTIONS,
    _weights_from_fit,
    build_dataset,
    default_meeting_roots,
    default_results_roots,
    evaluate_weight_set,
    fit_weights,
    walk_forward_fit,
)


def current_inner_weights() -> dict[str, np.ndarray]:
    return {
        section: np.array([weight for _feature, weight in CURRENT_MATRIX_FORMULAS[section]], dtype=float)
        for section in TRAINABLE_SECTIONS
    }


def outer_array(weights: dict[str, float]) -> np.ndarray:
    return np.array([weights[section] for section in SECTIONS], dtype=float)


def apply_delta(label: str, deltas: dict[str, float]) -> dict[str, Any]:
    weights = dict(CURRENT_MATRIX_WEIGHTS)
    for key, value in deltas.items():
        weights[key] = round(weights[key] + value, 4)
    total = sum(weights.values())
    weights = {key: round(value / total, 4) for key, value in weights.items()}
    return {"label": label, "weights": weights}


def summarize(label: str, races: list[dict[str, Any]], weights: dict[str, float]) -> dict[str, Any]:
    stats = evaluate_weight_set(races, current_inner_weights(), outer_array(weights))
    return {"label": label, "races": len(races), "weights": weights, "stats": stats}


def delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    c = candidate["stats"]
    b = baseline["stats"]
    keys = (
        "gold",
        "good",
        "min_threshold",
        "single",
        "champion",
        "top3_has_champion",
        "order_issue",
        "avg_winner_rank",
        "mrr",
        "avg_pick1_finish",
        "avg_top4_hits",
    )
    return {key: round(float(c.get(key, 0)) - float(b.get(key, 0)), 4) for key in keys}


def subset_rows(races: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    if kind == "all":
        return races
    if kind == "happy_valley":
        return [
            race
            for race in races
            if "happyvalley" in str(race.get("venue", "")).lower()
            or "happy valley" in str(race.get("venue", "")).lower()
            or "跑馬地" in str(race.get("venue", ""))
            or "HappyValley" in str(race.get("meeting", ""))
        ]
    if kind == "target_2026_06_10":
        return [race for race in races if str(race.get("date")) == "2026-06-10"]
    raise ValueError(kind)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--walk-forward", action="store_true", help="Run slower expanding walk-forward ML validation")
    parser.add_argument("--maxiter", type=int, default=60)
    args = parser.parse_args()

    dataset = build_dataset(default_meeting_roots(), default_results_roots())
    races = dataset["races"]
    candidates = [
        {"label": "current_live", "weights": dict(CURRENT_MATRIX_WEIGHTS)},
        apply_delta("light_shape_down_form_class_up", {
            "race_shape": -0.0200,
            "form_line": 0.0100,
            "class_advantage": 0.0100,
        }),
        apply_delta("medium_shape_down_form_class_up", {
            "race_shape": -0.0300,
            "form_line": 0.0150,
            "class_advantage": 0.0150,
        }),
        apply_delta("shape_to_024_form_class_up", {
            "race_shape": -0.0160,
            "form_line": 0.0080,
            "class_advantage": 0.0080,
        }),
        apply_delta("shape_down_form_class_sectional_up", {
            "race_shape": -0.0300,
            "form_line": 0.0125,
            "class_advantage": 0.0125,
            "sectional": 0.0050,
        }),
    ]

    scopes: dict[str, Any] = {}
    for scope_name in ("all", "happy_valley", "target_2026_06_10"):
        scope_races = subset_rows(races, scope_name)
        baseline = summarize("current_live", scope_races, dict(CURRENT_MATRIX_WEIGHTS))
        rows = []
        for candidate in candidates:
            row = summarize(candidate["label"], scope_races, candidate["weights"])
            row["delta_vs_current"] = delta(row, baseline)
            rows.append(row)
        scopes[scope_name] = rows

    ml_fit = fit_weights(
        races,
        temperature=6.0,
        winner_loss_share=0.45,
        pairwise_loss_share=0.35,
        regularization=0.18,
        maxiter=args.maxiter,
    )
    ml_full_sample = {}
    if ml_fit:
        ml_inner, ml_outer = _weights_from_fit(ml_fit)
        ml_full_sample = {
            "fit": ml_fit,
            "all": evaluate_weight_set(subset_rows(races, "all"), ml_inner, ml_outer),
            "happy_valley": evaluate_weight_set(subset_rows(races, "happy_valley"), ml_inner, ml_outer),
            "target_2026_06_10": evaluate_weight_set(subset_rows(races, "target_2026_06_10"), ml_inner, ml_outer),
        }

    walk_forward = {}
    if args.walk_forward:
        walk_forward = walk_forward_fit(
            races,
            min_train_races=48,
            min_train_meetings=8,
            min_slice_races=18,
            min_slice_meetings=3,
            temperature=6.0,
            winner_loss_share=0.45,
            pairwise_loss_share=0.35,
            regularization=0.18,
            maxiter=args.maxiter,
        )

    report = {
        "coverage": dataset["coverage"],
        "candidate_note": "shadow only; no production code or micro tie-break changes",
        "scopes": scopes,
        "ml_full_sample": ml_full_sample,
        "ml_walk_forward": {
            "folds": walk_forward.get("folds"),
            "global_summary": walk_forward.get("global_summary"),
            "sliced_summary": walk_forward.get("sliced_summary"),
            "average_outer_weights": walk_forward.get("average_outer_weights"),
            "slice_source_usage": walk_forward.get("slice_source_usage"),
            "fold_rows": walk_forward.get("fold_rows"),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
