"""
AU Wong Choi - Tier 1/2 Season Gap Scanner (fast)
Finds meetings on Racenet that are missing from the archive.
Uses shorter delay and outputs JSON for resume.

Usage: python3 au_scan_season_gaps_fast.py [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--output gaps.json]
"""

import os
import sys
import json
import datetime
import time
import random
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "au_racing"))
from au_season_batch_crawler_v2 import TRACKS, SLUG_TO_DISPLAY, ARCHIVE_DIR
from racenet_transport import fetch_html, RacenetBlockedError


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start_date", default="2025-08-01")
    p.add_argument("--to", dest="end_date", default=datetime.date.today().strftime("%Y-%m-%d"))
    p.add_argument("--output", default="au_season_gaps.json")
    p.add_argument("--delay-min", type=float, default=0.6)
    p.add_argument("--delay-max", type=float, default=1.5)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--resume", action="store_true", help="Skip dates already in output file")
    p.add_argument("--tracks", nargs="*", help="Subset of tracks to check (default: all)")
    return p.parse_args()


def track_in_archive(slug, date_obj):
    date_dashed = date_obj.strftime("%Y-%m-%d")
    display = SLUG_TO_DISPLAY.get(slug, slug.title())
    display_first_word = display.split()[0].lower()
    slug_words = slug.replace("-", " ")
    try:
        for f in os.listdir(ARCHIVE_DIR):
            if not f.startswith(date_dashed):
                continue
            fn = f.lower()
            if slug_words in fn or display_first_word in fn:
                return True
        return False
    except Exception:
        return False


def check_track_on_date(slug, date_obj):
    date_compact = date_obj.strftime("%Y%m%d")
    url = f"https://www.racenet.com.au/results/horse-racing/{slug}-{date_compact}/all-races"
    try:
        html = fetch_html(url, context_label=f"Scan/{slug}")
        return slug in url and "race-card-empty" not in html.lower() and "no results" not in html.lower()
    except RacenetBlockedError:
        return False
    except Exception:
        return False


def scan_worker(slug, date_obj, delay_min, delay_max):
    time.sleep(random.uniform(delay_min, delay_max))
    return slug, date_obj, check_track_on_date(slug, date_obj)


def main():
    args = parse_args()
    start = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(args.end_date, "%Y-%m-%d").date()

    tracks = args.tracks if args.tracks else TRACKS

    print("=" * 70)
    print(f"🔍 AU Season Gap Scanner (FAST)")
    print(f"  Range: {start} to {end}  ({(end - start).days + 1} days)")
    print(f"  Tracks: {len(tracks)} venues")
    print(f"  Workers: {args.workers}, delay: {args.delay_min}-{args.delay_max}s")
    print(f"  Total checks: {((end - start).days + 1) * len(tracks)}")
    print(f"  Output: {args.output}")
    print("=" * 70)

    gaps = []
    done = set()
    if args.resume and os.path.exists(args.output):
        try:
            with open(args.output) as f:
                gaps = json.load(f)
            done = {(g["slug"], g["date"]) for g in gaps}
            print(f"  Resuming with {len(done)} already-done entries")
        except Exception as e:
            print(f"  Resume failed: {e}, starting fresh")

    days = []
    current = end
    while current >= start:
        days.append(current)
        current -= datetime.timedelta(days=1)

    total_checks = len(days) * len(tracks)
    checked = 0
    found_count = len(gaps)
    consecutive_fail = 0
    cooldown_until = 0

    for date_obj in days:
        date_str = date_obj.strftime("%Y-%m-%d")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {}
            for slug in tracks:
                if (slug, date_str) in done:
                    continue
                f = ex.submit(scan_worker, slug, date_obj, args.delay_min, args.delay_max)
                futures[f] = slug

            for fut in as_completed(futures):
                slug, d, exists = fut.result()
                checked += 1
                if exists:
                    found_count += 1
                    consecutive_fail = 0
                    in_archive = track_in_archive(slug, d)
                    entry = {
                        "slug": slug,
                        "display": SLUG_TO_DISPLAY.get(slug, slug),
                        "date": date_str,
                        "in_archive": in_archive,
                    }
                    gaps.append(entry)
                    status = "✅" if in_archive else "❌"
                    print(f"  [{date_str}] {SLUG_TO_DISPLAY.get(slug, slug):20} {status}")
                    with open(args.output, "w") as f:
                        json.dump(gaps, f, indent=2)
                else:
                    consecutive_fail += 1

        if checked % 100 == 0 and checked > 0:
            print(f"  ... {checked}/{total_checks} checks, {found_count} found")

        if consecutive_fail > 20:
            cooldown = 60
            print(f"  ⚠️ {consecutive_fail} consecutive misses, cooldown {cooldown}s")
            time.sleep(cooldown)
            consecutive_fail = 0

    missing = [g for g in gaps if not g["in_archive"]]
    print("=" * 70)
    print(f"✅ Scan complete: {checked} new checks, {len(gaps)} meetings found")
    print(f"   {len(missing)} missing from archive")
    print(f"   {len(gaps) - len(missing)} already in archive")
    print(f"   Saved to {args.output}")


if __name__ == "__main__":
    main()
