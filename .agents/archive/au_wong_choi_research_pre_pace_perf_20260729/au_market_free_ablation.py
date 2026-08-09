#!/usr/bin/env python3
from __future__ import annotations

import itertools
import json
import math
import sys
from copy import deepcopy
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_sip_tester import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    condition_bucket,
    delta_report,
    detect_meeting_date,
    detect_meeting_track,
    evaluate_races,
    field_size_bucket,
    load_historical_results,
    normalize_horse_name,
    parse_int,
    race_class_bucket,
    report_summary,
)
from scoring import get_dynamic_matrix_weights, parse_float  # noqa: E402


OUTPUT_MD = ARCHIVE_ROOT / "AU_Auto_Market_Free_Ablation.md"
OUTPUT_CSV = ARCHIVE_ROOT / "AU_Auto_Market_Free_Ablation.csv"

MATRIX_KEYS = (
    "stability",
    "sectional",
    "race_shape",
    "jockey_trainer",
    "class_weight",
    "track",
    "form_line",
)


FORMULA_PRESETS = {
    "baseline_formula": {},
    "race_shape_pure_pace": {
        "race_shape": (("pace_map_score", 1.0),),
    },
    "race_shape_light_track": {
        "race_shape": (("pace_map_score", 0.90), ("track_score", 0.10)),
    },
    "sectional_speed_heavy": {
        "sectional": (("sectional_score", 0.75), ("distance_score", 0.15), ("trial_score", 0.10)),
    },
    "jt_fit_tempered": {
        "jockey_trainer": (
            ("jockey_score", 0.35),
            ("trainer_score", 0.25),
            ("jockey_horse_fit_score", 0.40),
        ),
    },
    "class_weight_80_20": {
        "class_weight": (("class_score", 0.80), ("weight_score", 0.20)),
    },
    "class_weight_class_only": {
        "class_weight": (("class_score", 1.0),),
    },
    "class_weight_no_rating": {
        "class_weight": (("class_score", 0.53), ("weight_score", 0.47)),
    },
    "class_weight_heavy_rating": {
        "class_weight": (("class_score", 0.20), ("rating_score", 0.60), ("weight_score", 0.20)),
    },
    "track_pure": {
        "track": (("track_score", 1.0),),
    },
    "formline_purer": {
        "form_line": (("formline_score", 0.82), ("form_score", 0.18)),
    },
}

PLACE_MODES = {
    "place_live": 1.0,
    "place_half": 0.5,
    "place_off": 0.0,
}


def clip_score(value, default=60.0):
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(100.0, score))


def weighted_feature_score(features: dict, formula: tuple[tuple[str, float], ...]) -> float:
    return round(sum(clip_score(features.get(key, 60.0)) * weight for key, weight in formula), 4)


def load_all_races():
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
            race_analysis = logic.get("race_analysis", {})
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            rows_for_race = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not rows_for_race:
                continue
            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            horses = []
            for horse_num, horse in logic.get("horses", {}).items():
                python_auto = horse.get("python_auto") or {}
                matrix_scores = python_auto.get("matrix_scores") or {}
                feature_scores = python_auto.get("feature_scores") or {}
                if not matrix_scores or not feature_scores:
                    continue
                result_row = race_lookup.get(normalize_horse_name(horse.get("horse_name")))
                if not result_row:
                    continue
                horses.append(
                    {
                        "horse_number": parse_int(horse_num) or 999,
                        "horse_name": horse.get("horse_name", ""),
                        "rank_score": float(python_auto.get("rank_score") or python_auto.get("ability_score") or 0.0),
                        "ability_score": float(python_auto.get("ability_score") or 0.0),
                        "place_tightening_bonus": float(python_auto.get("place_tightening_bonus") or 0.0),
                        "actual_pos": int(result_row["pos"]),
                        "condition_bucket": condition_bucket(result_row.get("condition")),
                        "risk_flags": python_auto.get("risk_flags", []),
                        "matrix_scores": {key: float(matrix_scores.get(key) or 60.0) for key in MATRIX_KEYS},
                        "feature_scores": feature_scores,
                        "barrier": parse_int(horse.get("barrier")),
                        "going": str(race_analysis.get("going", "") or ""),
                        "meeting_track": meeting_track,
                    }
                )
            if len(horses) < 4:
                continue
            races.append(
                {
                    "meeting": meeting_dir.name,
                    "race_no": race_no,
                    "meeting_track": meeting_track,
                    "race_class_bucket": race_class_bucket(race_analysis.get("race_class")),
                    "race_class": str(race_analysis.get("race_class") or ""),
                    "field_size_bucket": field_size_bucket(len(horses)),
                    "condition_bucket": horses[0]["condition_bucket"],
                    "going": str(race_analysis.get("going", "") or ""),
                    "field_count": len(horses),
                    "horses": horses,
                }
            )
    return races


