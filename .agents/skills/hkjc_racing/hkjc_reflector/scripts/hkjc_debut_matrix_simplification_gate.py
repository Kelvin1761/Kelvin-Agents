#!/usr/bin/env python3
"""Gate removal of the HKJC debut-only outer-weight formula.

The candidate changes only debut runners: their matrix scores use the same 7D
outer weights as every other horse.  This is both a model simplification and a
testable hypothesis that the current 30% horse-health debut weight suppresses
true competitiveness.

The primary replay uses materialized production matrix scores.  Published rank
order is preserved by monotonising archived ability scores before applying the
candidate delta.  A 70/30 meeting-time split is fixed before evaluation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
ENGINE = (
    ROOT / ".agents" / "skills" / "hkjc_racing"
    / "hkjc_wong_choi_auto" / "scripts" / "hkjc_racing_engine"
)
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(ENGINE))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from hkjc_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402


DEFAULT_DATASET = (
    ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector"
    / "artifacts" / "hkjc_ranking_dataset.csv"
)
DEFAULT_OUTPUT = ROOT / "scratch" / "hkjc_debut_matrix_simplification_gate.json"
DEFAULT_REPORT = ROOT / "scratch" / "hkjc_debut_matrix_simplification_gate_report.md"

CURRENT_DEBUT_WEIGHTS = {
    "trainer_signal": 0.30,
    "horse_health": 0.30,
    "race_shape": 0.20,
    "stability": 0.15,
    "class_advantage": 0.05,
}
CANDIDATES = {
    "shared_7d_weights": {
        "weights": MATRIX_WEIGHTS,
        "hypothesis": "取消初出馬outer-weight特例；保留各feature本身嘅初出馬中性／備戰處理。",
    },
    "trial_sectional_10": {
        "weights": {
            "sectional": 0.10,
            "trainer_signal": 0.30,
            "stability": 0.15,
            "race_shape": 0.20,
            "class_advantage": 0.05,
            "horse_health": 0.20,
        },
        "hypothesis": "只將10%由health轉到試閘／段速。",
    },
    "balanced_debut": {
        "weights": {
            "sectional": 0.15,
            "trainer_signal": 0.25,
            "stability": 0.20,
            "race_shape": 0.20,
            "class_advantage": 0.05,
            "horse_health": 0.15,
        },
        "hypothesis": "降低單一health/trainer集中度。",
    },
}


def as_float(value: Any, default: float = 60.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def load_races(path: Path) -> dict[tuple[str, int], list[dict[str, Any]]]:
    grouped: defaultdict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            meeting = str(raw.get("meeting_name") or Path(str(raw.get("meeting") or "")).name)
            race_number = as_int(raw.get("race_number"))
            number = as_int(raw.get("horse_number"))
            rank = as_int(raw.get("current_live_rank"))
            finish = as_int(raw.get("finish_pos"))
            if not meeting or min(race_number, number, rank, finish) <= 0:
                continue
            matrices = {
                key: as_float(raw.get(f"matrix_{key}"))
                for key in MATRIX_WEIGHTS
            }
            grouped[(meeting, race_number)].append(
                {
                    "meeting": meeting,
                    "date": str(raw.get("date") or meeting[:10]),
                    "race": race_number,
                    "number": number,
                    "name": str(raw.get("horse_name") or ""),
                    "published_rank": rank,
                    "published_ability": as_float(raw.get("current_live_ability")),
                    "finish": finish,
                    "is_debut": as_int(raw.get("is_debut")) == 1,
                    "matrices": matrices,
                }
            )

    races = {}
    for key, rows in grouped.items():
        if len(rows) < 3 or len({row["published_rank"] for row in rows}) != len(rows):
            continue
        # Archive files from one late meeting contain ability values generated
        # after the stored rank.  Enforce the published order with the smallest
        # possible monotonic adjustment before adding any candidate delta.
        previous = float("inf")
        for row in sorted(rows, key=lambda item: item["published_rank"]):
            calibrated = min(row["published_ability"], previous - 0.001)
            row["calibrated_ability"] = calibrated
            previous = calibrated
        races[key] = rows
    return races


def formula_score(row: dict[str, Any], weights: dict[str, float]) -> float:
    return sum(row["matrices"].get(key, 60.0) * weight for key, weight in weights.items())


def candidate_score(row: dict[str, Any], candidate: str) -> float:
    base = row["calibrated_ability"]
    if not row["is_debut"] or candidate == "published_baseline":
        return base
    current = formula_score(row, CURRENT_DEBUT_WEIGHTS)
    replacement = formula_score(row, CANDIDATES[candidate]["weights"])
    return base + replacement - current


def evaluate(races: list[list[dict[str, Any]]], candidate: str) -> tuple[dict[str, Any], dict[tuple[str, int], dict[str, Any]]]:
    metrics = []
    per_race = {}
    for rows in races:
        ranked = sorted(
            rows,
            key=lambda row: (
                -candidate_score(row, candidate),
                row["published_rank"],
                row["number"],
            ),
        )
        picks = [row["number"] for row in ranked]
        positions = {row["number"]: row["finish"] for row in ranked}
        top3 = [horse for horse, position in positions.items() if position <= 3]
        item = race_metrics(picks, top3, actual_pos=positions, field_size=len(positions))
        metrics.append(item)
        per_race[(rows[0]["meeting"], rows[0]["race"])] = {
            "top5": picks[:5],
            "top2_hits": item["top2_hits"],
            "top3_capture_at5": item["top3_capture_at5"],
            "winner_rank": item["winner_rank"],
            "ndcg_at5": item["ndcg_at5"],
        }
    return compact_summary(metrics), per_race


def compact_summary(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_races(metrics)
    comp = summary["competitiveness"]
    distribution = Counter(row["top2_hits"] for row in metrics)
    return {
        "races": len(metrics),
        "zero_hit": distribution[0],
        "one_hit": distribution[1],
        "two_hit": distribution[2],
        "top3_capture_at5": round(comp["mean_top3_capture_at5"], 4),
        "top3_all_within_top5": round(comp["top3_all_within_top5"]["rate"], 4),
        "ndcg_at5": round(comp["mean_ndcg_at5"], 4),
        "winner_in_top5": round(summary["rates"]["winner_in_top5"], 4),
        "mrr": round(summary["mrr"], 4),
    }


def deltas(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(candidate[key] - baseline[key], 4)
        for key in (
            "zero_hit",
            "one_hit",
            "two_hit",
            "top3_capture_at5",
            "top3_all_within_top5",
            "ndcg_at5",
            "winner_in_top5",
            "mrr",
        )
    }


def gate_candidate(results: dict[str, Any]) -> dict[str, Any]:
    development = results["development"]["delta"]
    holdout = results["temporal_holdout"]["delta"]
    debut_all = results["debut_all"]["delta"]
    debut_holdout = results["debut_temporal_holdout"]["delta"]
    no_harm_keys = ("top3_capture_at5", "ndcg_at5", "winner_in_top5", "mrr")
    no_harm = all(
        block[key] >= 0
        for block in (development, holdout, debut_all, debut_holdout)
        for key in no_harm_keys
    )
    zero_no_harm = all(
        block["zero_hit"] <= 0
        for block in (development, holdout, debut_all, debut_holdout)
    )
    holdout_lift = sum(debut_holdout[key] > 0 for key in no_harm_keys)
    all_lift = sum(debut_all[key] > 0 for key in no_harm_keys)
    passes = no_harm and zero_no_harm and holdout_lift >= 3 and all_lift >= 3
    return {
        "passes": passes,
        "no_harm_ranking_metrics": no_harm,
        "zero_hit_no_harm": zero_no_harm,
        "debut_holdout_metrics_improved": holdout_lift,
        "debut_all_metrics_improved": all_lift,
        "minimum_debut_holdout_races": results["debut_temporal_holdout"]["candidate"]["races"] >= 8,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    grouped = load_races(args.dataset)
    meeting_order = sorted({meeting for meeting, _race in grouped})
    cut_index = max(1, math.floor(len(meeting_order) * 0.70))
    development_meetings = set(meeting_order[:cut_index])
    holdout_meetings = set(meeting_order[cut_index:])
    all_races = list(grouped.values())
    slices = {
        "all": all_races,
        "development": [rows for rows in all_races if rows[0]["meeting"] in development_meetings],
        "temporal_holdout": [rows for rows in all_races if rows[0]["meeting"] in holdout_meetings],
        "debut_all": [rows for rows in all_races if any(row["is_debut"] for row in rows)],
        "debut_development": [
            rows for rows in all_races
            if rows[0]["meeting"] in development_meetings and any(row["is_debut"] for row in rows)
        ],
        "debut_temporal_holdout": [
            rows for rows in all_races
            if rows[0]["meeting"] in holdout_meetings and any(row["is_debut"] for row in rows)
        ],
    }
    baseline = {name: evaluate(races, "published_baseline")[0] for name, races in slices.items()}
    candidate_results = {}
    gates = {}
    for candidate in CANDIDATES:
        result = {}
        for name, races in slices.items():
            summary, _per_race = evaluate(races, candidate)
            result[name] = {
                "baseline": baseline[name],
                "candidate": summary,
                "delta": deltas(summary, baseline[name]),
            }
        candidate_results[candidate] = result
        gates[candidate] = gate_candidate(result)

    payload = {
        "method": {
            "candidate_changes_only_debut_runners": True,
            "published_rank_order_preserved_before_delta": True,
            "meeting_time_split": {
                "development": meeting_order[:cut_index],
                "temporal_holdout": meeting_order[cut_index:],
            },
            "outcome_features_in_score": False,
            "odds_in_score": False,
            "micro_tiebreak": False,
            "blind_swap": False,
        },
        "coverage": {
            "meetings": len(meeting_order),
            "races": len(all_races),
            "debut_races": len(slices["debut_all"]),
            "debut_runners": sum(row["is_debut"] for rows in all_races for row in rows),
            "temporal_holdout_races": len(slices["temporal_holdout"]),
            "debut_temporal_holdout_races": len(slices["debut_temporal_holdout"]),
        },
        "current_debut_weights": CURRENT_DEBUT_WEIGHTS,
        "candidates": CANDIDATES,
        "results": candidate_results,
        "gates": gates,
        "recommendation": (
            "PROMOTE_SHARED_7D"
            if gates["shared_7d_weights"]["passes"]
            else "HOLD_CURRENT_DEBUT_WEIGHTS"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shared = candidate_results["shared_7d_weights"]
    lines = [
        "# HKJC 初出馬 Matrix 簡化 Gate",
        "",
        f"- Coverage: {len(all_races)} races / {len(slices['debut_all'])} debut races / {payload['coverage']['debut_runners']} debut runners",
        f"- Temporal holdout: {len(slices['temporal_holdout'])} races；其中 debut {len(slices['debut_temporal_holdout'])} races",
        f"- Recommendation: **{payload['recommendation']}**",
        "",
        "| Slice | 0-hit Δ | Top3@5 Δ | 全部前三@5 Δ | NDCG@5 Δ | Winner@5 Δ | MRR Δ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("all", "development", "temporal_holdout", "debut_all", "debut_development", "debut_temporal_holdout"):
        delta = shared[name]["delta"]
        lines.append(
            f"| {name} | {delta['zero_hit']:+.0f} | {delta['top3_capture_at5']:+.4f} | "
            f"{delta['top3_all_within_top5']:+.4f} | {delta['ndcg_at5']:+.4f} | "
            f"{delta['winner_in_top5']:+.4f} | {delta['mrr']:+.4f} |"
        )
    lines.extend(
        [
            "",
            "Shared 7D candidate 只移除 debut outer-weight 特例；初出馬本身嘅 feature neutralisation、試閘、健康及 confidence 邏輯全部保留。",
            "",
        ]
    )
    args.report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"coverage": payload["coverage"], "recommendation": payload["recommendation"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
