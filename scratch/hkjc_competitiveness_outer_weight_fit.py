#!/usr/bin/env python3
"""Fit a simple 7D outer matrix for competitive-field ranking.

Only the seven existing matrix scores are used.  No new feature, outcome
overlay, boundary swap or race-specific rule is introduced.  Regularization
is selected by leave-one-meeting-out CV inside the chronological development
set; the final temporal holdout remains untouched until weights are frozen.
"""
from __future__ import annotations

import argparse
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
sys.path.insert(
    0,
    str(
        ROOT
        / ".agents"
        / "skills"
        / "hkjc_racing"
        / "hkjc_wong_choi_auto"
        / "scripts"
        / "au_racing_engine"
    ),
)

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402


DEFAULT_INPUT = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_ranking_dataset.csv"
)
OUTPUT = ROOT / "scratch" / "hkjc_competitiveness_outer_weight_fit.json"
REPORT = ROOT / "scratch" / "hkjc_competitiveness_outer_weight_fit_report.md"
SECTIONS = tuple(MATRIX_WEIGHTS)
CURRENT = np.array([MATRIX_WEIGHTS[name] for name in SECTIONS], dtype=float)
REGULARIZATIONS = (0.25, 0.5, 1.0, 2.0, 4.0)
TEMPERATURE = 4.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    return parser.parse_args()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(number) else number


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp = np.exp(shifted)
    return exp / np.sum(exp)


def weights_to_logits(weights: np.ndarray) -> np.ndarray:
    return np.log(np.clip(weights, 1e-9, None))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def prepare_races(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["meeting_name"], as_int(row["race_number"]))].append(row)
    races = []
    for (meeting, race_number), race_rows in grouped.items():
        matrix = np.array(
            [
                [as_float(row.get(f"matrix_{section}"), 60.0) for section in SECTIONS]
                for row in race_rows
            ],
            dtype=float,
        )
        positions = np.array(
            [as_int(row["finish_pos"], 99) for row in race_rows],
            dtype=int,
        )
        field = len(race_rows)
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
                "meeting": meeting,
                "date": min(str(row.get("date") or "") for row in race_rows),
                "race": race_number,
                "horses": np.array([as_int(row["horse_number"]) for row in race_rows], dtype=int),
                "matrix": matrix,
                "positions": positions,
                "relevance": relevance,
            }
        )
    return sorted(races, key=lambda race: (race["date"], race["meeting"], race["race"]))


def pairwise_loss_for_weights(weights: np.ndarray, races: list[dict[str, Any]]) -> float:
    total = pairs = 0.0
    for race in races:
        scores = race["matrix"] @ weights
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
    return pairwise_loss_for_weights(weights, races) + regularization * float(np.sum((weights - CURRENT) ** 2))


def fit(races: list[dict[str, Any]], regularization: float) -> np.ndarray:
    result = minimize(
        objective,
        weights_to_logits(CURRENT),
        args=(races, regularization),
        method="L-BFGS-B",
        options={"maxiter": 300},
    )
    return softmax(result.x)


