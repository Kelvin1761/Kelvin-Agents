#!/usr/bin/env python3
"""
AU auto weighting review baseline.
Scans AU archive meetings dynamically and evaluates current live deterministic outputs.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import asdict

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.append(str(PROJECT_ROOT / ".agents" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"))

from reflector_auto_stats import compute_race_stats, parse_results, parse_results_json, run_stats
from engine_core import RacingEngine, enrich_logic_from_facts


HK_EXCLUDE_TOKENS = (
    "ShaTin",
    "Sha Tin",
    "HappyValley",
    "Happy Valley",
    "HKJC",
)


def find_au_meetings(base_dir: pathlib.Path) -> list[pathlib.Path]:
    meetings = []
    for path in sorted(base_dir.iterdir()):
        if not path.is_dir():
            continue
        if any(token in path.name for token in HK_EXCLUDE_TOKENS):
            continue
        has_logic = bool(list(path.glob("Race_*_Logic.json")))
        has_au_artifacts = bool(list(path.glob("*Racecard.md"))) or bool(list(path.glob("*Formguide.md"))) or bool(list(path.glob("*Facts.md")))
        has_results = bool(meeting_results_file(path))
        if has_logic and has_au_artifacts and has_results:
            meetings.append(path)
    return meetings


def meeting_results_file(meeting_dir: pathlib.Path) -> pathlib.Path | None:
    md_results = sorted(meeting_dir.glob("Race_Results_Reflector.md"))
    if md_results:
        return md_results[0]
    json_results = sorted(meeting_dir.glob("Race_Results_*.json"))
    return json_results[0] if json_results else None


def summarize_stats(stats: dict) -> dict:
    summary = stats.get("summary", {})
    races = stats.get("races", [])
    total = summary.get("total_races", 0)
    champ = summary.get("champion_hit_rates", {}).get("top1_champion", {}).get("count", 0)
    gold = summary.get("position_hit_rates", {}).get("gold_standard", {}).get("count", 0)
    good = summary.get("position_hit_rates", {}).get("good_result", {}).get("count", 0)
    minimum = summary.get("position_hit_rates", {}).get("min_threshold", {}).get("count", 0)
    order_issue = summary.get("ranking_order", {}).get("pick34_beat_12", {}).get("count", 0)
    avg_top4_hits = 0.0
    mrr = 0.0
    if races and total:
        hit_sum = 0.0
        rr_sum = 0.0
        for race in races:
            top_picks = race.get("top_picks", [])
            actual_top3 = race.get("actual_top3", [])
            actual_pos = {row[1]: row[0] for row in actual_top3}
            hit_sum += sum(1 for pick in top_picks[:4] if pick[1] in actual_pos)
            winner = actual_top3[0][1] if actual_top3 else None
            rr = 0.0
            for idx, pick in enumerate(top_picks[:4], start=1):
                if pick[1] == winner:
                    rr = 1.0 / idx
                    break
            rr_sum += rr
        avg_top4_hits = round(hit_sum / total, 3)
        mrr = round(rr_sum / total, 4)
    return {
        "meetings": None,
        "races": total,
        "Champion": champ,
        "Gold": gold,
        "Good": good,
        "Minimum": minimum,
        "MRR": mrr,
        "Order Issue": order_issue,
        "Avg Top4 Hits": avg_top4_hits,
    }


def _load_results_map(results_file: pathlib.Path) -> dict[int, list]:
    if results_file.suffix.lower() == ".json":
        return parse_results_json(str(results_file))
    results_text = results_file.read_text(encoding="utf-8")
    race_results = {}
    race_sections = re.split(r"(?:##?\s*(?:Race|第)\s*(\d+)|---)", results_text)
    if len(race_sections) <= 1:
        all_results = parse_results(results_text)
        if all_results:
            race_results[1] = all_results
        return race_results
    current_race = None
    for section in race_sections:
        if section and section.strip().isdigit():
            current_race = int(section.strip())
            continue
        if current_race is None:
            continue
        res = parse_results(section)
        if res:
            race_results[current_race] = res
    return race_results


def _logic_sort_key(path: pathlib.Path) -> int:
    match = re.search(r"Race_(\d+)_Logic\.json$", path.name)
    return int(match.group(1)) if match else 999


def _facts_path_for_logic(logic_path: pathlib.Path, race_number: int | None) -> pathlib.Path | None:
    if race_number in (None, 0):
        return None
    matches = sorted(logic_path.parent.glob(f"*Race {race_number} Facts.md"))
    return matches[0] if matches else None


def _build_field_summary(horses: dict) -> dict:
    weights = []
    for horse in horses.values():
        try:
            weights.append(float(horse.get("weight")))
        except (TypeError, ValueError):
            continue
    if not weights:
        return {}
    return {
        "count": len(weights),
        "min_weight": min(weights),
        "max_weight": max(weights),
        "avg_weight": sum(weights) / len(weights),
    }


def _ranked_picks_from_logic(logic_path: pathlib.Path) -> list[tuple[int, int, str]]:
    logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
    race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    race_number = race.get("race_number")
    facts_path = _facts_path_for_logic(logic_path, int(race_number) if str(race_number).isdigit() else None)
    if facts_path and facts_path.exists():
        logic_data = enrich_logic_from_facts(logic_data, facts_path)
        race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    race["field_summary"] = _build_field_summary(logic_data.get("horses", {}))

    ranked = []
    for horse_num, horse in logic_data.get("horses", {}).items():
        data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
        auto = RacingEngine(
            horse,
            race,
            facts_section=data.get("facts_section", ""),
            facts_path=facts_path,
        ).analyze_horse()
        try:
            horse_number = int(horse_num)
        except (TypeError, ValueError):
            horse_number = 999
        ranked.append(
            {
                "horse_number": horse_number,
                "horse_name": str(horse.get("horse_name") or "").strip(),
                "rank_score": float(auto.get("rank_score", auto.get("ability_score", 0)) or 0.0),
                "ability_score": float(auto.get("ability_score", 0) or 0.0),
            }
        )

    ranked.sort(key=lambda row: (-row["rank_score"], -row["ability_score"], row["horse_number"]))
    return [
        (idx, row["horse_number"], row["horse_name"])
        for idx, row in enumerate(ranked[:4], start=1)
    ]


def summarize_race_stats(stats_list: list) -> dict:
    total = len(stats_list)
    champ = sum(1 for s in stats_list if s.champion_hit)
    gold = sum(1 for s in stats_list if s.gold_standard)
    good = sum(1 for s in stats_list if s.good_result)
    minimum = sum(1 for s in stats_list if s.min_threshold)
    order_issue = sum(1 for s in stats_list if s.pick34_beat_12)
    hit_sum = 0.0
    rr_sum = 0.0
    for race in stats_list:
        actual_pos = {row[1]: row[0] for row in race.actual_top3}
        hit_sum += sum(1 for pick in race.top_picks[:4] if pick[1] in actual_pos)
        winner = race.actual_top3[0][1] if race.actual_top3 else None
        rr = 0.0
        for idx, pick in enumerate(race.top_picks[:4], start=1):
            if pick[1] == winner:
                rr = 1.0 / idx
                break
        rr_sum += rr
    return {
        "meetings": None,
        "races": total,
        "Champion": champ,
        "Gold": gold,
        "Good": good,
        "Minimum": minimum,
        "MRR": round(rr_sum / total, 4) if total else 0.0,
        "Order Issue": order_issue,
        "Avg Top4 Hits": round(hit_sum / total, 3) if total else 0.0,
    }


def _rendered_mainline_race_stats(meeting: pathlib.Path, results_file: pathlib.Path) -> list:
    rendered_stats = run_stats(str(meeting), str(results_file)).get("races", [])
    rendered_map = {item["race_num"]: item for item in rendered_stats}
    results_map = _load_results_map(results_file)
    logic_paths = { _logic_sort_key(path): path for path in sorted(meeting.glob("Race_*_Logic.json"), key=_logic_sort_key) }
    auto_races = {
        int(match.group(1))
        for path in meeting.glob("Race_*_Auto_Analysis.md")
        for match in [re.search(r"Race_(\d+)_Auto_Analysis\.md$", path.name)]
        if match
    }

    race_stats = []
    eligible_races = sorted(set(logic_paths) | auto_races)
    for race_num in eligible_races:
        results = results_map.get(race_num, [])
        if not results:
            continue
        rendered = rendered_map.get(race_num)
        if race_num in auto_races and rendered:
            stats = compute_race_stats(rendered.get("top_picks", []), results, {})
            stats.race_num = race_num
            race_stats.append(stats)
            continue
        logic_path = logic_paths.get(race_num)
        if logic_path:
            picks = _ranked_picks_from_logic(logic_path)
            if not picks:
                continue
            stats = compute_race_stats(picks, results, {})
            stats.race_num = race_num
            race_stats.append(stats)
    return race_stats


def run_recomputed_review(base_dir: pathlib.Path) -> dict:
    meetings = find_au_meetings(base_dir)
    aggregate = {
        "meetings": len(meetings),
        "races": 0,
        "Champion": 0,
        "Gold": 0,
        "Good": 0,
        "Minimum": 0,
        "MRR": 0.0,
        "Order Issue": 0,
        "Avg Top4 Hits": 0.0,
    }
    mrr_weighted = 0.0
    top4_weighted = 0.0
    total_races = 0
    details = []
    for meeting in meetings:
        results_file = meeting_results_file(meeting)
        if not results_file:
            continue
        results_map = _load_results_map(results_file)
        race_stats = []
        for logic_path in sorted(meeting.glob("Race_*_Logic.json"), key=_logic_sort_key):
            race_num = _logic_sort_key(logic_path)
            results = results_map.get(race_num, [])
            if not results:
                continue
            picks = _ranked_picks_from_logic(logic_path)
            if not picks:
                continue
            stats = compute_race_stats(picks, results, {})
            stats.race_num = race_num
            race_stats.append(stats)
        summary = summarize_race_stats(race_stats)
        races = summary["races"]
        if not races:
            continue
        total_races += races
        aggregate["Champion"] += summary["Champion"]
        aggregate["Gold"] += summary["Gold"]
        aggregate["Good"] += summary["Good"]
        aggregate["Minimum"] += summary["Minimum"]
        aggregate["Order Issue"] += summary["Order Issue"]
        mrr_weighted += summary["MRR"] * races
        top4_weighted += summary["Avg Top4 Hits"] * races
        details.append(
            {
                "meeting": meeting.name,
                **summary,
                "races_detail": [asdict(item) for item in race_stats],
            }
        )
    aggregate["races"] = total_races
    aggregate["MRR"] = round(mrr_weighted / total_races, 4) if total_races else 0.0
    aggregate["Avg Top4 Hits"] = round(top4_weighted / total_races, 3) if total_races else 0.0
    return {"current_live": aggregate, "details": details}


def run_review(base_dir: pathlib.Path, mode: str = "rendered") -> dict:
    if mode == "recomputed":
        return run_recomputed_review(base_dir)
    meetings = find_au_meetings(base_dir)
    aggregate = {
        "meetings": len(meetings),
        "races": 0,
        "Champion": 0,
        "Gold": 0,
        "Good": 0,
        "Minimum": 0,
        "MRR": 0.0,
        "Order Issue": 0,
        "Avg Top4 Hits": 0.0,
    }
    mrr_weighted = 0.0
    top4_weighted = 0.0
    total_races = 0
    details = []
    for meeting in meetings:
        results_file = meeting_results_file(meeting)
        if not results_file:
            continue
        race_stats = _rendered_mainline_race_stats(meeting, results_file)
        summary = summarize_race_stats(race_stats)
        races = summary["races"]
        if not races:
            continue
        total_races += races
        aggregate["Champion"] += summary["Champion"]
        aggregate["Gold"] += summary["Gold"]
        aggregate["Good"] += summary["Good"]
        aggregate["Minimum"] += summary["Minimum"]
        aggregate["Order Issue"] += summary["Order Issue"]
        mrr_weighted += summary["MRR"] * races
        top4_weighted += summary["Avg Top4 Hits"] * races
        details.append({"meeting": meeting.name, **summary})
    aggregate["races"] = total_races
    aggregate["MRR"] = round(mrr_weighted / total_races, 4) if total_races else 0.0
    aggregate["Avg Top4 Hits"] = round(top4_weighted / total_races, 3) if total_races else 0.0
    return {"current_live": aggregate, "details": details}


def main():
    parser = argparse.ArgumentParser(description="Review AU current live deterministic weighting baseline")
    parser.add_argument("--base-dir", default=str(PROJECT_ROOT / "Archive_Race_Analysis"))
    parser.add_argument("--mode", choices=("rendered", "recomputed"), default="rendered")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_review(pathlib.Path(args.base_dir), mode=args.mode)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    current = report["current_live"]
    print("current_live")
    for key in ("meetings", "races", "Champion", "Gold", "Good", "Minimum", "MRR", "Order Issue", "Avg Top4 Hits"):
        print(f"{key} {current[key]}")


if __name__ == "__main__":
    main()