def dynamic_weighted_score(matrix_scores: dict, race: dict) -> float:
    weights = get_dynamic_matrix_weights(
        {
            "field_summary": {"count": race.get("field_count", 0)},
            "going": race.get("going", ""),
            "race_class": race.get("race_class") or race.get("race_class_bucket", ""),
        }
    )
    return sum(float(matrix_scores.get(key, 60.0)) * weights[key] for key in weights)


def apply_variant(horses: list[dict], race: dict, formula_names: tuple[str, ...], place_mode: str):
    place_scale = PLACE_MODES[place_mode]
    override_formulas = {}
    for name in formula_names:
        override_formulas.update(FORMULA_PRESETS[name])

    for horse in horses:
        base_matrix = horse["matrix_scores"]
        candidate_matrix = dict(base_matrix)
        for section, formula in override_formulas.items():
            candidate_matrix[section] = weighted_feature_score(horse["feature_scores"], formula)

        base_weighted = dynamic_weighted_score(base_matrix, race)
        candidate_weighted = dynamic_weighted_score(candidate_matrix, race)
        matrix_delta = candidate_weighted - base_weighted

        place_bonus = horse.get("place_tightening_bonus", 0.0)
        place_delta = (place_scale - 1.0) * place_bonus
        horse["rank_score"] = horse["rank_score"] + matrix_delta + place_delta

    return horses


def evaluate_variant(races: list[dict], formula_names: tuple[str, ...], place_mode: str):
    def adjust(horses, race):
        return apply_variant(horses, race, formula_names, place_mode)

    return evaluate_races(races, "variant", adjust)