def chronological_split(races: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    dates = {}
    for race in races:
        dates.setdefault(race["meeting"], race["date"])
    meetings = [meeting for meeting, _ in sorted(dates.items(), key=lambda item: (item[1], item[0]))]
    cut = max(1, math.floor(len(meetings) * 0.70))
    return meetings[:cut], meetings[cut:]


def choose_regularization(races: list[dict[str, Any]], development_meetings: list[str]) -> tuple[float, dict[str, Any]]:
    results = {}
    for regularization in REGULARIZATIONS:
        fold_losses = []
        fold_weights = []
        for held_meeting in development_meetings:
            train = [
                race
                for race in races
                if race["meeting"] in development_meetings and race["meeting"] != held_meeting
            ]
            validation = [race for race in races if race["meeting"] == held_meeting]
            weights = fit(train, regularization)
            fold_losses.append(pairwise_loss_for_weights(weights, validation))
            fold_weights.append(weights)
        results[str(regularization)] = {
            "mean_validation_pairwise_loss": round(float(np.mean(fold_losses)), 6),
            "weight_sd": {
                section: round(float(np.std([weights[idx] for weights in fold_weights])), 6)
                for idx, section in enumerate(SECTIONS)
            },
        }
    selected = min(
        REGULARIZATIONS,
        key=lambda value: (
            results[str(value)]["mean_validation_pairwise_loss"],
            -value,
        ),
    )
    return selected, results


def evaluate(races: list[dict[str, Any]], weights: np.ndarray) -> dict[str, Any]:
    metrics = []
    for race in races:
        scores = race["matrix"] @ weights
        order = sorted(range(len(scores)), key=lambda idx: (-scores[idx], int(race["horses"][idx])))
        picks = [int(race["horses"][idx]) for idx in order]
        positions = {
            int(race["horses"][idx]): int(race["positions"][idx])
            for idx in range(len(scores))
        }
        actual_top3 = [horse for horse, position in positions.items() if position <= 3]
        metrics.append(
            race_metrics(
                picks,
                actual_top3,
                actual_pos=positions,
                field_size=len(scores),
            )
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
    source = Path(parse_args().input)
    races = prepare_races(read_csv(source))
    development_meetings, holdout_meetings = chronological_split(races)
    selected_reg, cv = choose_regularization(races, development_meetings)
    train_races = [race for race in races if race["meeting"] in development_meetings]
    holdout_races = [race for race in races if race["meeting"] in holdout_meetings]
    learned = fit(train_races, selected_reg)

    slices = {
        "development": train_races,
        "temporal_holdout": holdout_races,
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

    holdout = results["temporal_holdout"]["delta"]
    overall = results["all"]["delta"]
    passes = (
        holdout["zero_hit"] <= 0
        and holdout["top2_total_hits"] >= 0
        and holdout["top3_capture_at5"] >= 0
        and holdout["competitive_recall_at5"] >= 0
        and holdout["ndcg_at5"] >= 0
        and holdout["winner_in_top5"] >= 0
        and holdout["mrr"] >= -0.005
        and overall["zero_hit"] <= 0
        and overall["top2_total_hits"] >= 1
        and overall["top3_capture_at5"] >= 0.002
        and overall["competitive_recall_at5"] >= 0.002
        and overall["ndcg_at5"] >= 0.002
    )
    payload = {
        "method": {
            "source": str(source),
            "outer_weights_only": True,
            "target": "graded competitive tier",
            "development_cv": "leave-one-meeting-out",
            "temporal_holdout_locked": True,
            "micro_tiebreak": False,
            "blind_swap": False,
        },
        "coverage": {
            "meetings": len(development_meetings) + len(holdout_meetings),
            "races": len(races),
            "development_meetings": development_meetings,
            "holdout_meetings": holdout_meetings,
        },
        "selected_regularization": selected_reg,
        "cv": cv,
        "current_weights": {
            section: round(float(CURRENT[idx]), 6)
            for idx, section in enumerate(SECTIONS)
        },
        "learned_weights": {
            section: round(float(learned[idx]), 6)
            for idx, section in enumerate(SECTIONS)
        },
        "results": results,
        "passes": passes,
        "recommendation": "PROMOTE_TO_FULL_ARCHIVE_GATE" if passes else "HOLD",
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# HKJC Competitiveness Outer-Weight Fit",
        "",
        f"- Coverage: {payload['coverage']['meetings']} meetings / {payload['coverage']['races']} races",
        f"- Selected regularization: {selected_reg}",
        f"- Recommendation: **{payload['recommendation']}**",
        "",
        "| Dimension | Current | Learned | Δ |",
        "|---|---:|---:|---:|",
    ]
    for idx, section in enumerate(SECTIONS):
        lines.append(
            f"| {section} | {CURRENT[idx]:.4f} | {learned[idx]:.4f} | {learned[idx] - CURRENT[idx]:+.4f} |"
        )
    lines.extend(
        [
            "",
            "| Slice | 0-hit Δ | Top2 hits Δ | Top3@5 Δ | Competitive recall@5 Δ | NDCG@5 Δ | Winner@5 Δ | MRR Δ |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name in ("development", "temporal_holdout", "all"):
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
                "selected_regularization": selected_reg,
                "recommendation": payload["recommendation"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
