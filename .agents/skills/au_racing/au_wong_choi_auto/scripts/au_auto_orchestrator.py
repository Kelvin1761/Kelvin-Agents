#!/usr/bin/env python3
"""
AU Wong Choi Auto Orchestrator.
Deterministic full-Python AU scoring/ranking/output pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from engine_core import RacingEngine, enrich_logic_from_facts
from renderer import ensure_verdict, render_meeting_csv, validate_report_text, write_race_outputs
from validation import validate_engine_scripts, validate_logic_data


def process_logic_file(logic_path: Path) -> dict:
    logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
    race_number = logic_data.get("race_analysis", {}).get("race_number")
    facts_path = _facts_path_for_logic(logic_path, race_number)
    if facts_path and facts_path.exists():
        logic_data = enrich_logic_from_facts(logic_data, facts_path)
    race_context = logic_data.get("race_analysis", {})
    race_context["field_summary"] = _build_field_summary(logic_data.get("horses", {}))
    for horse_num, horse in logic_data.get("horses", {}).items():
        facts_section = ""
        data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
        if isinstance(data, dict):
            facts_section = data.get("facts_section", "")
        engine = RacingEngine(horse, race_context, facts_section=facts_section, facts_path=facts_path)
        horse["python_auto"] = engine.analyze_horse()
    # SIP-030: _apply_place_rerank removed — fully numeric ranking only
    ensure_verdict(logic_data)
    errors = validate_logic_data(logic_data)
    if errors:
        raise ValueError(f"Logic validation failed for {logic_path}:\n" + "\n".join(errors))
    md_path, csv_path = write_race_outputs(logic_path, logic_data)
    report_errors = validate_report_text(md_path.read_text(encoding="utf-8"))
    if report_errors:
        raise ValueError(f"Report validation failed for {md_path}:\n" + "\n".join(report_errors))
    logic_path.write_text(json.dumps(logic_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Auto analysis written: {md_path.name}")
    print(f"✅ Auto scoring written: {csv_path.name}")
    return logic_data


def process_meeting_dir(meeting_dir: Path) -> list[dict]:
    results = []
    logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=_logic_sort_key)
    if not logic_files:
        raise FileNotFoundError(f"No Race_*_Logic.json files found in {meeting_dir}")
    for logic_path in logic_files:
        results.append(process_logic_file(logic_path))
    meeting_csv = render_meeting_csv(results)
    if meeting_csv:
        (meeting_dir / "Meeting_Auto_Scoring.csv").write_text(meeting_csv, encoding="utf-8")
        print("✅ Meeting_Auto_Scoring.csv updated")
    return results


def _facts_path_for_logic(logic_path: Path, race_number):
    if race_number in (None, ""):
        return None
    matches = sorted(logic_path.parent.glob(f"*Race {race_number} Facts.md"))
    return matches[0] if matches else None


def _logic_sort_key(path: Path):
    stem = path.stem
    try:
        return int(stem.split("_")[1])
    except (IndexError, ValueError):
        return 999


def _build_field_summary(horses):
    weights = []
    for horse in horses.values():
        try:
            weight = float(horse.get("weight"))
        except (TypeError, ValueError):
            continue
        weights.append(weight)
    if not weights:
        return {}
    return {
        "count": len(weights),
        "min_weight": min(weights),
        "max_weight": max(weights),
        "avg_weight": sum(weights) / len(weights),
    }


def _apply_place_rerank(logic_data: dict) -> None:
    race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    horses = logic_data.get("horses", {}) if isinstance(logic_data.get("horses"), dict) else {}
    if not _rerank_target_race(race):
        return
    ranked = sorted(
        [
            (str(num), horse)
            for num, horse in horses.items()
            if isinstance(horse.get("python_auto"), dict)
        ],
        key=lambda item: (
            -float(item[1]["python_auto"].get("rank_score", item[1]["python_auto"].get("ability_score", 0))),
            -float(item[1]["python_auto"].get("ability_score", 0)),
            _horse_number_sort_key(item[0]),
        ),
    )
    for idx, (horse_num, horse) in enumerate(ranked[:6], start=1):
        auto = horse.get("python_auto", {})
        matrix = auto.get("matrix_scores", {}) if isinstance(auto.get("matrix_scores"), dict) else {}
        features = auto.get("feature_scores", {}) if isinstance(auto.get("feature_scores"), dict) else {}
        risk_flags = set(auto.get("risk_flags", []) or [])
        bonus = 0.0
        if idx >= 4:
            if float(matrix.get("form_line", 60)) >= 70:
                bonus += 0.45
            if float(matrix.get("class_weight", 60)) >= 66:
                bonus += 0.55
            if float(matrix.get("track", 60)) >= 60:
                bonus += 0.20
            if float(matrix.get("stability", 60)) >= 66 and "high_consumption_load" not in risk_flags:
                bonus += 0.20
        else:
            if (
                float(matrix.get("sectional", 60)) >= 74
                and float(matrix.get("race_shape", 60)) >= 66
                and float(matrix.get("class_weight", 60)) <= 61
                and float(matrix.get("form_line", 60)) <= 68
                and "high_consumption_load" not in risk_flags
            ):
                bonus -= 0.45
            if (
                float(features.get("sectional_score", 60)) >= 74
                and float(features.get("form_score", 60)) <= 60
                and float(features.get("consistency_score", 60)) <= 60
            ):
                bonus -= 0.35
        if bonus:
            auto["rank_score"] = round(float(auto.get("rank_score", auto.get("ability_score", 0))) + bonus, 4)
            auto["place_rerank_bonus"] = round(bonus, 4)


def _rerank_target_race(race: dict) -> bool:
    race_class = str(race.get("race_class") or "").lower()
    going = str(race.get("going") or "").lower()
    field_summary = race.get("field_summary") if isinstance(race.get("field_summary"), dict) else {}
    field_count = int(field_summary.get("count") or 0)
    if "soft" in going or "heavy" in going:
        return False
    if field_count < 9 or field_count > 12:
        return False
    if "bm" not in race_class:
        return False
    return any(token in race_class for token in ("bm58", "bm64", "bm66", "bm68", "bm70", "bm72", "bm74", "bm78"))


def _horse_number_sort_key(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 999


def main():
    parser = argparse.ArgumentParser(description="AU Wong Choi Auto Orchestrator")
    parser.add_argument("target", help="Meeting directory or Race_X_Logic.json")
    args = parser.parse_args()

    script_errors = validate_engine_scripts(SCRIPT_DIR / "racing_engine")
    if script_errors:
        raise ValueError("Engine validation failed:\n" + "\n".join(script_errors))

    target = Path(args.target).resolve()
    if target.is_file():
        process_logic_file(target)
    elif target.is_dir():
        process_meeting_dir(target)
    else:
        raise FileNotFoundError(target)


if __name__ == "__main__":
    main()
