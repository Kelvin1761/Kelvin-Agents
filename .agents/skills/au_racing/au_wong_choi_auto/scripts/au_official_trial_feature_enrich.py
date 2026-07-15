#!/usr/bin/env python3
"""Attach verified official-trial features to AU Logic files as shadow data.

This script deliberately does *not* alter scoring.  A FreeFields trial total
time/L600 belongs to a heat, while finish and jockey belong to an individual
runner.  Keeping those levels separate lets the walk-forward test decide which
signals deserve to enter the production model.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING  # noqa: E402


RECORDS_PATH = AU_RACING / "Official_Free_Data" / "official_trial_events.jsonl"


def normalise_name(value: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", str(value or "").upper())
    return re.sub(r"[^A-Z0-9]+", "", text)


def seconds(value: str | None) -> float | None:
    try:
        parts = str(value or "").strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        pass
    return None


def meeting_date(meeting_dir: Path) -> str | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})\b", meeting_dir.name)
    if not match:
        return None
    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        return None
    return match.group(1)


def load_records() -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    if not RECORDS_PATH.exists():
        return grouped
    for line in RECORDS_PATH.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not row.get("meeting") or not row.get("race") or not row.get("horse_name"):
            continue
        key = (str(row["meeting"]), str(row["race"]), normalise_name(row["horse_name"]))
        grouped.setdefault(key, []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row.get("trial_date") or ""), reverse=True)
    return grouped


def build_features(records: list[dict[str, Any]], current_jockey: str, as_of_date: str) -> dict[str, Any] | None:
    usable = [row for row in records if str(row.get("trial_date") or "") < as_of_date]
    if not usable:
        return None
    usable.sort(key=lambda row: str(row.get("trial_date") or ""), reverse=True)
    current_key = normalise_name(current_jockey)
    runner_rows = [row for row in usable if row.get("runner_match_status") == "matched"]
    l600_speeds = []
    total_speeds = []
    for row in usable:
        official = row.get("official") if isinstance(row.get("official"), dict) else {}
        distance = official.get("distance_m") or row.get("distance_m")
        l600_seconds = seconds(official.get("last_600"))
        total_seconds = seconds(official.get("time"))
        if l600_seconds and l600_seconds > 0:
            l600_speeds.append(600.0 / l600_seconds)
        if distance and total_seconds and total_seconds > 0:
            total_speeds.append(float(distance) / total_seconds)
    jockey_matches = [
        row for row in runner_rows
        if current_key and normalise_name(row.get("trial_jockey") or "") == current_key
    ]
    official_top3 = sum(1 for row in runner_rows if str(row.get("official_finish") or "").isdigit() and int(row["official_finish"]) <= 3)
    latest = usable[0]
    latest_runner = latest.get("official_runner") if isinstance(latest.get("official_runner"), dict) else {}
    return {
        "schema_version": 1,
        "shadow_only": True,
        "as_of_date": as_of_date,
        "official_trial_count": len(usable),
        "official_trial_runner_match_count": len(runner_rows),
        "official_trial_top3_count": official_top3,
        "official_trial_electronic_count": sum(
            1 for row in usable
            if str((row.get("official") or {}).get("timing_method") or "").lower() == "electronic"
        ),
        "official_trial_l600_count": len(l600_speeds),
        "official_trial_l600_speed_avg": round(mean(l600_speeds), 4) if l600_speeds else None,
        "official_trial_l600_speed_latest": round(l600_speeds[0], 4) if l600_speeds else None,
        "official_trial_total_speed_avg": round(mean(total_speeds), 4) if total_speeds else None,
        "official_trial_latest_date": latest.get("trial_date"),
        "official_trial_latest_total_time": (latest.get("official") or {}).get("time"),
        "official_trial_latest_l600": (latest.get("official") or {}).get("last_600"),
        "official_trial_latest_timing_method": (latest.get("official") or {}).get("timing_method"),
        "official_trial_latest_jockey": latest.get("trial_jockey") or latest_runner.get("jockey") or "",
        "official_trial_latest_finish": int(latest["official_finish"]) if str(latest.get("official_finish") or "").isdigit() else None,
        "official_trial_jockey_match_count": len(jockey_matches),
        "official_trial_jockey_match_top3_count": sum(
            1 for row in jockey_matches
            if str(row.get("official_finish") or "").isdigit() and int(row["official_finish"]) <= 3
        ),
        "official_trial_latest_jockey_match": bool(
            current_key and normalise_name(latest.get("trial_jockey") or "") == current_key
        ),
        "official_trial_sources": sorted({str(row.get("authority") or "") for row in usable if row.get("authority")}),
        "model_rule": "Shadow-only: heat times are not individual sectionals. Use only in a leakage-safe walk-forward test before scoring changes.",
    }


def enrich_meeting(meeting_dir: Path, *, write: bool = True) -> tuple[int, int]:
    records = load_records()
    as_of = meeting_date(meeting_dir)
    if not as_of:
        return 0, 0
    updated = matched = 0
    for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json")):
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
        changed = False
        for horse in (logic.get("horses") or {}).values():
            if not isinstance(horse, dict):
                continue
            key = (meeting_dir.name, logic_path.stem, normalise_name(horse.get("horse_name") or ""))
            features = build_features(records.get(key, []), str(horse.get("jockey") or ""), as_of)
            if not features:
                continue
            data = horse.setdefault("_data", {})
            if data.get("official_trial_shadow") != features:
                data["official_trial_shadow"] = features
                changed = True
                updated += 1
            matched += 1
        if changed and write:
            logic_path.write_text(json.dumps(logic, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated, matched


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach official trial shadow features to AU Logic files.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--meeting-dir", type=Path)
    target.add_argument("--archive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    meetings = [args.meeting_dir] if args.meeting_dir else sorted(path for path in AU_RACING.iterdir() if path.is_dir() and path.name != "Official_Free_Data")
    total_updated = total_matched = 0
    for meeting in meetings:
        updated, matched = enrich_meeting(meeting, write=not args.dry_run)
        total_updated += updated
        total_matched += matched
    print(f"official trial shadow: matched horses={total_matched} | updated Logic files={total_updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
