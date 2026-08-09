#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # type: ignore
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from au_pace_profile_shadow_test import (  # type: ignore
    DEFAULT_TARGET_MEETINGS,
    _condition_bucket,
    _field_size_bucket,
    _race_class_bucket,
    _results_lookup,
    load_archive_meetings,
    load_target_meetings,
)
from au_sip_tester import delta_report, evaluate_races, report_summary  # type: ignore
from re_score_archive import build_field_summary  # type: ignore

import engine_core  # type: ignore
import matrix_mapper  # type: ignore
import scoring  # type: ignore
from engine_core import RacingEngine  # type: ignore


OUTPUT_MD = PROJECT_ROOT / "2026-05-31 AU Noise Fix Shadow Test.md"


def _fixed_dynamic_matrix_weights(race_context):
    weights = dict(scoring.MATRIX_WEIGHTS)
    field_summary = race_context.get("field_summary", {})
    field_count = int(field_summary.get("count", 0))
    going = str(race_context.get("going", "") or "").lower()
    race_class = str(race_context.get("race_class", "") or "").lower()

    if field_count >= 13:
        weights["race_shape"] -= 0.02
        weights["sectional"] -= 0.01
        weights["stability"] += 0.02
        weights["form_line"] += 0.01
    elif field_count >= 9:
        weights["race_shape"] -= 0.01
        weights["sectional"] -= 0.005
        weights["stability"] += 0.01
        weights["form_line"] += 0.005
    elif 0 < field_count <= 8:
        weights["race_shape"] += 0.04
        weights["sectional"] += 0.03
        weights["stability"] -= 0.02
        weights["form_line"] -= 0.02

    if "soft" in going or "heavy" in going:
        weights["race_shape"] -= 0.005
        weights["track"] += 0.01
        weights["stability"] -= 0.005
    elif "good" in going or "firm" in going:
        weights["sectional"] += 0.02
        weights["track"] -= 0.02

    if "bm" in race_class:
        bm_tokens = tuple(f"bm{n}" for n in range(50, 100))
        if any(t in race_class for t in ("bm58", "bm64", "bm68", "bm70")):
            weights["stability"] += 0.03
            weights["jockey_trainer"] += 0.02
            weights["class_weight"] -= 0.02
        elif any(t in race_class for t in bm_tokens):
            weights["class_weight"] += 0.005

    total = sum(weights.values())
    if total > 0:
        for key in weights:
            weights[key] = weights[key] / total

    for key, floor_val in scoring._WEIGHT_FLOOR.items():
        if weights[key] < floor_val:
            weights[key] = floor_val
    for key, ceil_val in scoring._WEIGHT_CEILING.items():
        if weights[key] > ceil_val:
            weights[key] = ceil_val
    for key in weights:
        weights[key] = round(weights[key], 4)
    return weights


@contextmanager
def patched_runtime(variant: str):
    saved_place = dict(scoring.PLACE_TIGHTENING_FEATURE_WEIGHTS)
    saved_formulas = deepcopy(matrix_mapper.MATRIX_FORMULAS)
    saved_class = dict(scoring.CLASS_MICRO_WEIGHTS)
    saved_track = dict(scoring.TRACK_MICRO_WEIGHTS)
    saved_fit = dict(scoring.FIT_MICRO_WEIGHTS)
    saved_engine_weights = engine_core.get_dynamic_matrix_weights
    saved_scoring_weights = scoring.get_dynamic_matrix_weights
    try:
        scoring.get_dynamic_matrix_weights = _fixed_dynamic_matrix_weights
        engine_core.get_dynamic_matrix_weights = _fixed_dynamic_matrix_weights

        if variant in {"confidence_demoted", "bundle_all"}:
            scoring.PLACE_TIGHTENING_FEATURE_WEIGHTS["confidence_score"] = 0.0

        if variant in {"health_removed", "bundle_all"}:
            matrix_mapper.MATRIX_FORMULAS["track"] = (("track_score", 1.0),)

        if variant in {"sign_anomalies_fixed", "bundle_all"}:
            scoring.CLASS_MICRO_WEIGHTS["class_up_pen"] = -4.0
            scoring.TRACK_MICRO_WEIGHTS["heavy_place_bonus"] = abs(scoring.TRACK_MICRO_WEIGHTS["heavy_place_bonus"])
            scoring.FIT_MICRO_WEIGHTS["best_formal_mult"] = abs(scoring.FIT_MICRO_WEIGHTS["best_formal_mult"])

        yield
    finally:
        scoring.PLACE_TIGHTENING_FEATURE_WEIGHTS.clear()
        scoring.PLACE_TIGHTENING_FEATURE_WEIGHTS.update(saved_place)
        matrix_mapper.MATRIX_FORMULAS.clear()
        matrix_mapper.MATRIX_FORMULAS.update(saved_formulas)
        scoring.CLASS_MICRO_WEIGHTS.clear()
        scoring.CLASS_MICRO_WEIGHTS.update(saved_class)
        scoring.TRACK_MICRO_WEIGHTS.clear()
        scoring.TRACK_MICRO_WEIGHTS.update(saved_track)
        scoring.FIT_MICRO_WEIGHTS.clear()
        scoring.FIT_MICRO_WEIGHTS.update(saved_fit)
        scoring.get_dynamic_matrix_weights = saved_scoring_weights
        engine_core.get_dynamic_matrix_weights = saved_engine_weights