def metric_score(bucket: dict) -> tuple:
    races = bucket["races"] or 1
    pass_rate = bucket["minimum"] / races
    good_rate = bucket["good"] / races
    gold_rate = bucket["gold"] / races
    place_rate = bucket["top3_places"] / (bucket["top3_slots"] or 1)
    zero_hit_rate = bucket["hit_distribution"][0] / races
    return (pass_rate, good_rate, gold_rate, place_rate, -zero_hit_rate)


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main():
    races = load_all_races()
    baseline, _, _, _ = evaluate_races(races, "baseline")
    baseline_summary = report_summary(baseline, "baseline")

    formula_sets = [()]
    single_names = [name for name in FORMULA_PRESETS if name != "baseline_formula"]
    formula_sets.extend((name,) for name in single_names)
    for combo_size in (2, 3):
        formula_sets.extend(itertools.combinations(single_names, combo_size))

    rows = []
    for formula_names in formula_sets:
        for place_mode in PLACE_MODES:
            if not formula_names and place_mode == "place_live":
                continue
            overall, by_condition, by_class, by_field = evaluate_variant(races, formula_names, place_mode)
            summary = report_summary(overall, f"{'+'.join(formula_names) or 'baseline_formula'} | {place_mode}")
            delta = delta_report(baseline, overall)
            rows.append(
                {
                    "formula": "+".join(formula_names) or "baseline_formula",
                    "place_mode": place_mode,
                    "overall": overall,
                    "summary": summary,
                    "delta": delta,
                    "condition": by_condition,
                    "race_class": by_class,
                    "field": by_field,
                }
            )

    rows.sort(key=lambda row: (metric_score(row["overall"]), -len(row["formula"])), reverse=True)
    best = rows[:30]

    csv_lines = [
        "rank,formula,place_mode,gold,good,pass,top3_place,top3_win,0hit,1hit,2hit,3hit,gold_delta,good_delta,pass_delta,place_delta,zero_hit_delta,one_hit_delta"
    ]
    for idx, row in enumerate(rows, 1):
        s = row["summary"]
        d = row["delta"]
        csv_lines.append(
            ",".join(
                [
                    str(idx),
                    row["formula"],
                    row["place_mode"],
                    s["gold"],
                    s["good"],
                    s["pass"],
                    s["top3_place"],
                    s["top3_win"],
                    str(s["0hit"]),
                    str(s["1hit"]),
                    str(s["2hit"]),
                    str(s["3hit"]),
                    f"{d['gold_delta']:+.1f}",
                    f"{d['good_delta']:+.1f}",
                    f"{d['pass_delta']:+.1f}",
                    f"{d['place_delta']:+.1f}",
                    f"{d['0hit_delta']:+d}",
                    f"{d['1hit_delta']:+d}",
                ]
            )
        )
    OUTPUT_CSV.write_text("\n".join(csv_lines), encoding="utf-8")

    md = [
        "# AU Auto Market-Free Ablation",
        "",
        "- This test uses archive results for validation only.",
        "- No market odds, SP, favourite rank, market move, or price field is used in candidate scoring.",
        "",
        "## Baseline",
        "",
        f"- Races: **{baseline_summary['races']}**",
        f"- Gold: **{baseline_summary['gold']}**",
        f"- Good: **{baseline_summary['good']}**",
        f"- Pass: **{baseline_summary['pass']}**",
        f"- Top3 Place Precision: **{baseline_summary['top3_place']}**",
        f"- 0-hit / 1-hit / 2-hit / 3-hit: **{baseline_summary['0hit']} / {baseline_summary['1hit']} / {baseline_summary['2hit']} / {baseline_summary['3hit']}**",
        "",
        "## Top Candidates",
        "",
        "| Rank | Candidate | Gold | Good | Pass | Place | Top3 Win | 0H | 1H | 2H | 3H | Delta |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(best, 1):
        s = row["summary"]
        d = row["delta"]
        md.append(
            "| {idx} | {formula} / {place} | {gold} | {good} | {pass_} | {place_prec} | {top3_win} | {z} | {o} | {tw} | {th} | "
            "G {gd:+.1f} / Good {goodd:+.1f} / Pass {pd:+.1f} / Place {pld:+.1f} / 0H {zh:+d} |".format(
                idx=idx,
                formula=row["formula"],
                place=row["place_mode"],
                gold=s["gold"],
                good=s["good"],
                pass_=s["pass"],
                place_prec=s["top3_place"],
                top3_win=s["top3_win"],
                z=s["0hit"],
                o=s["1hit"],
                tw=s["2hit"],
                th=s["3hit"],
                gd=d["gold_delta"],
                goodd=d["good_delta"],
                pd=d["pass_delta"],
                pld=d["place_delta"],
                zh=d["0hit_delta"],
            )
        )

    best_row = best[0] if best else None
    if best_row:
        md.extend(
            [
                "",
                "## Best Candidate Breakdown",
                "",
                f"- Candidate: **{best_row['formula']} / {best_row['place_mode']}**",
                "",
                "### Field Size",
                "",
                "| Field | Races | Gold | Good | Pass | Place | 0H | 1H | 2H | 3H |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for key in ("Field <=8", "Field 9-12", "Field 13+"):
            bucket = best_row["field"].get(key)
            if not bucket:
                continue
            s = report_summary(bucket, key)
            md.append(
                f"| {key} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |"
            )
        md.extend(
            [
                "",
                "### Race Class",
                "",
                "| Class | Races | Gold | Good | Pass | Place | 0H | 1H | 2H | 3H |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for key in ("BM58-70", "BM72-84", "BM88+", "Group 1", "Group 2/3", "Maiden", "Other"):
            bucket = best_row["race_class"].get(key)
            if not bucket:
                continue
            s = report_summary(bucket, key)
            md.append(
                f"| {key} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |"
            )
        md.extend(
            [
                "",
                "## Promotion Rule",
                "",
                "Promote only if overall Pass/Good improves without increasing 0-hit, then re-score archive with the engine and re-run calibration.",
            ]
        )

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"Loaded races: {len(races)}")
    print(
        "Baseline:",
        baseline_summary["gold"],
        baseline_summary["good"],
        baseline_summary["pass"],
        baseline_summary["top3_place"],
        "0H",
        baseline_summary["0hit"],
    )
    if best:
        s = best[0]["summary"]
        d = best[0]["delta"]
        print("Best:", best[0]["formula"], best[0]["place_mode"])
        print("  Gold/Good/Pass/Place:", s["gold"], s["good"], s["pass"], s["top3_place"])
        print("  0H/1H/2H/3H:", s["0hit"], s["1hit"], s["2hit"], s["3hit"])
        print("  Delta:", d)
    print(f"Report: {OUTPUT_MD}")
    print(f"CSV: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
