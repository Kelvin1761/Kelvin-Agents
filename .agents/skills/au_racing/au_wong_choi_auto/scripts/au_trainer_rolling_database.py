#!/usr/bin/env python3
"""Maintain and attach leakage-safe AU trainer rolling-form shadow data.

The canonical source is AU_Historical_Raw_Race_Results.csv, rebuilt after a
meeting's results are collected.  A compact trainer/date index is materialised
so a pre-race meeting can query *only* records strictly before its date.
Nothing here alters ranking; promotion remains subject to future holdouts.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date, datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
import sys
sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING  # noqa: E402

RAW_CSV = AU_RACING / "AU_Historical_Raw_Race_Results.csv"
INDEX_PATH = AU_RACING / "AU_Trainer_Rolling_Database.json"
PRIOR_PLACE_RATE = 0.365
RAW_FIELDS = ("Date", "Track", "Race", "Distance", "Condition", "Pos", "Horse", "Barrier", "Weight", "Jockey", "Trainer", "Margin", "SP", "Time")


def clean_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def parse_int(value: object) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def _raw_key(row: dict) -> tuple[str, str, str, str]:
    return (str(row.get("Date") or ""), str(row.get("Track") or "").lower(),
            str(row.get("Race") or ""), clean_name(row.get("Horse")))


def _result_json_rows(path: Path) -> list[dict]:
    """Normalise crawler's structured post-race JSON into canonical raw rows."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    meeting = payload.get("meeting") or {}
    day = str(meeting.get("date_local") or meeting.get("date_utc") or "")[:10]
    track = str(meeting.get("name") or "").strip()
    events = payload.get("events") or {}
    results = payload.get("results") or {}
    output = []
    for race_key, runners in results.items():
        event = events.get(str(race_key)) or events.get(int(race_key)) or {}
        for runner in runners or []:
            if runner.get("is_scratched"):
                continue
            pos = parse_int(runner.get("finish_position"))
            if not day or not track or not pos:
                continue
            output.append({
                "Date": day, "Track": track, "Race": str(race_key),
                "Distance": str(event.get("distance") or ""),
                "Condition": str(event.get("track_condition") or ""),
                "Pos": str(pos), "Horse": str(runner.get("horse_name") or ""),
                "Barrier": str(runner.get("barrier") or ""), "Weight": str(runner.get("weight") or ""),
                "Jockey": str(runner.get("jockey") or ""), "Trainer": str(runner.get("trainer") or ""),
                "Margin": str(runner.get("margin") or ""), "SP": str(runner.get("starting_price") or ""),
                "Time": str(runner.get("finish_time") or event.get("winning_time") or ""),
            })
    return output


def sync_result_json() -> tuple[int, int]:
    """Merge all stored structured AU results into raw history, idempotently."""
    current: dict[tuple[str, str, str, str], dict] = {}
    if RAW_CSV.exists():
        with RAW_CSV.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if _raw_key(row)[-1]:
                    current[_raw_key(row)] = {field: str(row.get(field) or "") for field in RAW_FIELDS}
    scanned = added_or_updated = 0
    for path in AU_RACING.rglob("Race_Results_*.json"):
        scanned += 1
        for row in _result_json_rows(path):
            key = _raw_key(row)
            if not key[-1]:
                continue
            previous = current.get(key)
            canonical = {field: str(row.get(field) or "") for field in RAW_FIELDS}
            if previous != canonical:
                current[key] = canonical
                added_or_updated += 1
    ordered = sorted(current.values(), key=lambda row: (row["Date"], row["Track"], parse_int(row["Race"]) or 999, parse_int(row["Pos"]) or 999))
    with RAW_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS)
        writer.writeheader()
        writer.writerows(ordered)
    return scanned, added_or_updated


def build_index() -> dict:
    trainers: dict[str, dict] = {}
    rows = 0
    if not RAW_CSV.exists():
        raise FileNotFoundError(RAW_CSV)
    with RAW_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            day = parse_date(row.get("Date"))
            pos = parse_int(row.get("Pos"))
            trainer = str(row.get("Trainer") or "").strip()
            key = clean_name(trainer)
            if not day or not pos or not key:
                continue
            record = trainers.setdefault(key, {"name": trainer, "runs": []})
            record["runs"].append({
                "date": day.isoformat(), "pos": pos,
                "track": str(row.get("Track") or "").strip(),
                "distance": parse_int(row.get("Distance")) or 0,
            })
            rows += 1
    for record in trainers.values():
        record["runs"].sort(key=lambda item: item["date"])
    all_dates = [item["date"] for rec in trainers.values() for item in rec["runs"]]
    payload = {
        "schema_version": 1,
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": str(RAW_CSV),
        "source_mtime": RAW_CSV.stat().st_mtime,
        "source_rows": rows,
        "source_min_date": min(all_dates) if all_dates else "",
        "source_max_date": max(all_dates) if all_dates else "",
        "source_scope": "local archive/crawler results; not verified as a full all-Australia result feed",
        "trainers": trainers,
    }
    INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return payload


