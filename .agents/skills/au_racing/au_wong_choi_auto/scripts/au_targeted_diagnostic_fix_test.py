#!/usr/bin/env python3
"""
AU Wong Choi Targeted Diagnostic Fix Test
==========================================
Based on deep diagnostics findings:
  - race_shape overestimated in 80.6% of zero-hit races
  - track is most underestimated dimension (19.4%)
  - class_weight has negative winner lift at 3% weight
  - Heavy track zero-hit rate is 1.8× Good/Firm
  - Ablation best: class_weight_heavy_rating (Gold +0.6%, 0-hit -1)

Tests formula-level changes (how features map to matrices) rather than
matrix weight changes, following the ablation framework.

Usage:
    python3 au_targeted_diagnostic_fix_test.py
"""
from __future__ import annotations

import sys
import json
from pathlib import Path
from collections import defaultdict
from copy import deepcopy

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path = [p for p in sys.path if p]
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from au_sip_tester import (
    evaluate_races,
    report_summary,
    delta_report,
    new_bucket,
)
from au_market_free_ablation import (
    FORMULA_PRESETS,
    weighted_feature_score,
    clip_score,
)
from re_score_archive import build_field_summary

import matrix_mapper
import scoring

OUTPUT_MD = SCRIPT_DIR.parents[4] / "2026-05-31 AU Targeted Diagnostic Fix Test.md"
PROJECT_ROOT = SCRIPT_DIR.parents[4]

MATRIX_KEYS = (
    "stability", "sectional", "race_shape", "jockey_trainer",
    "class_weight", "track", "form_line",
)


def load_races():
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(
            meeting_dir.glob("Race_*_Logic.json"),
            key=lambda p: parse_int(p.stem.split("_")[1], 999),
        )
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
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(
                logic_path.stem.split("_")[1]
            )
            rows_for_race = choose_track_rows(
                historical_results.get((meeting_date, race_no), []), meeting_track
            )
            if not rows_for_race:
                continue
            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            horses = []
            for horse_num, horse in (logic.get("horses") or {}).items():
                python_auto = horse.get("python_auto") or {}
                matrix_scores = python_auto.get("matrix_scores") or {}
                feature_scores = python_auto.get("feature_scores") or {}
                if not matrix_scores or not feature_scores:
                    continue
                result_row = race_lookup.get(
                    normalize_horse_name(horse.get("horse_name"))
                )
                if not result_row:
                    continue
                horses.append({
                    "horse_number": parse_int(horse_num) or 999,
                    "horse_name": horse.get("horse_name", ""),
                    "rank_score": float(
                        python_auto.get("rank_score")
                        or python_auto.get("ability_score")
                        or 0.0
                    ),
                    "ability_score": float(python_auto.get("ability_score") or 0.0),
                    "place_tightening_bonus": float(
                        python_auto.get("place_tightening_bonus") or 0.0
                    ),
                    "actual_pos": int(result_row["pos"]),
                    "condition_bucket": _condition_bucket(result_row.get("condition") or ""),
                    "risk_flags": python_auto.get("risk_flags", []),
                    "matrix_scores": {
                        key: float(matrix_scores.get(key) or 60.0)
                        for key in MATRIX_KEYS
                    },
                    "feature_scores": feature_scores,
                    "barrier": parse_int(horse.get("barrier")),
                    "going": str(race_analysis.get("going", "") or ""),
                    "meeting_track": meeting_track,
                    "race_class": str(race_analysis.get("race_class") or ""),
                })
            if len(horses) < 4:
                continue
            races.append({
                "meeting": meeting_dir.name,
                "race_no": race_no,
                "meeting_track": meeting_track,
                "condition_bucket": horses[0]["condition_bucket"],
                "going": str(race_analysis.get("going", "") or ""),
                "race_class": str(race_analysis.get("race_class") or ""),
                "field_count": len(horses),
                "horses": horses,
            })
    return races


def _condition_bucket(condition: str) -> str:
    c = str(condition).lower()
    if "heavy" in c:
        return "Heavy"
    if "soft" in c:
        return "Soft"
    return "Good/Firm"


