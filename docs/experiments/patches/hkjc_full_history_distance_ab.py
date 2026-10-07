#!/usr/bin/env python3
"""A/B the complete-profile distance-history correctness fix.

Baseline uses each archived Logic file unchanged. Candidate replaces only the
season/same-distance/same-course aggregates and distance-aptitude summary with
the complete point-in-time race table already rendered in the matching Facts
file. No result, odds, or same-day row enters the candidate features.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
PATCHES = Path(__file__).resolve().parent
AUTO = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
FACTS = REPO / ".agents/scripts"
for path in (PATCHES, AUTO, FACTS):
    sys.path.insert(0, str(path))

import hkjc_hierarchical_refit as metrics  # noqa: E402
import inject_hkjc_fact_anchors as facts  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402


def _integer(value: object) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def _facts_path(folder: Path, race_no: int) -> Path | None:
    matches = sorted(folder.glob(f"* Race {race_no} Facts.md"))
    return matches[0] if len(matches) == 1 else None


def _horse_blocks(text: str) -> dict[int, str]:
    output: dict[int, str] = {}
    for block in re.split(r"(?=^### 馬號 \d+)", text, flags=re.MULTILINE):
        match = re.match(r"^### 馬號 (\d+) —", block)
        if match:
            output[int(match.group(1))] = block
    return output


def _history(block: str) -> list[dict]:
    rows = []
    seen_dates = set()
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        columns = [part.strip() for part in line.split("|")]
        if len(columns) < 10 or not columns[1].isdigit():
            continue
        dt = facts.parse_date(columns[2])
        if dt is None or dt.date().isoformat() in seen_dates:
            continue
        try:
            distance = int(columns[4])
            finish = int(columns[9])
        except (TypeError, ValueError):
            continue
        if distance <= 0 or finish <= 0:
            continue
        rows.append({
            "date": columns[2],
            "date_dt": dt,
            "venue": columns[3],
            "distance": distance,
            "finish": finish,
        })
        seen_dates.add(dt.date().isoformat())
    rows.sort(key=lambda row: row["date_dt"], reverse=True)
    return rows


def _record(rows: list[dict], predicate) -> list[int]:
    record = [0, 0, 0, 0]
    for row in rows:
        if not predicate(row):
            continue
        finish = int(row["finish"])
        record[min(finish, 4) - 1] += 1
    return record


def _candidate_fields(rows: list[dict], race_context: dict, meeting_date: datetime) -> tuple[str, str]:
    distance = _integer(race_context.get("distance"))
    venue = facts.normalize_venue_surface(race_context.get("venue") or race_context.get("racecourse"))
    season_start = datetime(
        meeting_date.year if meeting_date.month >= facts.SEASON_START_MONTH else meeting_date.year - 1,
        facts.SEASON_START_MONTH,
        1,
    )
    season = _record(rows, lambda row: season_start <= row["date_dt"] < meeting_date)
    same_distance = _record(rows, lambda row: int(row["distance"]) == distance)
    same_course = _record(
        rows,
        lambda row: int(row["distance"]) == distance
        and facts.normalize_venue_surface(row["venue"]) == venue,
    )
    season_stats = (
        f"季內 ({'-'.join(map(str, season))}) | "
        f"同程 ({'-'.join(map(str, same_distance))}) | "
        f"同場同程 ({'-'.join(map(str, same_course))})"
    )

    aptitude = facts.compute_distance_aptitude(rows, distance)
    current = aptitude["today_record"]
    total = sum(current)
    if total:
        best_distance = (
            f"{aptitude['best_dist']}m | 今仗 {distance}m = "
            f"{total}場 ({current[0]}-{current[1]}-{current[2]})"
        )
    elif aptitude.get("close_wins"):
        values = ", ".join(f"{value}m" for value in aptitude["close_wins"])
        best_distance = f"{aptitude['best_dist']}m | 今仗 {distance}m = 未跑過，但有相近贏馬經驗 ({values}) ✅"
    elif aptitude.get("close_places"):
        values = ", ".join(f"{value}m" for value in aptitude["close_places"])
        best_distance = f"{aptitude['best_dist']}m | 今仗 {distance}m = 未跑過，但有相近上名經驗 ({values})"
    else:
        best_distance = f"{aptitude['best_dist']}m | 今仗 {distance}m = 未跑過且無相近近績 (±100m) ⚠️"
    return season_stats, best_distance


def _apply_candidate(horse: dict, season_stats: str, best_distance: str) -> None:
    horse["season_stats"] = season_stats
    horse["best_distance"] = best_distance
    data = horse.setdefault("_data", {})
    data["season_stats_line"] = season_stats
    data["best_distance"] = best_distance


def _result_map(folder: Path) -> dict[str, dict[int, int]]:
    matches = sorted(folder.glob("*_全日賽果.json"))
    if len(matches) != 1:
        return {}
    payload = json.loads(matches[0].read_text(encoding="utf-8"))
    output = {}
    for race_no, race in payload.items():
        positions = {}
        for row in race.get("results", []):
            number = _integer(row.get("horse_no"))
            position = _integer(row.get("pos"))
            if number and position:
                positions[number] = position
        if positions:
            output[str(race_no)] = positions
    return output


def _score(horses: dict, race_context: dict) -> tuple[dict[int, float], dict[int, dict]]:
    scores, details = {}, {}
    for horse_no, horse in horses.items():
        number = _integer(horse_no)
        result = RacingEngine(horse, race_context).analyze_horse()
        scores[number] = float(result["ability_score"])
        details[number] = result
    return scores, details


def _record_for(scores: dict[int, float], actual: dict[int, int]) -> dict:
    picks = sorted(scores, key=lambda number: (-scores[number], number))
    top3 = {number for number, position in actual.items() if position <= 3}
    return {
        "picks": picks,
        "gold": top3.issubset(set(picks[:4])),
        "good": len(picks) >= 2 and picks[0] in top3 and picks[1] in top3,
    }


def _window(rows: list[dict]) -> dict:
    candidate = [row["candidate_flags"] for row in rows]
    baseline = [row["baseline_flags"] for row in rows]
    return {
        "baseline": metrics._summarize(baseline),
        "candidate": metrics._summarize(candidate),
        "paired": metrics._paired(candidate, baseline),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(args.meeting_root)
    rows = []
    audit = Counter()
    ability_deltas = []
    for folder in sorted(root.glob("20??-??-??_*")):
        date_match = re.match(r"(20\d{2}-\d{2}-\d{2})", folder.name)
        if not date_match:
            continue
        meeting_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
        actual_by_race = _result_map(folder)
        for logic_path in sorted(folder.glob("Race_*_Logic.json")):
            race_match = re.search(r"Race_(\d+)_Logic", logic_path.name)
            if not race_match or race_match.group(1) not in actual_by_race:
                continue
            race_no = int(race_match.group(1))
            facts_path = _facts_path(folder, race_no)
            if facts_path is None:
                continue
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            context = copy.deepcopy(logic.get("race_analysis") or {})
            context["race_date"] = meeting_date.date().isoformat()
            baseline_horses = copy.deepcopy(logic.get("horses") or {})
            candidate_horses = copy.deepcopy(baseline_horses)
            blocks = _horse_blocks(facts_path.read_text(encoding="utf-8"))

            for horse_no, horse in candidate_horses.items():
                number = _integer(horse_no)
                history = _history(blocks.get(number, ""))
                if not history:
                    continue
                audit["horses_with_history"] += 1
                audit["future_or_same_day_rows"] += sum(row["date_dt"] >= meeting_date for row in history)
                season_stats, best_distance = _candidate_fields(history, context, meeting_date)
                before_stats = str(horse.get("season_stats") or "")
                before_distance = str(horse.get("best_distance") or horse.get("_data", {}).get("best_distance") or "")
                if before_stats != season_stats:
                    audit["season_stats_changed"] += 1
                if before_distance != best_distance:
                    audit["best_distance_changed"] += 1
                _apply_candidate(horse, season_stats, best_distance)

            baseline_scores, baseline_details = _score(baseline_horses, context)
            candidate_scores, candidate_details = _score(candidate_horses, context)
            actual = actual_by_race[str(race_no)]
            common = set(actual) & set(baseline_scores) & set(candidate_scores)
            if len(common) < 4 or len({n for n in common if actual[n] <= 3}) < 3:
                continue
            actual = {number: actual[number] for number in common}
            baseline_scores = {number: baseline_scores[number] for number in common}
            candidate_scores = {number: candidate_scores[number] for number in common}
            baseline_record = _record_for(baseline_scores, actual)
            candidate_record = _record_for(candidate_scores, actual)
            baseline_flags = metrics._flags(baseline_record, actual)
            candidate_flags = metrics._flags(candidate_record, actual)
            venue = facts.normalize_venue_surface(context.get("venue") or context.get("racecourse"))
            surface = "HV_TURF" if venue == "跑馬地" else "ST_AWT" if venue == "沙田AWT" else "ST_TURF"
            rows.append({
                "race_key": f"{folder.name}::{race_no}",
                "date": meeting_date.date().isoformat(),
                "surface": surface,
                "field_size": len(actual),
                "actual_pos": actual,
                "models": {"current_live": baseline_record, "candidate": candidate_record},
                "baseline_flags": baseline_flags,
                "candidate_flags": candidate_flags,
            })
            for number in common:
                delta = candidate_scores[number] - baseline_scores[number]
                ability_deltas.append(delta)
                if abs(delta) > 1e-9:
                    audit["ability_changed"] += 1
                before = set(baseline_details[number].get("risk_flags") or [])
                after = set(candidate_details[number].get("risk_flags") or [])
                if "distance_unproven" in before and "distance_unproven" not in after:
                    audit["distance_risk_resolved"] += 1

    dates = sorted({row["date"] for row in rows})
    terminal_count = max(1, math.ceil(len(dates) * 0.15))
    terminal_dates = set(dates[-terminal_count:])
    dev = [row for row in rows if row["date"] not in terminal_dates]
    terminal = [row for row in rows if row["date"] in terminal_dates]
    report = {
        "contract": {
            "races": len(rows),
            "dates": len(dates),
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "terminal_dates": [min(terminal_dates), max(terminal_dates)] if terminal_dates else [],
            "terminal_races": len(terminal),
            "candidate": "complete point-in-time profile history for distance aggregates",
        },
        "leakage_audit": {
            "future_or_same_day_rows": audit["future_or_same_day_rows"],
            "status": "PASS" if audit["future_or_same_day_rows"] == 0 else "FAIL",
        },
        "coverage": dict(audit),
        "ability_delta": {
            "changed_runners": audit["ability_changed"],
            "mean_abs": sum(abs(value) for value in ability_deltas) / len(ability_deltas) if ability_deltas else 0.0,
            "max_abs": max((abs(value) for value in ability_deltas), default=0.0),
        },
        "development": _window(dev),
        "terminal": _window(terminal),
        "all": _window(rows),
        "cohorts": metrics._cohort_report(rows),
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
