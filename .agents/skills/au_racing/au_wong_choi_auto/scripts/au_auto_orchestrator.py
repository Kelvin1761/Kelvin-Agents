#!/usr/bin/env python3
"""
AU Wong Choi Auto Orchestrator.
Deterministic full-Python AU scoring/ranking/output pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from engine_core import RacingEngine, enrich_logic_from_facts
from renderer import ensure_verdict, render_meeting_csv, validate_report_text, write_race_outputs
from validation import validate_engine_scripts, validate_logic_data


def process_logic_file(logic_path: Path) -> dict:
    try:
        logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Failed to read/parse Logic.json: {logic_path}\n{e}")
    race_number = logic_data.get("race_analysis", {}).get("race_number")
    facts_path = _facts_path_for_logic(logic_path, race_number)
    if facts_path and facts_path.exists():
        logic_data = enrich_logic_from_facts(logic_data, facts_path)
    if "race_analysis" not in logic_data:
        logic_data["race_analysis"] = {}
    race_context = logic_data["race_analysis"]
    race_context["field_summary"] = _build_field_summary(logic_data.get("horses", {}))
    # Today's runner names so the engine can flag 賽績線 head-to-head rematches.
    race_context["field_horse_names"] = [
        h.get("horse_name") for h in logic_data.get("horses", {}).values()
        if isinstance(h, dict) and h.get("horse_name")
    ]
    for horse_num, horse in logic_data.get("horses", {}).items():
        # Inject the saddlecloth number (it is the dict key, not a field) so the
        # engine can match the horse to its speed-map pace role / settling pattern.
        horse.setdefault("horse_number", horse_num)
        facts_section = ""
        data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
        if isinstance(data, dict):
            facts_section = data.get("facts_section", "")
        engine = RacingEngine(horse, race_context, facts_section=facts_section, facts_path=facts_path)
        horse["python_auto"] = engine.analyze_horse()
    # SIP-030: legacy post-hoc place rerank layer removed; engine ability_score is computed upstream.
    ensure_verdict(logic_data)
    errors = validate_logic_data(logic_data)
    if errors:
        raise ValueError(f"Logic validation failed for {logic_path}:\n" + "\n".join(errors))
    # Write JSON first to avoid inconsistent state (json write before md/csv)
    try:
        logic_path.write_text(json.dumps(logic_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except TypeError as e:
        raise ValueError(f"Failed to serialize Logic.json: {logic_path}\n{e}")
    md_path, csv_path = write_race_outputs(logic_path, logic_data)
    report_errors = validate_report_text(md_path.read_text(encoding="utf-8"))
    if report_errors:
        raise ValueError(f"Report validation failed for {md_path}:\n" + "\n".join(report_errors))
    print(f"✅ Auto analysis written: {md_path.name}")
    print(f"✅ Auto scoring written: {csv_path.name}")
    return logic_data


def process_meeting_dir(meeting_dir: Path) -> list[dict]:
    results = []
    logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=_logic_sort_key)
    if not logic_files:
        raise FileNotFoundError(f"No Race_*_Logic.json files found in {meeting_dir}")
    for logic_path in logic_files:
        try:
            results.append(process_logic_file(logic_path))
        except Exception as e:
            print(f"⚠️  Skipping {logic_path.name}: {e}", file=sys.stderr)
            continue
    meeting_csv = render_meeting_csv(results)
    if meeting_csv:
        (meeting_dir / "Meeting_Auto_Scoring.csv").write_text(meeting_csv, encoding="utf-8")
        print("✅ Meeting_Auto_Scoring.csv updated")
    return results


def _facts_path_for_logic(logic_path: Path, race_number):
    if race_number in (None, ""):
        return None
    # Sanitise race_number to prevent glob injection
    safe_race_num = re.sub(r"[^0-9]", "", str(race_number))
    if not safe_race_num:
        return None
    matches = sorted(logic_path.parent.glob(f"*Race_{safe_race_num}_Facts.md"))
    return matches[0] if matches else None


def _logic_sort_key(path: Path):
    stem = path.stem
    try:
        return int(stem.split("_")[1])
    except (IndexError, ValueError):
        return 999


def _build_field_summary(horses):
    weights = []
    ratings = []
    for horse in horses.values():
        try:
            weight = float(horse.get("weight"))
        except (TypeError, ValueError):
            weight = None
        if weight is not None:
            weights.append(weight)
        try:
            rating = float(horse.get("rating"))
        except (TypeError, ValueError):
            rating = None
        if rating is not None:
            ratings.append(rating)
    if not horses:
        return {}
    ratings_sorted = sorted(ratings, reverse=True)
    return {
        "count": len(horses),
        "min_weight": min(weights) if weights else 0.0,
        "max_weight": max(weights) if weights else 0.0,
        "avg_weight": (sum(weights) / len(weights)) if weights else 0.0,
        "rated_count": len(ratings),
        "min_rating": min(ratings) if ratings else 0.0,
        "max_rating": max(ratings) if ratings else 0.0,
        "avg_rating": (sum(ratings) / len(ratings)) if ratings else 0.0,
        "rating_stdev": (
            (sum((value - (sum(ratings) / len(ratings))) ** 2 for value in ratings) / len(ratings)) ** 0.5
            if ratings
            else 0.0
        ),
        "top3_rating_cutoff": ratings_sorted[2] if len(ratings_sorted) >= 3 else (ratings_sorted[-1] if ratings_sorted else 0.0),
    }


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
