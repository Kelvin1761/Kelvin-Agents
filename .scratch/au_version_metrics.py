#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MAINLINE_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"

sys.path.insert(0, str(MAINLINE_SCRIPTS))

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


def load_engine(engine_dir: Path):
    sys.path.insert(0, str(engine_dir))
    try:
        from engine_core import RacingEngine  # type: ignore
    finally:
        sys.path.pop(0)
    return RacingEngine


def iter_scored_races(racing_engine_cls):
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(
            meeting_dir.glob("Race_*_Logic.json"),
            key=lambda path: parse_int(path.stem.split("_")[1], 999),
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
            ranked_horses = []
            for horse_num, horse in logic.get("horses", {}).items():
                result_row = race_lookup.get(normalize_horse_name(horse.get("horse_name")))
                if not result_row:
                    continue

                engine = racing_engine_cls(horse, race_analysis)
                analysis = engine.analyze_horse()
                ranked_horses.append(
                    {
                        "horse_number": parse_int(horse_num) or 999,
                        "horse_name": horse.get("horse_name") or "",
                        "score": float(analysis.get("rank_score") or analysis.get("ability_score") or 0.0),
                        "actual_pos": int(result_row["pos"]),
                    }
                )

            if len(ranked_horses) < 4:
                continue

            yield {
                "meeting": meeting_dir.name,
                "race_no": race_no,
                "horses": ranked_horses,
            }


def collect_metrics(engine_dir: Path, label: str) -> dict:
    racing_engine_cls = load_engine(engine_dir)
    metrics = {
        "label": label,
        "engine_dir": str(engine_dir),
        "races": 0,
        "horses": 0,
        "champion": 0,
        "gold_3of3": 0,
        "pass_2of3": 0,
        "good_top2": 0,
        "top3_contains_winner": 0,
        "top3_places": 0,
        "zero_hit": 0,
    }

    for race in iter_scored_races(racing_engine_cls):
        ranked = sorted(race["horses"], key=lambda row: (-row["score"], row["horse_number"], row["horse_name"]))
        top1 = ranked[0]
        top2 = ranked[:2]
        top3 = ranked[:3]

        hits_top2 = sum(1 for row in top2 if row["actual_pos"] <= 3)
        hits_top3 = sum(1 for row in top3 if row["actual_pos"] <= 3)

        metrics["races"] += 1
        metrics["horses"] += len(ranked)
        metrics["top3_places"] += hits_top3
        if top1["actual_pos"] == 1:
            metrics["champion"] += 1
        if any(row["actual_pos"] == 1 for row in top3):
            metrics["top3_contains_winner"] += 1
        if hits_top3 == 3:
            metrics["gold_3of3"] += 1
        if hits_top3 >= 2:
            metrics["pass_2of3"] += 1
        if hits_top2 == 2:
            metrics["good_top2"] += 1
        if hits_top3 == 0:
            metrics["zero_hit"] += 1

    races = metrics["races"] or 1
    metrics["rates"] = {
        "champion": metrics["champion"] / races,
        "gold_3of3": metrics["gold_3of3"] / races,
        "pass_2of3": metrics["pass_2of3"] / races,
        "good_top2": metrics["good_top2"] / races,
        "top3_contains_winner": metrics["top3_contains_winner"] / races,
        "top3_place_precision": metrics["top3_places"] / (metrics["races"] * 3) if metrics["races"] else 0.0,
        "zero_hit": metrics["zero_hit"] / races,
    }
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-dir", required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    metrics = collect_metrics(Path(args.engine_dir).resolve(), args.label)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