def apply_formula_and_score(races, formula_overrides, matrix_weight_overrides=None, place_mode=1.0, heavy_dampening=False):
    """Re-score all races using custom formulas and optional weight overrides."""
    scored_races = []
    for race in races:
        horses = []
        for h in race["horses"]:
            feature_scores = h["feature_scores"]
            # Apply formula overrides to compute new matrix scores
            new_matrix = {}
            for key in MATRIX_KEYS:
                if key in formula_overrides:
                    new_matrix[key] = weighted_feature_score(
                        feature_scores, formula_overrides[key]
                    )
                else:
                    new_matrix[key] = h["matrix_scores"][key]

            # Compute new ability_score using matrix weights
            if matrix_weight_overrides:
                weights = matrix_weight_overrides
            else:
                weights = dict(scoring.MATRIX_WEIGHTS)

            ability = round(
                sum(new_matrix[key] * weights[key] for key in weights), 2
            )

            # Balanced horse bonus
            if min(new_matrix.values()) >= 56:
                ability += 2.0

            # Place tightening (scaled by place_mode)
            place_bonus = h["place_tightening_bonus"] * place_mode

            # Heavy track dampening
            if heavy_dampening and h["condition_bucket"] == "Heavy":
                # Penalize high stability on heavy (it's overestimated)
                stab = new_matrix.get("stability", 60)
                if stab >= 72:
                    ability -= (stab - 72) * 0.15
                # Boost track on heavy (it's underestimated)
                trk = new_matrix.get("track", 60)
                if trk >= 66:
                    ability += (trk - 60) * 0.10

            rank = ability + place_bonus

            horses.append({
                **h,
                "matrix_scores_new": new_matrix,
                "ability_score_new": ability,
                "rank_score_new": rank,
            })

        # Re-rank within race
        ranked = sorted(horses, key=lambda x: -x["rank_score_new"])
        for i, h in enumerate(ranked):
            h["new_rank"] = i + 1

        scored_races.append({
            **race,
            "horses": horses,
        })
    return scored_races


def evaluate_scored_races(races):
    """Evaluate scored races using the new rank_score_new."""
    overall = new_bucket()
    by_condition = defaultdict(new_bucket)
    by_class = defaultdict(new_bucket)
    by_field = defaultdict(new_bucket)

    for race in races:
        horses = race["horses"]
        ranked = sorted(horses, key=lambda x: -x["rank_score_new"])
        top3 = ranked[:3]
        top2 = ranked[:2]
        hits_top3 = sum(1 for h in top3 if h["actual_pos"] <= 3)
        hits_top2 = sum(1 for h in top2 if h["actual_pos"] <= 3)

        cond = race["condition_bucket"]
        cls = _race_class_bucket(race.get("race_class", ""))
        fld = _field_size_bucket(race["field_count"])

        for bucket in (overall, by_condition[cond], by_class[cls], by_field[fld]):
            bucket["races"] += 1
            bucket["top3_places"] += hits_top3
            bucket["top3_slots"] += 3
            bucket["hit_distribution"][hits_top3] += 1
            if ranked[0]["actual_pos"] == 1:
                bucket["champion"] += 1
            if any(h["actual_pos"] == 1 for h in top3):
                bucket["winner_in_top3"] += 1
            if hits_top3 == 3:
                bucket["gold"] += 1
            if hits_top2 == 2:
                bucket["good"] += 1
            if hits_top3 >= 2:
                bucket["minimum"] += 1

    return overall, by_condition, by_class, by_field


def _race_class_bucket(cls: str) -> str:
    c = str(cls).lower()
    if "group 1" in c or "g1" in c:
        return "Group 1"
    if "group 2" in c or "group 3" in c or "g2" in c or "g3" in c:
        return "Group 2/3"
    if "listed" in c:
        return "Listed"
    if "maiden" in c or "mdn" in c:
        return "Maiden"
    if "bm" in c:
        m = __import__("re").search(r"bm(\d+)", c)
        if m:
            n = int(m.group(1))
            if n >= 88:
                return "BM88+"
            if n >= 72:
                return "BM72-84"
        return "BM58-70"
    return "Other"


