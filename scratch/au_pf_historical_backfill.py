#!/usr/bin/env python3
"""Backfill pre-race Racenet PF metrics into a separate research cache.

The script never overwrites archive meetings. Historical form guides are
re-extracted under /private/tmp and reduced to a provenance-rich JSON cache.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "Wong Choi Horse Race Analysis/AU_Racing"
BACKFILL_ROOT = Path("/private/tmp/au_pf_backfill")
CACHE = ARCHIVE / "AU_PF_Historical_Backfill_Cache_2026-07-13.json"
EXTRACTOR = ROOT / ".agents/skills/au_racing/au_race_extractor/scripts/extractor.py"
AU_RACING_PATH = ROOT / ".agents/skills/au_racing"
LOCAL_RACE_INDEX = Path("/private/tmp/au_ranking_structural_review_cache.json")

HORSE_HEADER = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\((\d+)\)\s*$", re.M)
PF_TOKEN = re.compile(r"PF\[(.+?)\]")


def venue_from_folder(name: str) -> str:
    text = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", name)
    return re.sub(r"\s+Race\s+\d+(?:-\d+)?$", "", text, flags=re.I).strip()


def meeting_date(name: str) -> str | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    return match.group(1) if match else None


def meeting_slug(name: str) -> str | None:
    date = meeting_date(name)
    if not date:
        return None
    venue = re.sub(r"[^a-z0-9]+", "-", venue_from_folder(name).lower()).strip("-")
    return f"{venue}-{date.replace('-', '')}"


def expected_races(name: str) -> int:
    match = re.search(r"Race\s+(\d+)-(\d+)$", name, flags=re.I)
    if match:
        return int(match.group(2)) - int(match.group(1)) + 1
    return indexed_meetings().get(name, 0)


def indexed_meetings() -> dict[str, int]:
    """Use the already-localised research index; never rescan cloud files."""
    if not hasattr(indexed_meetings, "_cache"):
        payload = json.loads(LOCAL_RACE_INDEX.read_text(encoding="utf-8"))
        meetings: dict[str, int] = {}
        for race in payload.get("races", []):
            name = str(race.get("meeting") or "")
            meetings[name] = max(meetings.get(name, 0), int(race.get("race") or 0))
        indexed_meetings._cache = meetings
    return indexed_meetings._cache


def archive_has_pf(meeting: Path) -> bool:
    for path in meeting.glob("*Race * Formguide.md"):
        try:
            if "PF[" in path.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def normalised_venue(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", venue_from_folder(value).lower())


def output_meeting(meeting: Path) -> Path | None:
    exact = BACKFILL_ROOT / meeting.name
    if exact.is_dir():
        return exact
    date = meeting_date(meeting.name)
    if not date:
        return None
    venue = normalised_venue(meeting.name)
    candidates = [
        path for path in BACKFILL_ROOT.glob(f"{date} *")
        if path.is_dir() and normalised_venue(path.name) == venue
    ]
    return sorted(candidates)[0] if candidates else None


def output_complete(meeting: Path) -> bool:
    output = output_meeting(meeting)
    if not output:
        return False
    guides = [path for path in output.glob("*Race * Formguide.md") if "Index" not in path.name]
    token_count = sum(
        path.read_text(encoding="utf-8", errors="ignore").count("PF[")
        for path in guides
    )
    return len(guides) >= expected_races(meeting.name) and token_count > 0


def discover_missing() -> list[Path]:
    # Re-fetch every indexed meeting into one local, provenance-consistent
    # source.  Older meetings need the backfill; newer meetings are mirrored so
    # the raw contextual PF runs can be standardised without repeatedly reading
    # cloud-backed archive files.
    return [
        ARCHIVE / name
        for name in sorted(indexed_meetings())
        if meeting_date(name)
    ]


def extract_one(meeting: Path, timeout: int) -> dict:
    if output_complete(meeting):
        return {"meeting": meeting.name, "status": "cached"}
    slug = meeting_slug(meeting.name)
    if not slug:
        return {"meeting": meeting.name, "status": "invalid_slug"}
    url = f"https://www.racenet.com.au/form-guide/horse-racing/{slug}/all-races"
    env = os.environ.copy()
    env["WONGCHOI_DATA_ROOT"] = str(BACKFILL_ROOT)
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(AU_RACING_PATH)))
    try:
        result = subprocess.run(
            [sys.executable, str(EXTRACTOR), url, "all"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"meeting": meeting.name, "status": "timeout", "url": url}
    complete = output_complete(meeting)
    status = "ok" if complete else f"incomplete_exit_{result.returncode}"
    message = (result.stderr or result.stdout or "").strip().splitlines()
    return {
        "meeting": meeting.name,
        "status": status,
        "url": url,
        "message": message[-1] if message else "",
    }


def parse_pf_number(pattern: str, text: str):
    match = re.search(pattern, text)
    try:
        return float(match.group(1)) if match else None
    except (TypeError, ValueError):
        return None


def parse_pf_string(pattern: str, text: str):
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def parse_pf_token(token: str) -> dict:
    return {
        "l600_time": parse_pf_number(r"Last600:\s*([-\d.]+)", token),
        "runner_time": parse_pf_number(r"Runner Time:\s*([-\d.]+)", token),
        "race_time_diff": parse_pf_number(r"Race Time:\s*([-\d.]+)", token),
        "l800_delta": parse_pf_number(r"L800 Delta:\s*([-\d.]+)", token),
        "l600_delta": parse_pf_number(r"L600 Delta:\s*([-\d.]+)", token),
        "l400_delta": parse_pf_number(r"L400 Delta:\s*([-\d.]+)", token),
        "l200_delta": parse_pf_number(r"L200 Delta:\s*([-\d.]+)", token),
        "tempo_qrank": parse_pf_number(r"Tempo QRank:\s*([-\d.]+)", token),
        "early_runner_pace": parse_pf_string(r"Early Runner Pace:\s*([^.]+)\.", token),
        "early_race_pace": parse_pf_string(r"Early Race Pace:\s*([^.]+)\.", token),
    }


def going_bucket(value: str) -> str:
    number = parse_pf_number(r"(\d+(?:\.\d+)?)", value)
    if number is None:
        text = str(value or "").lower()
        if "heavy" in text:
            return "Heavy"
        if "soft" in text:
            return "Soft"
        return "Unknown"
    if number >= 8:
        return "Heavy"
    if number >= 5:
        return "Soft"
    return "Good/Firm"


def parse_run_line(line: str, target_date: str) -> dict | None:
    token_match = PF_TOKEN.search(line)
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line)
    if not token_match or not date_match or "**(TRIAL)**" in line:
        return None
    run_date = date_match.group(1)
    if run_date >= target_date:
        return None
    prefix = line[:date_match.start()].strip()
    track_match = re.match(r"(.+?)\s+R(\d+)\s*$", prefix)
    distance_match = re.search(rf"{re.escape(run_date)}\s+(\d+)m", line)
    condition_match = re.search(r"\bcond:([^\s]+)", line)
    weight_match = re.search(r"\([^)]*\)\s+([0-9.]+)kg", line)
    margin_match = re.search(r"\bmargin:([-\d.]+)", line)
    parsed = parse_pf_token(token_match.group(1))
    parsed.update({
        "run_date": run_date,
        "track": track_match.group(1).strip() if track_match else "Unknown",
        "race_number": int(track_match.group(2)) if track_match else None,
        "distance": int(distance_match.group(1)) if distance_match else None,
        "condition": condition_match.group(1) if condition_match else "",
        "going_bucket": going_bucket(condition_match.group(1) if condition_match else ""),
        "weight": float(weight_match.group(1)) if weight_match else None,
        "margin": float(margin_match.group(1)) if margin_match else None,
    })
    return parsed


def race_number_from_name(name: str) -> int | None:
    match = re.search(r"Race\s+(\d+)\s+Formguide", name, flags=re.I)
    return int(match.group(1)) if match else None


def parse_formguide(path: Path, target_date: str) -> tuple[dict, int]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    headers = list(HORSE_HEADER.finditer(text))
    horses = {}
    rejected = 0
    for index, header in enumerate(headers):
        body = text[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(text)]
        runs = []
        for line in body.splitlines():
            token_match = PF_TOKEN.search(line)
            date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line)
            if token_match and date_match and date_match.group(1) >= target_date:
                rejected += 1
                continue
            parsed = parse_run_line(line, target_date)
            if parsed:
                runs.append(parsed)
        horses[header.group(1)] = {
            "horse_name": header.group(2).strip(),
            "runs": runs,
        }
    return horses, rejected


def build_cache() -> dict:
    meetings = {}
    leakage_rejections = 0
    for archive_meeting in discover_missing():
        date = meeting_date(archive_meeting.name)
        output = output_meeting(archive_meeting)
        if not date or not output_complete(archive_meeting) or not output:
            continue
        races = {}
        for formguide in sorted(output.glob("*Race * Formguide.md")):
            race_number = race_number_from_name(formguide.name)
            if race_number is None:
                continue
            horses, rejected = parse_formguide(formguide, date)
            leakage_rejections += rejected
            races[str(race_number)] = horses
        meetings[archive_meeting.name] = {
            "target_date": date,
            "source_url": f"https://www.racenet.com.au/form-guide/horse-racing/{meeting_slug(archive_meeting.name)}/all-races",
            "races": races,
        }
    payload = {
        "version": "AU_PF_HISTORICAL_BACKFILL_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pre_race_only": True,
        "archive_logic_mutated": False,
        "meetings": meetings,
        "meeting_count": len(meetings),
        "race_count": sum(len(item["races"]) for item in meetings.values()),
        "horse_count": sum(len(horses) for item in meetings.values() for horses in item["races"].values()),
        "run_count": sum(len(horse["runs"]) for item in meetings.values() for horses in item["races"].values() for horse in horses.values()),
        "leakage_rejections": leakage_rejections,
    }
    CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=150)
    parser.add_argument("--build-cache", action="store_true")
    args = parser.parse_args()
    BACKFILL_ROOT.mkdir(parents=True, exist_ok=True)
    if args.build_cache:
        payload = build_cache()
        print(json.dumps({key: payload[key] for key in ("meeting_count", "race_count", "horse_count", "run_count", "leakage_rejections")}, indent=2))
        print(CACHE)
        return 0

    missing = [meeting for meeting in discover_missing() if not output_complete(meeting)]
    selected = missing[:args.limit]
    print(f"missing={len(missing)} selected={len(selected)} workers={args.workers}", flush=True)
    if not selected:
        return 0
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(extract_one, meeting, args.timeout) for meeting in selected]
        for future in as_completed(futures):
            row = future.result()
            results.append(row)
            print(f"{row['status']}: {row['meeting']}", flush=True)
    failures = [row for row in results if row["status"] not in {"ok", "cached"}]
    print(f"completed={len(results)} failures={len(failures)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
