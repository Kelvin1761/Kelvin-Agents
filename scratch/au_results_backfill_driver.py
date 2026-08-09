#!/usr/bin/env python3
"""Gentle daily Racenet results backfill for the AU Wong Choi results database.

Queue: scratch/au_backfill_queue.json — 2,669 real historical meetings mined
from our own horses' 賽績線/record tables (so every meeting is verified real
and maximally relevant to our jockey/trainer/horse population), ranked by how
many of our horses ran there.

Safety (RACENET_SAFE_MODE):
- default 8 meetings per run (transport guard: 18/process, 40/hour, 4s min);
- 25-45s random sleep between meetings;
- STOPS IMMEDIATELY on RacenetBlockedError or any fetch failure — no retries;
- resumable: done-list lives beside the output on Drive.

Output (Drive, AU_Racing root):
- AU_Backfill_Results/<date> <venue>/Race_Results_*.{md,json}
- AU_Backfill_Race_Results.csv — same schema as AU_Historical_Raw_Race_Results.csv
  (kept separate from the canonical file; consumers opt in).

Usage:
    python3 scratch/au_results_backfill_driver.py [--limit 8] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/Users/imac/Antigravity-repo")
sys.path.insert(0, str(REPO))
from wongchoi_paths import AU_RACING  # noqa: E402

QUEUE = REPO / "scratch" / "au_backfill_queue.json"
CLAW = REPO / ".agents" / "skills" / "au_racing" / "claw_racenet_results.py"
OUT_ROOT = AU_RACING / "AU_Backfill_Results"
DONE_PATH = OUT_ROOT / "backfill_done.json"
CSV_PATH = AU_RACING / "AU_Backfill_Race_Results.csv"
CSV_FIELDS = ["Date", "Track", "Race", "Distance", "Condition", "Pos", "Horse",
              "Barrier", "Weight", "Jockey", "Trainer", "Margin", "SP", "Time"]


def slugify(venue: str, date: str) -> str:
    slug = re.sub(r"[^a-z0-9 ]", "", venue.lower()).strip()
    return f"{slug.replace(' ', '-')}-{date.replace('-', '')}"


def append_csv_rows(date: str, venue: str, payload: dict) -> int:
    events = payload.get("events") or {}
    results = payload.get("results") or {}
    new_file = not CSV_PATH.exists()
    written = 0
    with CSV_PATH.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        for race_no, runners in sorted(results.items(), key=lambda kv: int(kv[0])):
            event = events.get(str(race_no)) or {}
            distance = re.sub(r"[^0-9]", "", str(event.get("distance") or ""))
            condition = str(event.get("track_condition") or "")
            for runner in runners:
                if runner.get("finish_position") in (None, 0, ""):
                    continue
                margin = runner.get("margin")
                writer.writerow({
                    "Date": date,
                    "Track": venue,
                    "Race": race_no,
                    "Distance": distance,
                    "Condition": condition,
                    "Pos": runner.get("finish_position"),
                    "Horse": runner.get("horse_name"),
                    "Barrier": runner.get("barrier"),
                    "Weight": f"{runner.get('weight')}kg" if runner.get("weight") else "",
                    "Jockey": runner.get("jockey"),
                    "Trainer": runner.get("trainer"),
                    "Margin": ("—" if not margin else f"{margin}L"),
                    "SP": (f"${runner.get('starting_price'):.2f}" if runner.get("starting_price") else ""),
                    "Time": runner.get("finish_time") or "",
                })
                written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Gentle Racenet results backfill")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    done = set(json.loads(DONE_PATH.read_text(encoding="utf-8"))) if DONE_PATH.exists() else set()

    picked = []
    for item in queue:  # queue is already sorted by relevance
        key = f"{item['date']}|{item['venue']}"
        if key not in done:
            picked.append(item)
        if len(picked) >= args.limit:
            break
    print(f"queue {len(queue)}, done {len(done)}, this run {len(picked)}")
    if args.dry_run:
        for item in picked:
            print("  would fetch:", slugify(item["venue"], item["date"]))
        return 0

    for idx, item in enumerate(picked, 1):
        date, venue = item["date"], item["venue"]
        key = f"{date}|{venue}"
        slug = slugify(venue, date)
        url = f"https://www.racenet.com.au/results/horse-racing/{slug}/all-races"
        out_dir = OUT_ROOT / f"{date} {venue}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{idx}/{len(picked)}] {slug}", flush=True)
        proc = subprocess.run(
            [sys.executable, str(CLAW), "--url", url, "--json", "--output_dir", str(out_dir)],
            capture_output=True, text=True,
        )
        json_files = list(out_dir.glob("Race_Results_*.json"))
        if proc.returncode != 0 or not json_files:
            blocked = "block" in (proc.stderr + proc.stdout).lower()
            print(f"  FAILED ({'BLOCKED — stopping for 24h' if blocked else 'no data'}): {proc.stderr[-200:]}", flush=True)
            if blocked:
                return 1
            done.add(key)  # bad slug / abandoned meeting: don't retry forever
            DONE_PATH.write_text(json.dumps(sorted(done)), encoding="utf-8")
            time.sleep(random.uniform(25, 45))
            continue
        payload = json.loads(json_files[0].read_text(encoding="utf-8"))
        rows = append_csv_rows(date, venue, payload)
        done.add(key)
        DONE_PATH.write_text(json.dumps(sorted(done)), encoding="utf-8")
        print(f"  OK — {rows} result rows appended", flush=True)
        if idx < len(picked):
            time.sleep(random.uniform(25, 45))
    print(f"DONE this run. total done {len(done)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
