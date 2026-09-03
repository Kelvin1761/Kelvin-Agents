#!/usr/bin/env python3
"""Test Racenet run-shape × expected-pace interactions without new micro rules.

Each race is scored once by the current engine. Candidate rankings are then
recomposed from the same pre-race feature vector after a single conditional
pace-map interaction. Actual position/SP remain outcome-only labels.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from au_archive_calibrator import (
    detect_meeting_date,
    load_historical_results,
    parse_int,
)
from au_runtime_micro_ablation import (
    aligned_race,
    build_report,
    discover_logic_files,
    iter_aligned_races,
    metric_delta,
    metrics_for_scored_races,
    render_markdown,
    score_variant,
    select_indices,
)
from au_racing_engine.scoring import compose_matrix_score
from au_racing_engine.io_utils import write_json_atomic, write_text_atomic
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score


VARIANTS = (
    ("revised_current", "", 0.0),
    ("pace_shape:all_s50", "all", 0.5),
    ("pace_shape:all_s100", "all", 1.0),
    ("pace_shape:clear_s50", "clear", 0.5),
    ("pace_shape:clear_s100", "clear", 1.0),
    ("pace_shape:large_s50", "large", 0.5),
    ("pace_shape:large_s100", "large", 1.0),
    ("pace_shape:large_clear_s50", "large_clear", 0.5),
    ("pace_shape:large_clear_s100", "large_clear", 1.0),
    ("pace_shape:missing_pf_s50", "missing_pf", 0.5),
    ("pace_shape:missing_pf_s100", "missing_pf", 1.0),
    ("pace_shape:large_missing_pf_s50", "large_missing_pf", 0.5),
    ("pace_shape:large_missing_pf_s100", "large_missing_pf", 1.0),
)


def raw_pace_adjustment(speed_map: dict, horse_number: int) -> float:
    """Return the existing symmetric role-vs-tempo interaction in score points."""
    if not isinstance(speed_map, dict) or not horse_number:
        return 0.0

    def bucket(name: str) -> set[int]:
        output = set()
        for value in speed_map.get(name) or []:
            parsed = parse_int(value)
            if parsed:
                output.add(parsed)
        return output

    role = next(
        (
            name
            for name in ("leaders", "on_pace", "pressers", "mid_pack", "closers")
            if horse_number in bucket(name)
        ),
        None,
    )
    if role is None:
        return 0.0
    pace = str(
        speed_map.get("predicted_pace")
        or speed_map.get("expected_pace")
        or ""
    ).lower()
    lead_pressure = len(bucket("leaders")) + len(bucket("pressers"))
    slow = any(token in pace for token in ("極慢", "慢", "controlled", "slow"))
    fast = any(token in pace for token in ("極快", "快", "hot", "fast", "genuine"))
    slow = slow or (not fast and len(bucket("leaders")) == 0 and len(bucket("pressers")) <= 1)
    fast = fast or (not slow and lead_pressure >= 5)
    if slow == fast:
        return 0.0
    if slow:
        return {
            "leaders": 3.0,
            "on_pace": 3.0,
            "pressers": 1.5,
            "mid_pack": 0.0,
            "closers": -3.0,
        }.get(role, 0.0)
    return {
        "closers": 3.0,
        "mid_pack": 1.0,
        "pressers": -1.0,
        "on_pace": -2.0,
        "leaders": -3.0,
    }.get(role, 0.0)


def applies(mode: str, *, large: bool, clear: bool, missing_pf: bool) -> bool:
    return {
        "all": True,
        "clear": clear,
        "large": large,
        "large_clear": large and clear,
        "missing_pf": missing_pf,
        "large_missing_pf": large and missing_pf,
    }.get(mode, False)


def recompose_row(
    row: dict,
    *,
    adjustment: float,
    scale: float,
) -> dict:
    output = dict(row)
    features = dict(row["feature_scores"])
    features["pace_map_score"] = clip_score(
        features.get("pace_map_score", 60.0) + adjustment * scale
    )
    matrix = map_features_to_matrix_scores(features)
    output["score"] = round(
        compose_matrix_score(matrix)
        + float(row.get("wet_form_feature") or 0.0)
        + float(row.get("proven_class_feature") or 0.0),
        4,
    )
    return output


def render_with_cohorts(report: dict) -> str:
    lines = render_markdown(report).rstrip().splitlines()
    lines.extend(
        [
            "",
            "## Target cohorts",
            "",
            "| Variant | 13+ Comp R@5 Δ | 13+ NDCG Δ | 13+ W@5 Δ | PF-missing Comp R@5 Δ | PF-missing NDCG Δ |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, cohorts in report["target_cohorts"].items():
        large = cohorts["large_field_13_plus"]["delta_vs_current"]
        missing = cohorts["pace_figure_missing_majority"]["delta_vs_current"]
        lines.append(
            f"| {name} | {large.get('competitive_recall_at5', 0) * 100:.2f}% | "
            f"{large.get('ndcg_at5', 0) * 100:.2f}% | "
            f"{large.get('winner_top5', 0) * 100:.2f}% | "
            f"{missing.get('competitive_recall_at5', 0) * 100:.2f}% | "
            f"{missing.get('ndcg_at5', 0) * 100:.2f}% |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--results-csv", type=Path, required=True)
    parser.add_argument("--materialize-on-demand", action="store_true")
    parser.add_argument("--prefetch-workers", type=int, default=8)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--holdout-fraction", type=float, default=0.15)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/private/tmp/au_shape_interaction_audit.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("/private/tmp/au_shape_interaction_audit.md"),
    )
    args = parser.parse_args()

    materialized, placeholders = discover_logic_files(args.archive_root)
    if args.require_complete and placeholders and not args.materialize_on_demand:
        raise SystemExit(
            f"Archive incomplete: {len(materialized)} materialized, "
            f"{len(placeholders)} placeholders."
        )
    files = materialized + placeholders if args.materialize_on_demand else materialized
    files.sort(key=lambda path: (path.parent.name, parse_int(path.stem, 999)))
    historical = load_historical_results(args.results_csv)
    scored = {name: [] for name, _mode, _scale in VARIANTS}
    race_dates = []
    rejections: dict[str, int] = {}
    large_indices = set()
    missing_pf_indices = set()

    iterator = iter_aligned_races(
        files,
        historical,
        prefetch_workers=args.prefetch_workers if args.materialize_on_demand else 1,
    )
    for index, (logic_path, aligned) in enumerate(iterator, 1):
        if aligned[0] is None:
            reason = aligned[1]
            rejections[reason] = rejections.get(reason, 0) + 1
            continue
        logic, aligned_rows = aligned
        baseline = score_variant(
            logic,
            aligned_rows,
            logic_path,
            [],
            include_details=True,
        )
        aligned_index = len(race_dates)
        race_dates.append(detect_meeting_date(logic_path.parent))
        large = len(baseline) >= 13
        if large:
            large_indices.add(aligned_index)
        missing_count = sum(
            row["feature_evidence_state"].get("pace_figure_score") == "missing"
            for row in baseline
        )
        if missing_count > len(baseline) / 2:
            missing_pf_indices.add(aligned_index)
        analysis = logic.get("race_analysis") or {}
        speed_map = analysis.get("speed_map") or {}
        confidence = str(speed_map.get("pace_confidence") or "").lower()
        clear = any(token in confidence for token in ("clear", "high", "高"))

        for name, mode, scale in VARIANTS:
            if name == "revised_current":
                scored[name].append(baseline)
                continue
            candidate = []
            for row in baseline:
                missing_pf = (
                    row["feature_evidence_state"].get("pace_figure_score")
                    == "missing"
                )
                adjustment = (
                    raw_pace_adjustment(speed_map, row["horse_number"])
                    if applies(
                        mode,
                        large=large,
                        clear=clear,
                        missing_pf=missing_pf,
                    )
                    else 0.0
                )
                candidate.append(
                    recompose_row(
                        row,
                        adjustment=adjustment,
                        scale=scale,
                    )
                )
            scored[name].append(candidate)
        if index == 1 or index % 25 == 0:
            print(f"Scored {index}/{len(files)} Logic races", flush=True)

    if not race_dates:
        raise SystemExit("No aligned races available.")
    read_failures = sum(
        count
        for reason, count in rejections.items()
        if reason.startswith("logic_read_error:")
    )
    if args.require_complete and read_failures:
        raise SystemExit(
            f"Archive read failed for {read_failures} Logic files: {rejections}"
        )
    report = build_report(
        [(name, []) for name, _mode, _scale in VARIANTS],
        scored,
        race_dates,
        rejections,
        holdout_fraction=args.holdout_fraction,
    )
    baseline_large = metrics_for_scored_races(
        select_indices(scored["revised_current"], large_indices)
    )
    baseline_missing = metrics_for_scored_races(
        select_indices(scored["revised_current"], missing_pf_indices)
    )
    report["target_cohorts"] = {}
    for name, _mode, _scale in VARIANTS:
        large_metrics = metrics_for_scored_races(
            select_indices(scored[name], large_indices)
        )
        missing_metrics = metrics_for_scored_races(
            select_indices(scored[name], missing_pf_indices)
        )
        report["target_cohorts"][name] = {
            "large_field_13_plus": {
                "races": len(large_indices),
                "metrics": large_metrics,
                "delta_vs_current": metric_delta(
                    large_metrics,
                    baseline_large,
                ),
            },
            "pace_figure_missing_majority": {
                "races": len(missing_pf_indices),
                "metrics": missing_metrics,
                "delta_vs_current": metric_delta(
                    missing_metrics,
                    baseline_missing,
                ),
            },
        }
    report["design"]["interaction_source"] = (
        "Racenet recent settled/400m shape -> pre-race speed_map role × "
        "expected pace; barrier already enters pace_map_score separately."
    )
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_with_cohorts(report))
    print(f"Aligned races: {len(race_dates)}")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
