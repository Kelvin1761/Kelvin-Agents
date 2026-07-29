#!/usr/bin/env python3
"""Build conservative HKJC race-level anomaly annotations.

The annotations are review-only.  Odds and post-race incident text never enter
the pre-race score.  A race is flagged only when either:

1. an actual Top-3 runner started at or above the explicit extreme-outsider
   threshold; or
2. a model Top-2 runner missed the placings and the official report contains a
   material medical, interference, or abnormal-event phrase for that runner.

The unfiltered benchmark remains authoritative.  These annotations only add a
second adjusted view so unpredictable outcomes cannot drive optimisation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from hkjc_results_db import (
    build_results_index,
    get_analysis_archive_root,
    get_season_results_roots,
)


ROOT = Path(__file__).resolve().parents[5]
DEFAULT_DATASET = ROOT / "scratch" / "hkjc_prerace_replay.csv"
DEFAULT_OUTPUT = ROOT / "scratch" / "hkjc_anomaly_annotations.csv"
DEFAULT_SUMMARY = ROOT / "scratch" / "hkjc_anomaly_annotations_summary.json"

INJURY_PATTERNS = (
    r"流鼻血",
    r"心律不正常",
    r"喘鳴症",
    r"不良於行",
    r"跛",
    r"骨折",
    r"受傷",
    r"患有",
    r"失去[^。]{0,12}蹄鐵",
)
INTERFERENCE_PATTERNS = (
    r"大力勒避",
    r"嚴重受阻",
    r"受困[^。]{0,25}未能望空",
    r"未能望空",
    r"未能被全力催策",
    r"被阻礙",
    r"失去平衡及失地",
)
MAJOR_PATTERNS = (
    r"收停",
    r"退出",
    r"表現難以接受",
    r"必須試閘及格[^。]{0,60}獸醫檢驗",
    r"未能全力催策[^。]{0,20}終點",
)
NON_FINISH = {"PU", "WV", "DNF", "FE", "UR", "TNP"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--extreme-outsider-odds",
        type=float,
        default=30.0,
        help="Top-3 win-odds threshold used only for adjusted review (default: 30)",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def finish_position(value: Any) -> int:
    text = str(value or "").strip().upper()
    return as_int(text, 99) if text not in NON_FINISH else 99


def horse_base_name(value: Any) -> str:
    return re.sub(r"\s*\([A-Z]\d+\)\s*$", "", str(value or "")).strip()


def _marker_matches(report: str, results: list[dict[str, Any]]) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    for row in results:
        horse = as_int(row.get("horse_no"))
        position = re.escape(str(row.get("pos") or "").strip())
        name = re.escape(horse_base_name(row.get("horse_name")))
        if not horse or not position or not name:
            continue
        pattern = rf"(?:^|\s){position}\s+{horse}\s+{name}(?:\s*\([A-Z]\d+\))?"
        match = re.search(pattern, report)
        if match:
            matches.append((match.start(), horse))
    return sorted(matches)


def incident_segments(report: Any, results: list[dict[str, Any]]) -> dict[int, str]:
    text = re.sub(r"\s+", " ", str(report or "")).strip()
    if not text:
        return {}
    markers = _marker_matches(text, results)
    segments: dict[int, str] = {}
    for index, (start, horse) in enumerate(markers):
        end = markers[index + 1][0] if index + 1 < len(markers) else len(text)
        segments[horse] = text[start:end].strip()
    return segments


def has_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def result_file_for_race(
    results_index: dict[str, Path],
    *,
    date: str,
    meeting: str,
) -> Path | None:
    indexed = results_index.get(date)
    if indexed is not None:
        return indexed
    meeting_dir = get_analysis_archive_root() / meeting
    local = sorted(meeting_dir.glob("*全日賽果.json"))
    return local[0] if local else None


def build_annotations(
    dataset: Path,
    *,
    extreme_outsider_odds: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    races: defaultdict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(dataset):
        meeting = Path(str(row.get("meeting") or "")).name
        race = as_int(row.get("race_number"))
        if meeting and race > 0:
            races[(meeting, race)].append(row)

    results_index = build_results_index(get_season_results_roots())
    day_cache: dict[Path, dict[str, Any]] = {}
    annotations: list[dict[str, Any]] = []
    missing_results: list[str] = []
    flagged_counts: defaultdict[str, int] = defaultdict(int)

    for (meeting, race_number), rows in sorted(races.items()):
        date = str(rows[0].get("date") or meeting[:10])
        result_path = result_file_for_race(
            results_index,
            date=date,
            meeting=meeting,
        )
        race_result: dict[str, Any] = {}
        if result_path is not None:
            if result_path not in day_cache:
                try:
                    day_cache[result_path] = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    day_cache[result_path] = {}
            race_result = day_cache[result_path].get(str(race_number), {})

        results = race_result.get("results") if isinstance(race_result, dict) else None
        if not isinstance(results, list):
            missing_results.append(f"{meeting} R{race_number}")
            results = []

        result_by_horse = {
            as_int(item.get("horse_no")): item
            for item in results
            if isinstance(item, dict) and as_int(item.get("horse_no")) > 0
        }
        segments = incident_segments(race_result.get("incident_report"), results)
        top2 = {
            as_int(row.get("horse_number"))
            for row in rows
            if 0 < as_int(row.get("reference_original_rank")) <= 2
        }

        outsider_evidence: list[str] = []
        injury_evidence: list[str] = []
        interference_evidence: list[str] = []
        major_evidence: list[str] = []
        abnormal_evidence: list[str] = []

        for horse, item in result_by_horse.items():
            finish = finish_position(item.get("pos"))
            odds = as_float(item.get("win_odds"))
            name = horse_base_name(item.get("horse_name"))
            if finish <= 3 and odds is not None and odds >= extreme_outsider_odds:
                outsider_evidence.append(f"#{horse} {name} actual {finish}／odds {odds:g}")

            if horse not in top2 or finish <= 3:
                continue
            segment = segments.get(horse, "")
            if str(item.get("pos") or "").strip().upper() in NON_FINISH:
                abnormal_evidence.append(f"#{horse} {name} {item.get('pos')}")
            if segment and has_pattern(segment, INJURY_PATTERNS):
                injury_evidence.append(f"#{horse} {name}: {segment[:180]}")
            if segment and has_pattern(segment, INTERFERENCE_PATTERNS):
                interference_evidence.append(f"#{horse} {name}: {segment[:180]}")
            if segment and has_pattern(segment, MAJOR_PATTERNS):
                major_evidence.append(f"#{horse} {name}: {segment[:180]}")

        flags = {
            "extreme_outsider": bool(outsider_evidence),
            "major_incident": bool(major_evidence),
            "interference": bool(interference_evidence),
            "injury": bool(injury_evidence),
            "abnormal": bool(abnormal_evidence),
        }
        for flag, enabled in flags.items():
            flagged_counts[flag] += int(enabled)
        notes = []
        for label, evidence in (
            ("extreme_outsider", outsider_evidence),
            ("major_incident", major_evidence),
            ("interference", interference_evidence),
            ("injury", injury_evidence),
            ("abnormal", abnormal_evidence),
        ):
            if evidence:
                notes.append(f"{label}: {' || '.join(evidence)}")
        annotations.append(
            {
                "meeting": meeting,
                "race_number": race_number,
                **flags,
                "notes": " | ".join(notes),
            }
        )

    flagged_races = sum(
        any(row[flag] for flag in ("extreme_outsider", "major_incident", "interference", "injury", "abnormal"))
        for row in annotations
    )
    summary = {
        "method": {
            "source": "HKJC full_day_results.json",
            "extreme_outsider_odds": extreme_outsider_odds,
            "incident_scope": "model Top-2 missed placing + conservative official-report phrase",
            "score_usage": False,
            "unfiltered_retained": True,
        },
        "coverage": {
            "races": len(annotations),
            "results_matched": len(annotations) - len(missing_results),
            "missing_results": len(missing_results),
            "flagged_races": flagged_races,
            "adjusted_races": len(annotations) - flagged_races,
        },
        "flag_counts": dict(flagged_counts),
        "missing_result_races": missing_results,
    }
    return annotations, summary


def main() -> int:
    args = parse_args()
    annotations, summary = build_annotations(
        args.dataset,
        extreme_outsider_odds=args.extreme_outsider_odds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "meeting",
            "race_number",
            "extreme_outsider",
            "major_incident",
            "interference",
            "injury",
            "abnormal",
            "notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(annotations)
    args.summary_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["coverage"], ensure_ascii=False))
    print(f"annotations={args.output}")
    print(f"summary={args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