def _target_runtime_races(meeting_dirs: list[Path]) -> list[dict]:
    races = []
    for meeting_dir in meeting_dirs:
        results_candidates = sorted(meeting_dir.glob("Race_Results_*.json"))
        if not results_candidates:
            continue
        results_by_race = _results_lookup(results_candidates[0])
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999)):
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis") or {}
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            actual_positions = results_by_race.get(race_no) or {}
            if not actual_positions:
                continue
            race_context = dict(race_analysis)
            race_context["field_summary"] = build_field_summary(logic.get("horses", {}))
            horses = []
            for horse_num, horse in (logic.get("horses") or {}).items():
                horse_number = parse_int(horse_num) or parse_int(horse.get("number")) or 999
                actual_pos = actual_positions.get(horse_number)
                if actual_pos is None:
                    continue
                engine = RacingEngine(
                    horse,
                    race_context,
                    horse.get("_data", {}).get("facts_section", ""),
                    facts_path=str(meeting_dir / f"{meeting_dir.name}_runtime.md"),
                )
                auto = engine.analyze_horse()
                horses.append(
                    {
                        "horse_number": horse_number,
                        "horse_name": str(horse.get("horse_name") or "").strip(),
                        "rank_score": float(auto.get("rank_score") or auto.get("ability_score") or 0.0),
                        "ability_score": float(auto.get("ability_score") or 0.0),
                        "actual_pos": int(actual_pos),
                        "condition_bucket": _condition_bucket(race_analysis.get("going", "")),
                        "risk_flags": list(auto.get("risk_flags") or []),
                        "matrix": auto.get("matrix") or {},
                        "matrix_scores": auto.get("matrix_scores") or {},
                        "feature_scores": auto.get("feature_scores") or {},
                        "barrier": parse_int(horse.get("barrier")),
                        "going": race_analysis.get("going", ""),
                        "meeting_track": meeting_dir.name,
                        "meeting_track_normalized": normalize_horse_name(meeting_dir.name),
                        "jockey": horse.get("jockey", ""),
                        "trainer": horse.get("trainer", ""),
                        "data": horse.get("_data") if isinstance(horse.get("_data"), dict) else {},
                        "speed_map": race_analysis.get("speed_map") if isinstance(race_analysis.get("speed_map"), dict) else {},
                    }
                )
            if len(horses) < 4:
                continue
            races.append(
                {
                    "meeting": meeting_dir.name,
                    "race_no": race_no,
                    "meeting_track": meeting_dir.name,
                    "meeting_track_normalized": normalize_horse_name(meeting_dir.name),
                    "race_class_bucket": _race_class_bucket(race_analysis.get("race_class")),
                    "field_size_bucket": _field_size_bucket(len(horses)),
                    "condition_bucket": horses[0]["condition_bucket"],
                    "going": race_analysis.get("going", ""),
                    "race_class": race_analysis.get("race_class", ""),
                    "field_count": len(horses),
                    "horses": horses,
                    "speed_map": race_analysis.get("speed_map") if isinstance(race_analysis.get("speed_map"), dict) else {},
                }
            )
    return races


