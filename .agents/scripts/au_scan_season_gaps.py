"""
AU Wong Choi - Tier 1/2 Season Gap Scanner
Finds meetings on Racenet that are missing from the archive.
Outputs a list of (slug, date) tuples for the season batch crawler to process.

Usage: python3 au_scan_season_gaps.py [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--output gaps.json]
"""

import os
import sys
import json
import datetime
import time
import random
import argparse
from curl_cffi import requests

sys.path.insert(0, os.path.dirname(__file__))
from au_season_batch_crawler_v2 import TRACKS, SLUG_TO_DISPLAY, ARCHIVE_DIR


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start_date", default="2025-08-01")
    p.add_argument("--to", dest="end_date", default=datetime.date.today().strftime("%Y-%m-%d"))
    p.add_argument("--output", default="au_season_gaps.json")
    p.add_argument("--delay-min", type=float, default=2.0)
    p.add_argument("--delay-max", type=float, default=4.0)
    return p.parse_args()


def track_in_archive(slug, date_obj):
    """Check if a meeting is already in the archive (any level of completeness)."""
    date_dashed = date_obj.strftime("%Y-%m-%d")
    display = SLUG_TO_DISPLAY.get(slug, slug.title())
    for f in os.listdir(ARCHIVE_DIR):
        if f.startswith(date_dashed) and slug.replace("-", " ") in f.lower():
            return True
        if f.startswith(date_dashed) and display.split()[0].lower() in f.lower():
            return True
    return False


def check_track_on_date(slug, date_obj):
    date_compact = date_obj.strftime("%Y%m%d")
    url = f"https://www.racenet.com.au/results/horse-racing/{slug}-{date_compact}/all-races"
    try:
        r = requests.get(url, impersonate="chrome136", timeout=12)
        return r.status_code == 200 and slug in r.url
    except Exception:
        return False


def main():
    args = parse_args()
    start = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(args.end_date, "%Y-%m-%d").date()

    print("=" * 70)
    print(f"🔍 AU Season Gap Scanner")
    print(f"  Range: {start} to {end}  ({(end - start).days + 1} days)")
    print(f"  Tracks: {len(TRACKS)} tier 1/2 venues")
    print(f"  Total checks: {((end - start).days + 1) * len(TRACKS)}")
    print(f"  Delay between checks: {args.delay_min}-{args.delay_max}s")
    print(f"  Output: {args.output}")
    print("=" * 70)

    gaps = []
    total_checks = 0
    found_count = 0

    current = end
    while current >= start:
        for slug in TRACKS:
            total_checks += 1
            if total_checks % 50 == 0:
                print(f"  ... checked {total_checks}, found {found_count} gaps so far")
            try:
                if check_track_on_date(slug, current):
                    found_count += 1
                    in_archive = track_in_archive(slug, current)
                    gap_entry = {
                        "slug": slug,
                        "display": SLUG_TO_DISPLAY.get(slug, slug),
                        "date": current.strftime("%Y-%m-%d"),
                        "in_archive": in_archive,
                    }
                    gaps.append(gap_entry)
                    status = "✅ IN ARCHIVE" if in_archive else "❌ MISSING"
                    print(f"  [{current}] {SLUG_TO_DISPLAY.get(slug, slug):20} {status}")
            except Exception as e:
                pass
            time.sleep(random.uniform(args.delay_min, args.delay_max))
        current -= datetime.timedelta(days=1)

    missing = [g for g in gaps if not g["in_archive"]]
    print("=" * 70)
    print(f"✅ Scan complete: {total_checks} checks, {len(gaps)} meetings found")
    print(f"   {len(missing)} missing from archive")
    print(f"   {len(gaps) - len(missing)} already in archive")
    print("=" * 70)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"scanned_at": datetime.datetime.now().isoformat(), "all_found": gaps, "missing_only": missing}, f, ensure_ascii=False, indent=2)
    print(f"📝 Saved to {args.output}")


if __name__ == "__main__":
    main()
