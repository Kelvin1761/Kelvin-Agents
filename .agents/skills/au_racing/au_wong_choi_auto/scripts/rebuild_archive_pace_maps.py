#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(PROJECT_ROOT / ".agents" / "scripts"))

from au_archive_calibrator import detect_meeting_date, detect_meeting_track, parse_int  # type: ignore
from build_au_logic import _load_track_profile  # type: ignore
from inject_fact_anchors import _aggregate_confidence, _classify_pace_v2, _pace_confidence  # type: ignore


ARCHIVE_ROOT = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
STYLE_GROUP_MAP = {
    "前領": "leaders",
    "跟前": "pressers",
    "守中": "mid_pack",
    "後上": "closers",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild venue-aware pace maps for archived AU logic files")
    parser.add_argument("--archive-root", type=Path, default=ARCHIVE_ROOT)
    parser.add_argument("--meeting", help="Optional substring filter for a specific meeting directory")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _racecard_header(meeting_dir: Path, race_no: int) -> str:
    candidates = sorted(meeting_dir.glob(f"*Race {race_no} Racecard.md"))
    if not candidates:
        return ""
    return candidates[0].read_text(encoding="utf-8").splitlines()[0].strip()


def _going_from_header(header: str) -> str:
    match = re.search(r"Track:\s*([^|]+?)\s*(?:\||$)", header)
    return match.group(1).strip() if match else ""


def _distance_m(value: object) -> int:
    return parse_int(value, 0) or 0


def _horse_group_from_style_line(style_line: str) -> str:
    parts = [part.strip() for part in str(style_line or "").split("/") if part.strip()]
    if len(parts) >= 2:
        return STYLE_GROUP_MAP.get(parts[1], "")
    if parts:
        return STYLE_GROUP_MAP.get(parts[0], "")
    return ""


def _existing_group(speed_map: dict, horse_no: int) -> str:
    for key in ("leaders", "pressers", "on_pace", "mid_pack", "closers"):
        if horse_no in (speed_map.get(key) or []):
            return key
    return ""


def _existing_confidence(speed_map: dict, horse_no: int) -> str:
    evidence_text = str(speed_map.get("style_evidence") or "")
    match = re.search(rf"#{horse_no}\s+[^()]+\(([^()]+)\)", evidence_text)
    return match.group(1).strip() if match else ""


def _style_profile(horse_no: int, horse: dict, speed_map: dict) -> tuple[str, str]:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    style_line = str(data.get("running_style_line") or "").strip()
    confidence = str(data.get("style_confidence_line") or "").strip()
    group = _horse_group_from_style_line(style_line)
    if not group:
        group = _existing_group(speed_map, horse_no)
    if not confidence:
        confidence = _existing_confidence(speed_map, horse_no)
    return group, confidence


def _style_evidence_entry(horse_no: int, horse: dict, group: str, confidence: str) -> str:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    style_line = str(data.get("running_style_line") or "").strip()
    parts = [part.strip() for part in style_line.split("/") if part.strip()]
    if len(parts) >= 2:
        style_3way, style_cn = parts[0], parts[1]
    else:
        fallback_map = {
            "leaders": ("前置", "前領"),
            "pressers": ("前置", "跟前"),
            "mid_pack": ("守中", "守中"),
            "closers": ("後上", "後上"),
            "on_pace": ("前置", "跟前"),
        }
        style_3way, style_cn = fallback_map.get(group or "mid_pack", ("守中", "守中"))
    return f"#{horse_no} {style_3way}/{style_cn}({confidence or '低'})"


def _rebuild_speed_map(logic: dict, meeting_dir: Path, meeting_track: str, meeting_date: str) -> dict:
    race_analysis = logic.setdefault("race_analysis", {})
    old_speed_map = race_analysis.get("speed_map") if isinstance(race_analysis.get("speed_map"), dict) else {}
    horses = logic.get("horses") if isinstance(logic.get("horses"), dict) else {}
    race_no = parse_int(race_analysis.get("race_number")) or 0
    distance_m = _distance_m(race_analysis.get("distance"))
    header = _racecard_header(meeting_dir, race_no)
    going = (
        str(race_analysis.get("going") or "").strip()
        or str(old_speed_map.get("going") or "").strip()
        or _going_from_header(header)
    )

    groups = {key: [] for key in ("leaders", "pressers", "on_pace", "mid_pack", "closers")}
    style_profiles = []
    style_evidence = []
    field_size = 0

    for horse_key, horse in horses.items():
        horse_no = parse_int(horse_key)
        if horse_no is None:
            continue
        field_size += 1
        barrier = parse_int(horse.get("barrier"), 99) or 99
        group, confidence = _style_profile(horse_no, horse, old_speed_map)
        if not group:
            group = "mid_pack"
        groups[group].append({"num": horse_no, "barrier": barrier})
        if confidence:
            style_profiles.append({"num": horse_no, "confidence": confidence})
        style_evidence.append(_style_evidence_entry(horse_no, horse, group, confidence))

    for values in groups.values():
        values.sort(key=lambda row: (row["barrier"], row["num"]))

    predicted_pace = _classify_pace_v2(
        len(groups["leaders"]),
        len(groups["on_pace"]),
        field_size,
        distance_m or 1200,
        going,
        n_pressers=len(groups["pressers"]),
    )
    style_confidence = _aggregate_confidence([profile.get("confidence", "低") for profile in style_profiles])
    pace_confidence = _pace_confidence(
        style_profiles,
        len(groups["leaders"]),
        len(groups["pressers"]),
        field_size,
        meeting_track,
    )

    return {
        "predicted_pace": predicted_pace,
        "expected_pace": predicted_pace,
        "pace_confidence": pace_confidence,
        "style_confidence": style_confidence,
        "pace_volatility": str(old_speed_map.get("pace_volatility") or ""),
        "leaders": [row["num"] for row in groups["leaders"]],
        "pressers": [row["num"] for row in groups["pressers"]],
        "on_pace": [row["num"] for row in groups["on_pace"]],
        "mid_pack": [row["num"] for row in groups["mid_pack"]],
        "closers": [row["num"] for row in groups["closers"]],
        "style_evidence": "; ".join(style_evidence),
        "going": going,
        "track_bias": (
            f"FACTS_SPEED_MODEL: {meeting_track or 'Unknown venue'} {distance_m or '?'}m; "
            "using barriers, video/settled weighted recent run style, and engine cross-check."
        ),
        "tactical_nodes": (
            f"FACTS_SPEED_MODEL: leaders={len(groups['leaders'])}, pressers={len(groups['pressers'])}, "
            f"on_pace={len(groups['on_pace'])}, mid={len(groups['mid_pack'])}, closers={len(groups['closers'])}; "
            f"predicted pace {predicted_pace}; pace_confidence={pace_confidence}."
        ),
        "collapse_point": (
            "FACTS_SPEED_MODEL: high early pressure upgrades closers/savers; "
            "controlled tempo upgrades leaders/on-pace runners."
        ),
        "source": "FACTS_SPEED_MODEL_V4_ARCHIVE_REBUILD",
        "meeting_date": meeting_date,
    }


def _rebuild_metadata(logic: dict, meeting_dir: Path, meeting_track: str, meeting_date: str) -> dict:
    payload = deepcopy(logic)
    race_analysis = payload.setdefault("race_analysis", {})
    race_no = parse_int(race_analysis.get("race_number")) or 0
    header = _racecard_header(meeting_dir, race_no)
    going = (
        str(race_analysis.get("going") or "").strip()
        or str((race_analysis.get("speed_map") or {}).get("going") or "").strip()
        or _going_from_header(header)
    )
    speed_map = _rebuild_speed_map(payload, meeting_dir, meeting_track, meeting_date)
    race_analysis["speed_map"] = speed_map
    race_analysis["going"] = going

    meeting_intelligence = race_analysis.get("meeting_intelligence")
    if not isinstance(meeting_intelligence, dict):
        meeting_intelligence = {}
    meeting_intelligence = dict(meeting_intelligence)
    if meeting_track:
        meeting_intelligence["venue"] = meeting_track
    if meeting_date:
        meeting_intelligence["date"] = meeting_date
    if going:
        meeting_intelligence["going"] = going
    race_analysis["meeting_intelligence"] = meeting_intelligence

    track_profile = _load_track_profile(meeting_track, _distance_m(race_analysis.get("distance")))
    if track_profile:
        race_analysis["track_profile"] = track_profile
    return payload


def main() -> int:
    args = _parse_args()
    archive_root = args.archive_root
    meetings = sorted(path for path in archive_root.iterdir() if path.is_dir())
    if args.meeting:
        needle = args.meeting.lower()
        meetings = [path for path in meetings if needle in path.name.lower()]

    updated = 0
    changed = 0
    clear_before = 0
    clear_after = 0
    unknown_before = 0
    unknown_after = 0

    for meeting_dir in meetings:
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        if not meeting_track:
            continue

        for logic_path in logic_files:
            original = json.loads(logic_path.read_text(encoding="utf-8"))
            original_speed_map = (original.get("race_analysis") or {}).get("speed_map") or {}
            if original_speed_map.get("pace_confidence") == "Clear":
                clear_before += 1
            if "Unknown venue" in str(original_speed_map.get("track_bias") or ""):
                unknown_before += 1

            rebuilt = _rebuild_metadata(original, meeting_dir, meeting_track, meeting_date)
            rebuilt_speed_map = (rebuilt.get("race_analysis") or {}).get("speed_map") or {}
            if rebuilt_speed_map.get("pace_confidence") == "Clear":
                clear_after += 1
            if "Unknown venue" in str(rebuilt_speed_map.get("track_bias") or ""):
                unknown_after += 1

            updated += 1
            if rebuilt != original:
                changed += 1
                if not args.dry_run:
                    logic_path.write_text(json.dumps(rebuilt, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"updated_logic_files={updated}")
    print(f"changed_logic_files={changed}")
    print(f"clear_before={clear_before}")
    print(f"clear_after={clear_after}")
    print(f"unknown_before={unknown_before}")
    print(f"unknown_after={unknown_after}")
    print(f"mode={'dry-run' if args.dry_run else 'write'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
