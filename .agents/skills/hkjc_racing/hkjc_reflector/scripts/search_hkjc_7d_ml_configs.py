#!/usr/bin/env python3
"""
search_hkjc_7d_ml_configs.py — coarse config search for HKJC 7D ML trainer.

Searches over a small grid of training configs and compares:
- current_live on held-out walk-forward meetings
- ML global walk-forward
- ML sliced walk-forward

The goal is not to replace a full ranking model, but to identify whether the
current 7D-weight-learning setup has headroom before we move to a richer model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from train_hkjc_7d_ml_weights import (
    build_dataset,
    default_meeting_roots,
    default_results_roots,
    evaluate_current_live,
    walk_forward_fit,
)


DEFAULT_TEMPERATURES = [4.5, 6.0, 7.5]
DEFAULT_WINNER_SHARES = [0.35, 0.45, 0.55]
DEFAULT_PAIRWISE_SHARES = [0.20, 0.35, 0.50]
DEFAULT_REGULARIZATIONS = [0.10, 0.18, 0.28]
DEFAULT_MIN_SLICE_RACES = [16, 18, 22]
DEFAULT_MIN_SLICE_MEETINGS = [3, 4]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search HKJC 7D ML trainer configs")
    parser.add_argument("--meeting-root", action="append", default=[], help="Root folder to scan for HKJC meetings")
    parser.add_argument("--results-root", action="append", default=[], help="Root folder containing HKJC results")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument("--max-runs", type=int, default=24, help="Hard cap on number of configs to evaluate")
    parser.add_argument("--min-train-races", type=int, default=48)
    parser.add_argument("--min-train-meetings", type=int, default=8)
    parser.add_argument("--maxiter", type=int, default=200)
    return parser.parse_args()


def _candidate_configs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for temperature in DEFAULT_TEMPERATURES:
        for winner_share in DEFAULT_WINNER_SHARES:
            for pairwise_share in DEFAULT_PAIRWISE_SHARES:
                if winner_share + pairwise_share >= 0.95:
                    continue
                for regularization in DEFAULT_REGULARIZATIONS:
                    for min_slice_races in DEFAULT_MIN_SLICE_RACES:
                        for min_slice_meetings in DEFAULT_MIN_SLICE_MEETINGS:
                            rows.append(
                                {
                                    "temperature": temperature,
                                    "winner_loss_share": winner_share,
                                    "pairwise_loss_share": pairwise_share,
                                    "regularization": regularization,
                                    "min_slice_races": min_slice_races,
                                    "min_slice_meetings": min_slice_meetings,
                                }
                            )
    rows.sort(
        key=lambda row: (
            abs((row["winner_loss_share"] + row["pairwise_loss_share"]) - 0.75),
            row["regularization"],
            row["temperature"],
            row["min_slice_races"],
            row["min_slice_meetings"],
        )
    )
    return rows


def _score_tuple(stats: dict[str, Any]) -> tuple:
    return (
        int(stats.get("champion", 0)),
        int(stats.get("gold", 0)),
        int(stats.get("min_threshold", 0)),
        float(stats.get("mrr", 0.0)),
        -float(stats.get("avg_pick1_finish", 99.0)),
        float(stats.get("avg_top4_hits", 0.0)),
    )


def _heldout_meetings_from_walk_forward(wf: dict[str, Any]) -> set[str]:
    return {row["meeting"] for row in wf.get("fold_rows", [])}


def run_search(args: argparse.Namespace) -> dict[str, Any]:
    meeting_roots = [Path(path) for path in args.meeting_root] or default_meeting_roots()
    results_roots = [Path(path) for path in args.results_root] or default_results_roots()
    dataset = build_dataset(meeting_roots, results_roots)
    races = dataset["races"]

    candidates = _candidate_configs()[: args.max_runs]
    current_live_heldout = None
    results: list[dict[str, Any]] = []

    for idx, config in enumerate(candidates, start=1):
        wf = walk_forward_fit(
            races,
            min_train_races=args.min_train_races,
            min_train_meetings=args.min_train_meetings,
            min_slice_races=config["min_slice_races"],
            min_slice_meetings=config["min_slice_meetings"],
            temperature=config["temperature"],
            winner_loss_share=config["winner_loss_share"],
            pairwise_loss_share=config["pairwise_loss_share"],
            regularization=config["regularization"],
            maxiter=args.maxiter,
        )
        heldout_meetings = _heldout_meetings_from_walk_forward(wf)
        heldout_races = [race for race in races if race["meeting"] in heldout_meetings]
        if current_live_heldout is None:
            current_live_heldout = evaluate_current_live(heldout_races)

        global_stats = wf.get("global_summary") or {}
        sliced_stats = wf.get("sliced_summary") or {}

        results.append(
            {
                "rank_index": idx,
                "config": config,
                "global_summary": global_stats,
                "sliced_summary": sliced_stats,
                "slice_source_usage": wf.get("slice_source_usage") or {},
                "global_score_tuple": _score_tuple(global_stats),
                "sliced_score_tuple": _score_tuple(sliced_stats),
            }
        )

    best_global = max(results, key=lambda row: row["global_score_tuple"]) if results else None
    best_sliced = max(results, key=lambda row: row["sliced_score_tuple"]) if results else None

    return {
        "coverage": dataset["coverage"],
        "evaluated_configs": len(results),
        "current_live_heldout": current_live_heldout or {},
        "best_global": best_global,
        "best_sliced": best_sliced,
        "top_results": sorted(results, key=lambda row: row["sliced_score_tuple"], reverse=True)[:8],
    }


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    lines = [
        "# HKJC 7D ML Config Search",
        "",
        "## Coverage",
        f"- Meetings matched: {coverage['meetings']}",
        f"- Races matched: {coverage['races']}",
        f"- Horses rescored: {coverage['horses']}",
        f"- Configs evaluated: {report['evaluated_configs']}",
        "",
        "## Held-Out Baseline",
        f"- current_live: `{json.dumps(report['current_live_heldout'], ensure_ascii=False, sort_keys=True)}`",
    ]

    if report["best_global"]:
        lines.extend(
            [
                "",
                "## Best Global Walk-Forward",
                f"- Config: `{json.dumps(report['best_global']['config'], ensure_ascii=False, sort_keys=True)}`",
                f"- Result: `{json.dumps(report['best_global']['global_summary'], ensure_ascii=False, sort_keys=True)}`",
            ]
        )
    if report["best_sliced"]:
        lines.extend(
            [
                "",
                "## Best Sliced Walk-Forward",
                f"- Config: `{json.dumps(report['best_sliced']['config'], ensure_ascii=False, sort_keys=True)}`",
                f"- Result: `{json.dumps(report['best_sliced']['sliced_summary'], ensure_ascii=False, sort_keys=True)}`",
                f"- Slice usage: `{json.dumps(report['best_sliced']['slice_source_usage'], ensure_ascii=False, sort_keys=True)}`",
            ]
        )

    if report["top_results"]:
        lines.extend(
            [
                "",
                "## Top Results",
                "",
                "| Rank | Temp | Winner | Pairwise | Reg | Slice Races | Slice Mtgs | Global Champ | Sliced Champ | Global MRR | Sliced MRR | Global Pick1 | Sliced Pick1 |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in report["top_results"]:
            cfg = row["config"]
            g = row["global_summary"]
            s = row["sliced_summary"]
            lines.append(
                f"| {row['rank_index']} | {cfg['temperature']} | {cfg['winner_loss_share']} | {cfg['pairwise_loss_share']} | "
                f"{cfg['regularization']} | {cfg['min_slice_races']} | {cfg['min_slice_meetings']} | "
                f"{g.get('champion', 0)} | {s.get('champion', 0)} | {g.get('mrr', '-')} | {s.get('mrr', '-')} | "
                f"{g.get('avg_pick1_finish', '-')} | {s.get('avg_pick1_finish', '-')} |"
            )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = run_search(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