def load_index(*, rebuild_if_stale: bool = True) -> dict:
    if not INDEX_PATH.exists() or not RAW_CSV.exists():
        return build_index()
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return build_index()
    if rebuild_if_stale and float(data.get("source_mtime") or 0) < RAW_CSV.stat().st_mtime:
        return build_index()
    return data


def stats_before(record: dict | None, as_of: date, days: int) -> dict:
    runs = []
    for item in (record or {}).get("runs") or []:
        day = parse_date(item.get("date"))
        if day and 0 < (as_of - day).days <= days:
            runs.append(item)
    count = len(runs)
    wins = sum(item["pos"] == 1 for item in runs)
    places = sum(item["pos"] <= 3 for item in runs)
    return {
        "runs": count, "wins": wins, "places": places,
        "win_rate": round(wins / count, 4) if count else None,
        "place_rate": round(places / count, 4) if count else None,
    }


def candidate_score(stat90: dict, stat365: dict) -> tuple[float | None, str]:
    if stat90["runs"] >= 5:
        stat, shrink, label = stat90, 10.0, "90日"
    elif stat365["runs"] >= 10:
        stat, shrink, label = stat365, 20.0, "365日"
    else:
        return None, "樣本不足"
    rate = (stat["places"] + shrink * PRIOR_PLACE_RATE) / (stat["runs"] + shrink)
    return max(45.0, min(75.0, 60.0 + (rate - PRIOR_PLACE_RATE) * 100.0)), label


def enrich_meeting(meeting_dir: Path, *, write: bool = True) -> tuple[int, int]:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", meeting_dir.name)
    if not match:
        return 0, 0
    as_of = date.fromisoformat(match.group(1))
    index = load_index()
    source_max = parse_date(index.get("source_max_date"))
    stale_days = max(0, (as_of - source_max).days) if source_max else None
    updated = eligible = 0
    for logic_path in meeting_dir.glob("Race_*_Logic.json"):
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
        changed = False
        for horse in (logic.get("horses") or {}).values():
            trainer = str(horse.get("trainer") or "").strip()
            record = (index.get("trainers") or {}).get(clean_name(trainer))
            stat90 = stats_before(record, as_of, 90)
            stat365 = stats_before(record, as_of, 365)
            score, window = candidate_score(stat90, stat365)
            shadow = {
                "schema_version": 1, "shadow_only": True,
                "as_of_date": as_of.isoformat(), "source_max_date": index.get("source_max_date", ""),
                "source_scope": index.get("source_scope", "local archive results"),
                "source_stale_days": stale_days, "trainer": trainer,
                "stats_90d": stat90, "stats_365d": stat365,
                "candidate_score": round(score, 2) if score is not None else None,
                "candidate_window": window,
                "model_rule": "display/shadow only; never changes trainer_score until multi-window holdout passes",
            }
            data = horse.setdefault("_data", {})
            if data.get("trainer_rolling_shadow") != shadow:
                data["trainer_rolling_shadow"] = shadow
                changed = True
                updated += 1
            eligible += int(score is not None)
        if changed and write:
            logic_path.write_text(json.dumps(logic, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated, eligible


def main() -> int:
    parser = argparse.ArgumentParser(description="AU trainer rolling form database/shadow enricher")
    parser.add_argument("--build", action="store_true", help="Rebuild the trainer/date index from canonical raw results")
    parser.add_argument("--sync-results", action="store_true", help="Merge stored structured AU result JSON then rebuild the index")
    parser.add_argument("--meeting-dir", type=Path, help="Attach strictly pre-race rolling shadow fields to a meeting")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.build and not args.meeting_dir and not args.sync_results:
        parser.error("one of --build, --sync-results or --meeting-dir is required")
    if args.sync_results:
        scanned, changed = sync_result_json()
        print(f"trainer rolling result sync: json_files={scanned} rows_added_or_updated={changed}")
        args.build = True
    if args.build:
        data = build_index()
        print(f"trainer rolling index: rows={data['source_rows']} trainers={len(data['trainers'])} through={data['source_max_date']}")
    if args.meeting_dir:
        updated, eligible = enrich_meeting(args.meeting_dir.resolve(), write=not args.dry_run)
        print(f"trainer rolling shadow: eligible={eligible} updated horses={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