def _archive_runtime_races() -> list[dict]:
    races = []
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        if not meeting_date or not meeting_track:
            continue
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis") or {}
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            rows_for_race = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not rows_for_race:
                continue
            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            race_context = dict(race_analysis)
            race_context["field_summary"] = build_field_summary(logic.get("horses", {}))
            horses = []
            for horse_num, horse in (logic.get("horses") or {}).items():
                result_row = race_lookup.get(normalize_horse_name(horse.get("horse_name")))
                if not result_row:
                    continue
                engine = RacingEngine(
                    horse,
                    race_context,
                    horse.get("_data", {}).get("facts_section", ""),
                    facts_path=str(meeting_dir / f"{meeting_date}_runtime.md"),
                )
                auto = engine.analyze_horse()
                horses.append(
                    {
                        "horse_number": parse_int(horse_num) or 999,
                        "horse_name": str(horse.get("horse_name") or "").strip(),
                        "rank_score": float(auto.get("rank_score") or auto.get("ability_score") or 0.0),
                        "ability_score": float(auto.get("ability_score") or 0.0),
                        "actual_pos": int(result_row["pos"]),
                        "condition_bucket": _condition_bucket(result_row.get("condition") or ""),
                        "risk_flags": list(auto.get("risk_flags") or []),
                        "matrix": auto.get("matrix") or {},
                        "matrix_scores": auto.get("matrix_scores") or {},
                        "feature_scores": auto.get("feature_scores") or {},
                        "barrier": parse_int(horse.get("barrier")),
                        "going": race_analysis.get("going", ""),
                        "meeting_track": meeting_track,
                        "meeting_track_normalized": normalize_horse_name(meeting_track),
                        "jockey": horse.get("jockey", ""),
                        "trainer": horse.get("trainer", ""),
                        "data": horse.get("_data") if isinstance(horse.get("_data"), dict) else {},
                        "speed_map": race_analysis.get("speed_map") if isinstance(race_analysis.get("speed_map"), dict) else {},
                    }
                )
            if len(horses) < 4:
                continue
            races.append(
                {
                    "meeting": meeting_dir.name,
                    "race_no": race_no,
                    "meeting_track": meeting_track,
                    "meeting_track_normalized": normalize_horse_name(meeting_track),
                    "race_class_bucket": _race_class_bucket(race_analysis.get("race_class")),
                    "field_size_bucket": _field_size_bucket(len(horses)),
                    "condition_bucket": horses[0]["condition_bucket"],
                    "going": race_analysis.get("going", ""),
                    "race_class": race_analysis.get("race_class", ""),
                    "field_count": len(horses),
                    "horses": horses,
                    "speed_map": race_analysis.get("speed_map") if isinstance(race_analysis.get("speed_map"), dict) else {},
                }
            )
    return races


def _summary_block(label: str, summary: dict, delta: dict | None = None) -> list[str]:
    lines = [
        f"## {label}",
        "",
        f"- Races: `{summary['races']}`",
        f"- Champion: `{summary['champion']}`",
        f"- Gold: `{summary['gold']}`",
        f"- Good: `{summary['good']}`",
        f"- Pass: `{summary['pass']}`",
        f"- Top3 Place: `{summary['top3_place']}`",
        f"- 0-hit: `{summary['0hit']}`",
        f"- 1-hit: `{summary['1hit']}`",
    ]
    if delta:
        lines.append(
            f"- Delta: gold `{delta['gold_delta']:+.1f}`, good `{delta['good_delta']:+.1f}`, "
            f"pass `{delta['pass_delta']:+.1f}`, place `{delta['place_delta']:+.1f}`, "
            f"0-hit `{delta['0hit_delta']:+d}`, 1-hit `{delta['1hit_delta']:+d}`"
        )
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="AU noise-fix shadow test")
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    args = parser.parse_args()

    archive_stored = load_archive_meetings()
    target_stored = load_target_meetings(DEFAULT_TARGET_MEETINGS)

    baseline_archive, _, _, _ = evaluate_races(archive_stored, "archive-stored")
    baseline_target, _, _, _ = evaluate_races(target_stored, "target-stored")
    baseline_archive_summary = report_summary(baseline_archive, "archive baseline")
    baseline_target_summary = report_summary(baseline_target, "target baseline")

    variant_results = {}
    for variant in ("runtime_fixed_good_only", "confidence_demoted", "health_removed", "sign_anomalies_fixed", "bundle_all"):
        patch_name = "runtime_fixed_good_only" if variant == "runtime_fixed_good_only" else variant
        actual_patch = "runtime_fixed_good_only" if variant == "runtime_fixed_good_only" else variant
        with patched_runtime(actual_patch):
            archive_runtime = _archive_runtime_races()
            target_runtime = _target_runtime_races(DEFAULT_TARGET_MEETINGS)
        archive_overall, _, _, _ = evaluate_races(archive_runtime, f"{patch_name}-archive")
        target_overall, _, _, _ = evaluate_races(target_runtime, f"{patch_name}-target")
        archive_summary = report_summary(archive_overall, patch_name)
        target_summary = report_summary(target_overall, patch_name)
        variant_results[variant] = {
            "archive": archive_summary,
            "target": target_summary,
            "archive_delta": delta_report(baseline_archive, archive_overall),
            "target_delta": delta_report(baseline_target, target_overall),
        }

    lines = [
        "# AU Noise / Logic-Fix Shadow Test",
        "",
        "Baseline uses stored live `python_auto` scores already saved in logic files.",
        "Candidate variants rerun the current engine with targeted patches.",
        "",
        *_summary_block("Stored Archive Baseline", baseline_archive_summary),
        *_summary_block("Stored 05-30 Baseline", baseline_target_summary),
    ]

    for variant, payload in variant_results.items():
        lines.extend(_summary_block(f"{variant} / archive", payload["archive"], payload["archive_delta"]))
        lines.extend(_summary_block(f"{variant} / 05-30", payload["target"], payload["target_delta"]))

    output_path = Path(args.output_md)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
