#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_pace_profile_shadow_test import load_archive_meetings  # type: ignore
from au_sip_tester import delta_report, evaluate_races, report_summary  # type: ignore
from matrix_mapper import MATRIX_FORMULAS  # type: ignore
from scoring import (  # type: ignore
    PLACE_TIGHTENING_FEATURE_WEIGHTS,
    PLACE_TIGHTENING_MAX_ABS_BONUS,
    PLACE_TIGHTENING_SCALE,
    clip_score,
    get_dynamic_matrix_weights,
)


OUTPUT_MD = PROJECT_ROOT / "2026-05-31 AU Simplification Shadow Test.md"


def _place_bonus(feature_scores: dict, confidence_on: bool = True) -> float:
    bonus = 0.0
    for key, weight in PLACE_TIGHTENING_FEATURE_WEIGHTS.items():
        if not confidence_on and key == "confidence_score":
            continue
        bonus += weight * (clip_score(feature_scores.get(key), 60.0) - 60.0)
    bonus *= PLACE_TIGHTENING_SCALE
    return max(-PLACE_TIGHTENING_MAX_ABS_BONUS, min(PLACE_TIGHTENING_MAX_ABS_BONUS, bonus))


def _weighted_formula_score(feature_scores: dict, formula: tuple[tuple[str, float], ...]) -> float:
    return round(sum(clip_score(feature_scores.get(name, 60.0)) * weight for name, weight in formula), 4)


def _apply_matrix_delta(horse: dict, race: dict, section: str, formula: tuple[tuple[str, float], ...]) -> None:
    base_matrix = horse.get("matrix_scores") or {}
    base_score = float(base_matrix.get(section, 60.0))
    new_score = _weighted_formula_score(horse.get("feature_scores") or {}, formula)
    if abs(new_score - base_score) < 1e-9:
        return
    weights = get_dynamic_matrix_weights(
        {
            "field_summary": {"count": race.get("field_count", 0)},
            "going": race.get("going", ""),
            "race_class": race.get("race_class") or race.get("race_class_bucket", ""),
        }
    )
    horse["rank_score"] += (new_score - base_score) * float(weights.get(section, 0.0))


def variant_identity(horses: list[dict], race: dict) -> list[dict]:
    return horses


def variant_confidence_off(horses: list[dict], race: dict) -> list[dict]:
    for horse in horses:
        feature_scores = horse.get("feature_scores") or {}
        old_bonus = _place_bonus(feature_scores, confidence_on=True)
        new_bonus = _place_bonus(feature_scores, confidence_on=False)
        horse["rank_score"] += new_bonus - old_bonus
        if float(feature_scores.get("confidence_score", 60.0)) <= 50.0:
            horse["rank_score"] += 0.2
    return horses


def variant_track_pure(horses: list[dict], race: dict) -> list[dict]:
    formula = (("track_score", 1.0),)
    for horse in horses:
        _apply_matrix_delta(horse, race, "track", formula)
    return horses


def variant_track_pure_confidence_off(horses: list[dict], race: dict) -> list[dict]:
    horses = variant_confidence_off(horses, race)
    horses = variant_track_pure(horses, race)
    return horses


def variant_jt_no_fit(horses: list[dict], race: dict) -> list[dict]:
    formula = (
        ("jockey_score", 0.5833333333),
        ("trainer_score", 0.4166666667),
    )
    for horse in horses:
        _apply_matrix_delta(horse, race, "jockey_trainer", formula)
    return horses


def variant_jt_no_fit_track_pure(horses: list[dict], race: dict) -> list[dict]:
    horses = variant_jt_no_fit(horses, race)
    horses = variant_track_pure(horses, race)
    return horses


def variant_jt_fit_tempered(horses: list[dict], race: dict) -> list[dict]:
    formula = (
        ("jockey_score", 0.35),
        ("trainer_score", 0.25),
        ("jockey_horse_fit_score", 0.40),
    )
    for horse in horses:
        _apply_matrix_delta(horse, race, "jockey_trainer", formula)
    return horses


VARIANTS = {
    "baseline": variant_identity,
    "confidence_off": variant_confidence_off,
    "track_pure": variant_track_pure,
    "track_pure_confidence_off": variant_track_pure_confidence_off,
    "jt_no_fit": variant_jt_no_fit,
    "jt_no_fit_track_pure": variant_jt_no_fit_track_pure,
    "jt_fit_tempered": variant_jt_fit_tempered,
}


def _summary_block(title: str, summary: dict, delta: dict | None = None) -> list[str]:
    lines = [
        f"## {title}",
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
    parser = argparse.ArgumentParser(description="AU simplification shadow test")
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    args = parser.parse_args()

    archive_races = load_archive_meetings()
    baseline_overall, _, _, _ = evaluate_races(archive_races, "baseline")
    baseline_summary = report_summary(baseline_overall, "baseline")

    lines = [
        "# AU Simplification Shadow Test",
        "",
        "All variants start from stored archive `python_auto` scores and apply isolated rank/matrix deltas.",
        "",
        *_summary_block("Baseline", baseline_summary),
    ]

    for name, adjust_fn in VARIANTS.items():
        if name == "baseline":
            continue
        overall, _, _, _ = evaluate_races(load_archive_meetings(), name, adjust_fn)
        summary = report_summary(overall, name)
        delta = delta_report(baseline_overall, overall)
        lines.extend(_summary_block(name, summary, delta))

    output_path = Path(args.output_md)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
