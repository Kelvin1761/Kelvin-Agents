#!/usr/bin/env python3
"""Reproducible old-vs-current AU performance comparison on one corpus."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from au_eval import (  # noqa: E402
    baseline_report,
    compare,
    default_scorer,
    load_races,
    verdict_dict,
)
from au_racing_engine.io_utils import write_json_atomic, write_text_atomic  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402


def pre_performance_quality_scorer(row):
    """Old production: stability's 40% branch used consistency fallback."""
    features = dict(row["features"])
    features["performance_quality_score"] = features.get(
        "consistency_score", 60.0,
    )
    matrices = map_features_to_matrix_scores(features)
    return sum(
        matrices.get(key, 60.0) * weight
        for key, weight in MATRIX_WEIGHTS.items()
    ) + float(row["wet"] or 0.0)


def metric_deltas(old, current):
    return {
        split: {
            key: current[split][key] - old[split][key]
            for key in current[split]
            if key in old[split]
        }
        for split in current
    }


def render_markdown(report):
    old = report["old"]["metrics"]
    new = report["current"]["metrics"]
    delta = report["metric_delta_pp"]
    verdict = report["paired_verdict"]
    lines = [
        "# AU Old vs Current Performance",
        "",
        "Old = the pre-performance-quality stability branch "
        "(`performance_quality_score := consistency_score`).",
        "Current = the live point-in-time performance-quality branch.",
        "Both versions use the same 805-race corpus, date partition and metric contract.",
        "",
        "## Full archive",
        "",
        "| Metric | Old | Current | Delta |",
        "|---|---:|---:|---:|",
    ]
    labels = {
        "gold": "Gold",
        "good_positional": "Good (Top-2 both place)",
        "pass": "Pass",
        "champion": "Top-1 win",
        "winner_in_top3": "Winner@3",
        "winner_in_top5": "Winner@5",
        "t3prec": "Top-3 precision",
    }
    for key, label in labels.items():
        lines.append(
            f"| {label} | {old['all'][key]:.2f}% | {new['all'][key]:.2f}% | "
            f"{delta['all'][key]:+.2f}pp |"
        )
    lines.extend([
        f"| Top-5 AUC | {report['old']['auc']['top_k_all']:.5f} | "
        f"{report['current']['auc']['top_k_all']:.5f} | "
        f"{report['auc_delta']['top_k_all']:+.5f} |",
        "",
        "## Date split",
        "",
        f"- Development / terminal races: "
        f"{report['current']['design']['development_races']} / "
        f"{report['current']['design']['terminal_holdout_races']}",
        f"- Development Top-5 AUC delta: {verdict['top_dev']:+.5f}",
        f"- Terminal Top-5 AUC delta: {verdict['top_hold']:+.5f} "
        f"(95% CI [{verdict['top_hold_ci'][0]:+.5f}, "
        f"{verdict['top_hold_ci'][1]:+.5f}])",
        f"- Promotion verdict: {'PASS' if verdict['ship'] else 'NO PASS'} — "
        f"{verdict['reason']}",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument(
        "--output-json", type=Path,
        default=Path("/private/tmp/au_version_comparison.json"),
    )
    parser.add_argument(
        "--output-md", type=Path,
        default=Path("/private/tmp/au_version_comparison.md"),
    )
    parser.add_argument("--holdout-fraction", type=float, default=0.15)
    args = parser.parse_args()

    races = load_races(args.dataset_json)
    old = baseline_report(races, args.holdout_fraction, pre_performance_quality_scorer)
    current = baseline_report(races, args.holdout_fraction, default_scorer)
    verdict = compare(
        races,
        pre_performance_quality_scorer,
        default_scorer,
        label="current performance-quality matrix vs old consistency branch",
        holdout=args.holdout_fraction,
    )
    report = {
        "design": {
            "dataset": str(args.dataset_json),
            "old_contract": "performance_quality_score := consistency_score",
            "current_contract": "live performance_quality_score with point-in-time fallback",
        },
        "old": old,
        "current": current,
        "metric_delta_pp": metric_deltas(old["metrics"], current["metrics"]),
        "auc_delta": {
            key: current["auc"][key] - old["auc"][key]
            for key in current["auc"]
        },
        "paired_verdict": verdict_dict(verdict),
    }
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    print(render_markdown(report))
    print(f"JSON: {args.output_json}\nMarkdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