def _field_size_bucket(n: int) -> str:
    if n <= 8:
        return "Field <=8"
    if n <= 12:
        return "Field 9-12"
    return "Field 13+"


def summary_block(label, s, delta=None):
    lines = [
        f"## {label}",
        "",
        f"- Races: `{s['races']}`",
        f"- Champion: `{s['champion']}`",
        f"- Gold: `{s['gold']}`",
        f"- Good: `{s['good']}`",
        f"- Pass: `{s['pass']}`",
        f"- Top3 Place: `{s['top3_place']}`",
        f"- 0-hit: `{s['0hit']}`",
        f"- 1-hit: `{s['1hit']}`",
        f"- 2-hit: `{s['2hit']}`",
        f"- 3-hit: `{s['3hit']}`",
    ]
    if delta:
        lines.append(
            f"- Delta: Gold `{delta['gold_delta']:+.1f}pp`, Good `{delta['good_delta']:+.1f}pp`, "
            f"Pass `{delta['pass_delta']:+.1f}pp`, Place `{delta['place_delta']:+.1f}pp`, "
            f"0-hit `{delta['0hit_delta']:+d}`"
        )
    lines.append("")
    return lines


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    args = parser.parse_args()

    print("📦 Loading archive races...")
    races = load_races()
    print(f"   Loaded {len(races)} races")

    # Baseline: use stored rank_score
    print("\n📊 BASELINE (stored rank_score):")
    bl_races = []
    for race in races:
        horses = []
        for h in race["horses"]:
            horses.append({**h, "rank_score_new": h["rank_score"]})
        bl_races.append({**race, "horses": horses})
    bl_overall, bl_cond, bl_class, bl_field = evaluate_scored_races(bl_races)
    bl_summary = report_summary(bl_overall, "Baseline")
    print(f"  Gold: {bl_summary['gold']}  |  Good: {bl_summary['good']}  |  Pass: {bl_summary['pass']}  |  Place: {bl_summary['top3_place']}  |  0H: {bl_summary['0hit']}")

    # Define targeted variants
    variants = [
        (
            "T1: class_weight_heavy_rating (ablation best)",
            # From ablation: class_weight = 60% rating, 20% class, 20% weight
            {"class_weight": (("class_score", 0.20), ("rating_score", 0.60), ("weight_score", 0.20))},
            None, 1.0, False,
        ),
        (
            "T2: race_shape_light_track (ablation safe)",
            # race_shape = 90% pace + 10% track (reduces pure draw bias)
            {"race_shape": (("pace_map_score", 0.90), ("track_score", 0.10))},
            None, 1.0, False,
        ),
        (
            "T3: class_weight_heavy_rating + race_shape_light_track",
            {
                "class_weight": (("class_score", 0.20), ("rating_score", 0.60), ("weight_score", 0.20)),
                "race_shape": (("pace_map_score", 0.90), ("track_score", 0.10)),
            },
            None, 1.0, False,
        ),
        (
            "T4: T3 + jt_fit_tempered",
            {
                "class_weight": (("class_score", 0.20), ("rating_score", 0.60), ("weight_score", 0.20)),
                "race_shape": (("pace_map_score", 0.90), ("track_score", 0.10)),
                "jockey_trainer": (("jockey_score", 0.35), ("trainer_score", 0.25), ("jockey_horse_fit_score", 0.40)),
            },
            None, 1.0, False,
        ),
        (
            "T5: T4 + formline_purer",
            {
                "class_weight": (("class_score", 0.20), ("rating_score", 0.60), ("weight_score", 0.20)),
                "race_shape": (("pace_map_score", 0.90), ("track_score", 0.10)),
                "jockey_trainer": (("jockey_score", 0.35), ("trainer_score", 0.25), ("jockey_horse_fit_score", 0.40)),
                "form_line": (("formline_score", 0.82), ("form_score", 0.18)),
            },
            None, 1.0, False,
        ),
        (
            "T6: T5 + heavy dampening",
            {
                "class_weight": (("class_score", 0.20), ("rating_score", 0.60), ("weight_score", 0.20)),
                "race_shape": (("pace_map_score", 0.90), ("track_score", 0.10)),
                "jockey_trainer": (("jockey_score", 0.35), ("trainer_score", 0.25), ("jockey_horse_fit_score", 0.40)),
                "form_line": (("formline_score", 0.82), ("form_score", 0.18)),
            },
            None, 1.0, True,  # heavy_dampening=True
        ),
        (
            "T7: T5 + place_off (no place tightening)",
            {
                "class_weight": (("class_score", 0.20), ("rating_score", 0.60), ("weight_score", 0.20)),
                "race_shape": (("pace_map_score", 0.90), ("track_score", 0.10)),
                "jockey_trainer": (("jockey_score", 0.35), ("trainer_score", 0.25), ("jockey_horse_fit_score", 0.40)),
                "form_line": (("formline_score", 0.82), ("form_score", 0.18)),
            },
            None, 0.0, False,  # place_mode=0.0
        ),
        (
            "T8: sectional_speed_heavy + T6",
            {
                "class_weight": (("class_score", 0.20), ("rating_score", 0.60), ("weight_score", 0.20)),
                "race_shape": (("pace_map_score", 0.90), ("track_score", 0.10)),
                "jockey_trainer": (("jockey_score", 0.35), ("trainer_score", 0.25), ("jockey_horse_fit_score", 0.40)),
                "form_line": (("formline_score", 0.82), ("form_score", 0.18)),
                "sectional": (("sectional_score", 0.75), ("distance_score", 0.15), ("trial_score", 0.10)),
            },
            None, 1.0, True,
        ),
    ]

    results_md = [
        "# AU Wong Choi Targeted Diagnostic Fix Test",
        "",
        "Based on deep diagnostics: race_shape overestimated in 80% zero-hit races,",
        "track most underestimated, class_weight negative lift at 3%, Heavy 1.8× zero-hit.",
        "",
        f"Archive: `{len(races)}` races",
        "",
    ]

    for name, formula_overrides, weight_overrides, place_mode, heavy_damp in variants:
        print(f"\n🧪 {name}...")
        scored = apply_formula_and_score(
            races, formula_overrides, weight_overrides, place_mode, heavy_damp
        )
        overall, cond, cls, fld = evaluate_scored_races(scored)
        summary = report_summary(overall, name)
        delta = delta_report(bl_overall, overall)

        print(f"  Gold: {summary['gold']}  |  Good: {summary['good']}  |  Pass: {summary['pass']}  |  Place: {summary['top3_place']}  |  0H: {summary['0hit']}")
        print(f"  ΔGold: {delta['gold_delta']:+.1f}pp  |  ΔPass: {delta['pass_delta']:+.1f}pp  |  ΔPlace: {delta['place_delta']:+.1f}pp  |  Δ0H: {delta['0hit_delta']:+d}")

        verdict = "✅" if delta["pass_delta"] >= 0 and delta["0hit_delta"] <= 0 else "❌"
        if delta["gold_delta"] > 0 and delta["0hit_delta"] <= 0:
            verdict = "✅✅"
        print(f"  {verdict}")

        results_md.extend(summary_block(name, summary, delta))

        # Condition breakdown for heavy-dampening variants
        if heavy_damp:
            results_md.append("### Condition Breakdown")
            results_md.append("")
            for c in ("Good/Firm", "Soft", "Heavy"):
                b = cond.get(c, new_bucket())
                if b["races"] == 0:
                    continue
                s = report_summary(b, c)
                bl_b = bl_cond.get(c, new_bucket())
                bl_s = report_summary(bl_b, f"BL {c}")
                d = delta_report(bl_b, b)
                results_md.append(f"| {c} | {b['races']} | {s['gold']} | {s['good']} | {s['pass']} | {s['top3_place']} | {b['hit_distribution'][0]} | {d['gold_delta']:+.1f} | {d['pass_delta']:+.1f} | {d['0hit_delta']:+d} |")
            results_md.append("")

    output_path = Path(args.output_md)
    output_path.write_text("\n".join(results_md), encoding="utf-8")
    print(f"\n📄 Report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
