#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SHARED_RACING = SCRIPT_DIR.parents[2] / "shared_racing"
if str(SHARED_RACING) not in sys.path:
    sys.path.insert(0, str(SHARED_RACING))

from eval_metrics import race_metrics
from hkjc_results_db import get_analysis_archive_root, get_season_csvs, get_season_results_roots
from model_evaluation_decision import build_evaluation_input, evaluate_candidate
from review_auto_weighting import run_review


MAXIMIZE_KEYS = (
    "gold",
    "good",
    "min_threshold",
    "champion",
    "top3_has_champion",
    "mrr",
    "avg_top4_hits",
)
MINIMIZE_KEYS = ("order_issue", "avg_winner_rank", "avg_pick1_finish")


def _delta(candidate: dict[str, Any], baseline: dict[str, Any], key: str) -> float:
    return round(float(candidate.get(key, 0)) - float(baseline.get(key, 0)), 4)


def evaluate_gate(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    deltas = {key: _delta(candidate, baseline, key) for key in (*MAXIMIZE_KEYS, *MINIMIZE_KEYS)}
    failures: list[str] = []

    if int(candidate.get("races", 0)) != int(baseline.get("races", 0)):
        failures.append("race_count_changed")

    for key in MAXIMIZE_KEYS:
        if deltas[key] < 0:
            failures.append(f"{key}_down:{deltas[key]}")
    for key in MINIMIZE_KEYS:
        if deltas[key] > 0:
            failures.append(f"{key}_up:{deltas[key]}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "delta": deltas,
    }


def _canonical_metrics(race: dict[str, Any], model_name: str) -> dict[str, Any]:
    model = race["models"][model_name]
    actual_pos = {int(key): int(value) for key, value in race["actual_pos"].items()}
    picks = [int(value) for value in model.get("picks") or []]
    top3 = {horse for horse, position in actual_pos.items() if position <= 3}
    winner = next((horse for horse, position in actual_pos.items() if position == 1), None)
    ranking = race_metrics(
        picks,
        top3,
        winner=winner,
        actual_pos=actual_pos,
        field_size=len(actual_pos),
    )
    return {
        # Preserve HKJC's locked Gold/Good semantics as its primary KPIs.
        "gold": bool(model.get("gold")),
        "good_positional": bool(model.get("good")),
        "top3_capture_at5": ranking["top3_capture_at5"],
        "mean_top3_model_rank": ranking["top3_mean_model_rank"],
        "competitive_recall_at5": ranking["competitive_recall_at5"],
        "ndcg_at5": ranking["ndcg_at5"],
    }


def evaluate_stage4_candidate(
    race_records: list[dict[str, Any]],
    candidate_name: str,
    *,
    leakage_audit_passed: bool,
    holdout_fraction: float = 0.15,
) -> dict[str, Any]:
    eligible = [
        race
        for race in race_records
        if "current_live" in race.get("models", {})
        and candidate_name in race.get("models", {})
        and race.get("date")
    ]
    built = build_evaluation_input(
        domain="hkjc",
        dates=[str(race["date"]) for race in eligible],
        baseline_rows=[_canonical_metrics(race, "current_live") for race in eligible],
        candidate_rows=[_canonical_metrics(race, candidate_name) for race in eligible],
        leakage_audit_passed=leakage_audit_passed,
        holdout_fraction=holdout_fraction,
        ranking_metrics=(
            "top3_capture_at5",
            "ndcg_at5",
            "competitive_recall_at5",
        ),
    )
    return evaluate_candidate(built)


def run_gate(*, leakage_audit_passed: bool = False) -> dict[str, Any]:
    review = run_review(
        [get_analysis_archive_root()],
        get_season_results_roots() + [get_analysis_archive_root()],
        get_season_csvs(),
        include_races=True,
    )
    baseline = review["model_summary"]["current_live"]
    model_roles = review.get("model_roles", {})

    candidates = {}
    for model_name, metrics in sorted(review["model_summary"].items()):
        if model_name == "current_live":
            continue
        if model_roles.get(model_name) != "experimental":
            continue
        stage4 = evaluate_stage4_candidate(
            review["race_records"],
            model_name,
            leakage_audit_passed=leakage_audit_passed,
        )
        candidates[model_name] = {
            "metrics": metrics,
            **evaluate_gate(metrics, baseline),
            "stage4": stage4,
        }

    passing = {
        name: data
        for name, data in candidates.items()
        if data["status"] == "PASS"
        and data["stage4"]["verdict"] in {"PRIMARY_WIN", "RANKING_WIN"}
    }
    return {
        "baseline_model": "current_live",
        "baseline_metrics": baseline,
        "gate": {
            "maximize": MAXIMIZE_KEYS,
            "minimize": MINIMIZE_KEYS,
            "rule": "candidate must not regress any listed all-archive metric versus current_live",
            "stage4_rule": "Gold/Good primary; supported ranking-only path; locked terminal holdout",
            "leakage_audit_passed": leakage_audit_passed,
        },
        "passing_candidates": passing,
        "candidate_results": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="HKJC all-archive no-regression gate for scoring candidates")
    parser.add_argument("--json", action="store_true", help="Emit full JSON")
    parser.add_argument(
        "--leakage-audit-passed",
        action="store_true",
        help="Confirm the candidate's separate point-in-time leakage audit passed",
    )
    args = parser.parse_args()

    result = run_gate(leakage_audit_passed=args.leakage_audit_passed)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    baseline = result["baseline_metrics"]
    print("HKJC no-regression gate")
    print(f"- Baseline: current_live ({baseline.get('races', 0)} races)")
    print(
        "- Metrics: "
        f"Gold {baseline.get('gold')}, Good {baseline.get('good')}, "
        f"Pass {baseline.get('min_threshold')}, Champion {baseline.get('champion')}, "
        f"MRR {baseline.get('mrr')}, Order Issue {baseline.get('order_issue')}, "
        f"Avg Top4 Hits {baseline.get('avg_top4_hits')}"
    )
    if result["passing_candidates"]:
        print("- Passing candidates:")
        for name in result["passing_candidates"]:
            print(f"  - {name}")
    else:
        print("- Passing candidates: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
