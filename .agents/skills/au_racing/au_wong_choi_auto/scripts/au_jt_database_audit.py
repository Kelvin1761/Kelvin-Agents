#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from au_archive_calibrator import ARCHIVE_ROOT, detect_meeting_track, parse_int

COMBO_PATH = ARCHIVE_ROOT / "AU_Jockey_Trainer_Combo_Stats.csv"
OUTPUT_MD = ARCHIVE_ROOT / "AU_JT_Database_Audit.md"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_combo_track(value: str) -> str:
    text = clean_text(value).lower()
    text = text.replace("*", " ")
    text = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", text)
    text = re.sub(r"\s+race\s+\d+(?:-\d+)?$", "", text)
    text = text.replace(" gardens", "")
    text = text.replace(" heath", "")
    text = text.replace(" lakeside", "")
    text = text.replace(" hillside", "")
    return clean_text(text)


def load_combo_stats():
    combo = {}
    trainer = defaultdict(lambda: {"runs": 0, "wins": 0, "places": 0})
    with COMBO_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            track = normalize_combo_track(row.get("Track"))
            jockey = clean_text(row.get("Jockey")).lower()
            trainer_name = clean_text(row.get("Trainer")).lower()
            if not track or not trainer_name:
                continue
            runs = int(float(row.get("Total Runs") or 0))
            wins = int(float(row.get("Wins") or 0))
            places = int(float(row.get("Places (Top 3)") or 0))
            if jockey:
                combo[(track, jockey, trainer_name)] = {"runs": runs, "wins": wins, "places": places}
            trainer_bucket = trainer[(track, trainer_name)]
            trainer_bucket["runs"] += runs
            trainer_bucket["wins"] += wins
            trainer_bucket["places"] += places
    return combo, trainer


def bucket_runs(runs: int) -> str:
    if runs <= 0:
        return "0"
    if runs <= 2:
        return "1-2"
    if runs <= 4:
        return "3-4"
    if runs <= 9:
        return "5-9"
    return "10+"


def pct(part: int, whole: int) -> str:
    return f"{(part / whole) * 100:.1f}%" if whole else "0.0%"


def main():
    combo_cache, trainer_cache = load_combo_stats()
    total_horses = 0
    counts = Counter()
    combo_run_buckets = Counter()
    trainer_run_buckets = Counter()
    by_track = defaultdict(Counter)

    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        venue = normalize_combo_track(detect_meeting_track(meeting_dir, sample_logic))
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            for horse in logic.get("horses", {}).values():
                total_horses += 1
                data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
                jockey = clean_text(horse.get("jockey")).lower()
                trainer_name = clean_text(horse.get("trainer")).lower()

                if clean_text(data.get("current_jockey_history_line")):
                    counts["history_line"] += 1
                if int(float(data.get("current_jockey_formal_rides") or 0)) > 0:
                    counts["current_formal_rides"] += 1
                if int(float(data.get("current_jockey_trial_rides") or 0)) > 0:
                    counts["current_trial_rides"] += 1
                if int(float(data.get("best_formal_jockey_rides") or 0)) > 0:
                    counts["best_formal_rides"] += 1

                combo_stats = combo_cache.get((venue, jockey, trainer_name), {}) if venue and jockey and trainer_name else {}
                trainer_stats = trainer_cache.get((venue, trainer_name), {}) if venue and trainer_name else {}

                if combo_stats:
                    counts["combo_any"] += 1
                    combo_run_buckets[bucket_runs(combo_stats.get("runs", 0))] += 1
                else:
                    combo_run_buckets["0"] += 1
                if combo_stats.get("runs", 0) >= 5:
                    counts["combo_5"] += 1
                if combo_stats.get("runs", 0) >= 10:
                    counts["combo_10"] += 1

                if trainer_stats:
                    counts["trainer_any"] += 1
                    trainer_run_buckets[bucket_runs(trainer_stats.get("runs", 0))] += 1
                else:
                    trainer_run_buckets["0"] += 1
                if trainer_stats.get("runs", 0) >= 10:
                    counts["trainer_10"] += 1
                if trainer_stats.get("runs", 0) >= 20:
                    counts["trainer_20"] += 1

                by_track[venue]["horses"] += 1
                if combo_stats.get("runs", 0) >= 5:
                    by_track[venue]["combo_5"] += 1
                if trainer_stats.get("runs", 0) >= 10:
                    by_track[venue]["trainer_10"] += 1

    lines = [
        "# AU JT Database Audit",
        "",
        f"- Horse entries scanned: **{total_horses}**",
        f"- `current_jockey_history_line`: **{counts['history_line']} / {total_horses} = {pct(counts['history_line'], total_horses)}**",
        f"- `current_jockey_formal_rides > 0`: **{counts['current_formal_rides']} / {total_horses} = {pct(counts['current_formal_rides'], total_horses)}**",
        f"- `current_jockey_trial_rides > 0`: **{counts['current_trial_rides']} / {total_horses} = {pct(counts['current_trial_rides'], total_horses)}**",
        f"- `best_formal_jockey_rides > 0`: **{counts['best_formal_rides']} / {total_horses} = {pct(counts['best_formal_rides'], total_horses)}**",
        "",
        "## Venue Combo Coverage",
        "",
        f"- Exact jockey+trainer+track combo exists: **{counts['combo_any']} / {total_horses} = {pct(counts['combo_any'], total_horses)}**",
        f"- Combo sample `>=5`: **{counts['combo_5']} / {total_horses} = {pct(counts['combo_5'], total_horses)}**",
        f"- Combo sample `>=10`: **{counts['combo_10']} / {total_horses} = {pct(counts['combo_10'], total_horses)}**",
        "",
        "## Trainer Track Coverage",
        "",
        f"- Trainer+track exists: **{counts['trainer_any']} / {total_horses} = {pct(counts['trainer_any'], total_horses)}**",
        f"- Trainer+track sample `>=10`: **{counts['trainer_10']} / {total_horses} = {pct(counts['trainer_10'], total_horses)}**",
        f"- Trainer+track sample `>=20`: **{counts['trainer_20']} / {total_horses} = {pct(counts['trainer_20'], total_horses)}**",
        "",
        "## Combo Sample Buckets",
        "",
        "| Bucket | Horses | Share |",
        "|---|---:|---:|",
    ]
    for key in ("0", "1-2", "3-4", "5-9", "10+"):
        value = combo_run_buckets.get(key, 0)
        lines.append(f"| {key} | {value} | {pct(value, total_horses)} |")

    lines.extend(
        [
            "",
            "## Trainer Track Sample Buckets",
            "",
            "| Bucket | Horses | Share |",
            "|---|---:|---:|",
        ]
    )
    for key in ("0", "1-2", "3-4", "5-9", "10+"):
        value = trainer_run_buckets.get(key, 0)
        lines.append(f"| {key} | {value} | {pct(value, total_horses)} |")

    lines.extend(
        [
            "",
            "## Track Breakdown",
            "",
            "| Track | Horses | Combo>=5 | Trainer>=10 |",
            "|---|---:|---:|---:|",
        ]
    )
    for track, counter in sorted(by_track.items(), key=lambda item: item[1]["horses"], reverse=True)[:15]:
        lines.append(
            f"| {track or 'unknown'} | {counter['horses']} | {pct(counter['combo_5'], counter['horses'])} | {pct(counter['trainer_10'], counter['horses'])} |"
        )

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {OUTPUT_MD}")


if __name__ == "__main__":
    main()
