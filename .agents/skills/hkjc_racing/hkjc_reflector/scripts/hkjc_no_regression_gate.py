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

from hkjc_results_db import get_analysis_archive_root, get_season_csvs, get_season_results_roots
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


def run_gate() -> dict[str, Any]:
    review = run_review(
        [get_analysis_archive_root()],
        get_season_results_roots() + [get_analysis_archive_root()],
        get_season_csvs(),
        include_races=False,
    )
    baseline = review["model_summary"]["current_live"]
    model_roles = review.get("model_roles", {})

    candidates = {}
    for model_name, metrics in sorted(review["model_summary"].items()):
        if model_name == "current_live":
            continue
        if model_roles.get(model_name) != "experimental":
            continue
        candidates[model_name] = {
            "metrics": metrics,
            **evaluate_gate(metrics, baseline),
        }

    passing = {name: data for name, data in candidates.items() if data["status"] == "PASS"}
    return {
        "baseline_model": "current_live",
        "baseline_metrics": baseline,
        "gate": {
            "maximize": MAXIMIZE_KEYS,
            "minimize": MINIMIZE_KEYS,
            "rule": "candidate must not regress any listed all-archive metric versus current_live",
        },
        "passing_candidates": passing,
        "candidate_results": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="HKJC all-archive no-regression gate for scoring candidates")
    parser.add_argument("--json", action="store_true", help="Emit full JSON")
    args = parser.parse_args()

    result = run_gate()
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
