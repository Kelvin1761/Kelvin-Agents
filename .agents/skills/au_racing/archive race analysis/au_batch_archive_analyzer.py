#!/usr/bin/env python3
"""
AU Batch Archive Analyzer
=========================
Discovers past race meetings from Racenet results listing,
filters by target venues (Tier 1 + Tier 2), and runs the full
AU Wong Choi pipeline race-by-race for each meeting.

Outputs to: archive race analysis/YYYY-MM-DD Venue Race 1-N/

Usage:
    python au_batch_archive_analyzer.py
    python au_batch_archive_analyzer.py --venues "rosehill,eagle farm"
    python au_batch_archive_analyzer.py --date-range 2026-04-01:2026-05-30
    python au_batch_archive_analyzer.py --max-meetings 5
    python au_batch_archive_analyzer.py --dry-run

Full Season Mode (slow, human-like, anti-blocking):
    python au_batch_archive_analyzer.py --mode full-season --dry-run
    python au_batch_archive_analyzer.py --mode full-season --max-meetings 5
    python au_batch_archive_analyzer.py --mode full-season
"""

from __future__ import annotations

import os
os.environ.setdefault("PYTHONUTF8", "1")
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import subprocess
import re
import io
import time
import random
from pathlib import Path
from datetime import datetime, timedelta

# ─── Path Setup ──────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
# archive race analysis/ → au_racing/ → skills/ → .agents/ → PROJECT_ROOT
PROJECT_ROOT = SCRIPT_DIR.parents[3]

# racenet_transport lives in au_racing/
AU_RACING_DIR = PROJECT_ROOT / ".agents" / "skills" / "au_racing"

# Output goes to: antigravity/Archive_Race_Analysis/AU_Racing/
AU_OUTPUT_DIR = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
OUTPUT_DIR = AU_OUTPUT_DIR  # For existing code that references OUTPUT_DIR
if not AU_OUTPUT_DIR.exists():
    AU_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Created output directory: {AU_OUTPUT_DIR}")
if str(AU_RACING_DIR) not in sys.path:
    sys.path.insert(0, str(AU_RACING_DIR))

from racenet_transport import RacenetBlockedError, fetch_nuxt_data

# claw_racenet_results for results extraction
try:
    from claw_racenet_results import (
        extract_meeting as results_extract_meeting,
        extract_events as results_extract_events,
        extract_race_results,
        format_markdown as results_format_markdown,
        format_reflector_results,
    )
except ImportError:
    # Fallback: load from same directory
    _claw_path = str(AU_RACING_DIR)
    if _claw_path not in sys.path:
        sys.path.insert(0, _claw_path)
    from claw_racenet_results import (
        extract_meeting as results_extract_meeting,
        extract_events as results_extract_events,
        extract_race_results,
        format_markdown as results_format_markdown,
        format_reflector_results,
    )

PYTHON = sys.executable
RESULTS_LISTING_URL = "https://www.racenet.com.au/results/horse-racing"

# ─── Venue Definitions ──────────────────────────────────────

# Venue slug patterns for URL construction (used in full-season mode)
VENUE_SLUG_MAP = {
    # Tier 1 — Metro
    "rosehill gardens": ["rosehill-gardens"],
    "rosehill": ["rosehill-gardens"],
    "randwick": ["randwick"],
    "flemington": ["flemington"],
    "caulfield": ["caulfield"],
    "caulfield heath": ["caulfield-heath", "caulfield"],
    "eagle farm": ["eagle-farm"],
    "doomben": ["doomben"],
    "moonee valley": ["moonee-valley"],
    # Tier 2 — Provincial
    "warwick farm": ["warwick-farm"],
    "canterbury": ["canterbury"],
    "pakenham": ["pakenham"],
    "gosford": ["gosford"],
    "newcastle": ["newcastle"],
    "geelong": ["geelong"],
    "cranbourne": ["cranbourne"],
}

# Racenet display names for each slug (for output folder naming)
VENUE_DISPLAY_NAMES = {
    "rosehill-gardens": "Rosehill Gardens",
    "randwick": "Randwick",
    "flemington": "Flemington",
    "caulfield": "Caulfield",
    "caulfield-heath": "Caulfield Heath",
    "eagle-farm": "Eagle Farm",
    "doomben": "Doomben",
    "moonee-valley": "Moonee Valley",
    "warwick-farm": "Warwick Farm",
    "canterbury": "Canterbury",
    "pakenham": "Pakenham",
    "gosford": "Gosford",
    "newcastle": "Newcastle",
    "geelong": "Geelong",
    "cranbourne": "Cranbourne",
}

TARGET_VENUES = [
    # Tier 1 — Metro
    "rosehill gardens", "rosehill",
    "randwick",
    "flemington",
    "caulfield", "caulfield heath",
    "eagle farm",
    "doomben",
    "moonee valley",
    # Tier 2 — Provincial
    "warwick farm",
    "canterbury",
    "pakenham",
    "gosford",
    "newcastle",
    "geelong",
    "cranbourne",
]

# All slug variants to probe in full-season mode
ALL_TARGET_SLUGS = []
for slug_list in VENUE_SLUG_MAP.values():
    ALL_TARGET_SLUGS.extend(slug_list)
ALL_TARGET_SLUGS = list(dict.fromkeys(ALL_TARGET_SLUGS))  # dedupe, preserve order

# ─── Anti-Blocking: Human-Like Delays ───────────────────────

# State file to track progress across runs (keep progress in same dir as script)
PROGRESS_FILE = SCRIPT_DIR / "batch_progress.json"

# Minimum seconds between Racenet requests
MIN_DELAY = 8
MAX_DELAY = 15

# Delay between meetings (longer pause)
MEETING_DELAY_MIN = 30
MEETING_DELAY_MAX = 60

# Block recovery wait time (seconds)
BLOCK_WAIT = 300  # 5 minutes

# Max consecutive blocks before stopping
MAX_CONSECUTIVE_BLOCKS = 3


def _update_delays(min_delay: float, max_delay: float):
    """Update the global delay settings."""
    global MIN_DELAY, MAX_DELAY
    MIN_DELAY = min_delay
    MAX_DELAY = max_delay


def _human_delay(label: str = "request", min_s: float = None, max_s: float = None):
    """Sleep for a random human-like interval."""
    if min_s is None:
        min_s = MIN_DELAY
    if max_s is None:
        max_s = MAX_DELAY
    delay = random.uniform(min_s, max_s)
    print(f"  ⏳ {label}: waiting {delay:.1f}s (human-like)...")
    time.sleep(delay)


def _meeting_delay():
    """Longer delay between meetings."""
    _human_delay("between meetings", MEETING_DELAY_MIN, MEETING_DELAY_MAX)


def _block_recovery_wait():
    """Wait after being blocked before retrying."""
    print(f"\n  🛑 Blocked! Waiting {BLOCK_WAIT}s before retry...")
    time.sleep(BLOCK_WAIT)


# ─── Progress Tracking ──────────────────────────────────────

def _load_progress() -> dict:
    """Load progress from JSON file."""
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"processed_slugs": [], "failed_slugs": [], "last_run": None}


def _save_progress(progress: dict):
    """Save progress to JSON file."""
    progress["last_run"] = datetime.now().isoformat()
    PROGRESS_FILE.write_text(
        json.dumps(progress, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ─── Results Listing Discovery ───────────────────────────────

def fetch_results_listing() -> dict:
    """Fetch the Racenet results listing and return raw NUXT data."""
    print(f"🔍 Fetching results listing: {RESULTS_LISTING_URL}")
    nuxt = fetch_nuxt_data(RESULTS_LISTING_URL, context_label="Results listing")
    print("✅ Results listing fetched")
    return nuxt


def extract_meetings_from_results(nuxt_data: dict) -> dict[int, dict]:
    """Extract meeting info from results page Apollo cache.

    Returns dict keyed by event_number with meeting metadata.
    """
    apollo = nuxt_data.get("apollo", {}).get("defaultClient",
             nuxt_data.get("apollo", {}).get("horseClient", {}))
    meetings = {}
    for key, val in apollo.items():
        if key.startswith("Meeting:") and isinstance(val, dict):
            slug = val.get("slug", "")
            name = val.get("name", "Unknown")
            date_local = val.get("meetingDateLocal", val.get("meetingDateUtc", ""))
            date_str = date_local[:10] if date_local else ""
            rail = val.get("railPosition", "Unknown")
            track_comments = val.get("trackComments", "")
            events_raw = val.get("events", [])
            events = {}
            for ev_ref in events_raw:
                ev_id = ev_ref.get("id") if isinstance(ev_ref, dict) else None
                if ev_id and ev_id in apollo:
                    ev = apollo[ev_id]
                    ev_num = ev.get("eventNumber")
                    if ev_num is not None:
                        events[ev_num] = {
                            "id": ev_id,
                            "slug": ev.get("slug", ""),
                            "name": ev.get("name", ""),
                            "distance": ev.get("distance", "?"),
                            "event_class": ev.get("eventClass", ""),
                            "prize": ev.get("racePrizeMoney", 0) or 0,
                            "starters": ev.get("starters", 0),
                        }
            meetings[id(val)] = {
                "name": name,
                "slug": slug,
                "date": date_str,
                "rail": rail,
                "track_comments": track_comments,
                "events": events,
            }
    return meetings


def extract_events_from_results(nuxt_data: dict) -> dict:
    """Extract events keyed by event_number from results page."""
    apollo = nuxt_data.get("apollo", {}).get("defaultClient",
             nuxt_data.get("apollo", {}).get("horseClient", {}))
    events = {}
    for key, val in apollo.items():
        if key.startswith("Event:") and not key.startswith("$") and isinstance(val, dict):
            ev_num = val.get("eventNumber")
            if ev_num is None:
                continue
            eid = val.get("id", key.split(":")[1])
            events[ev_num] = {
                "id": eid,
                "slug": val.get("slug", ""),
                "name": val.get("name", ""),
                "distance": val.get("distance", "?"),
                "event_class": val.get("eventClass", ""),
                "prize": ev.get("racePrizeMoney", 0) or 0,
                "starters": val.get("starters", 0),
            }
    return events


def _venue_match(venue_name: str, targets: list[str]) -> bool:
    """Check if a venue name matches any target venue."""
    lower = venue_name.lower()
    return any(t in lower for t in targets)


def _venue_folder_name(venue: str) -> str:
    """Clean venue name for folder naming."""
    # Remove common suffixes for cleaner folder names
    v = venue.strip()
    for suffix in [" Racecourse", " Race Club", " Park"]:
        if v.lower().endswith(suffix.lower()):
            v = v[: -len(suffix)]
    return v


# ─── Full Season: Date Range Generation ─────────────────────

def generate_season_dates(start: str, end: str) -> list[str]:
    """Generate all dates in the season range (YYYY-MM-DD format).
    
    Australian racing typically runs Wed-Sat but we probe all days
    to be thorough (some meetings happen on other days).
    """
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    dates = []
    current = start_dt
    while current <= end_dt:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def _probe_meeting_from_results(date_str: str, slug: str) -> dict | None:
    """Try to fetch a specific meeting's results page.
    
    Returns meeting dict if found, None if not available.
    Uses the results page URL pattern.
    """
    date_compact = date_str.replace("-", "")
    results_url = f"{RESULTS_LISTING_URL}/{slug}-{date_compact}/all-races"
    
    try:
        nuxt = fetch_nuxt_data(results_url, context_label=f"Probe {slug}-{date_compact}")
        apollo = nuxt.get("apollo", {}).get("defaultClient",
                 nuxt.get("apollo", {}).get("horseClient", {}))
        
        # Find meeting in Apollo
        for key, val in apollo.items():
            if key.startswith("Meeting:") and isinstance(val, dict):
                name = val.get("name", "Unknown")
                events_raw = val.get("events", [])
                event_count = len(events_raw)
                if event_count > 0:
                    return {
                        "name": name,
                        "slug": slug,
                        "date": date_str,
                        "rail": val.get("railPosition", "Unknown"),
                        "track_comments": val.get("trackComments", ""),
                        "events": {},  # Will be filled later
                        "event_count": event_count,
                        "results_url": results_url,
                    }
    except RacenetBlockedError:
        raise  # Propagate block to caller
    except Exception:
        pass  # Silently skip non-existent meetings
    
    return None


def discover_full_season_meetings(
    dates: list[str],
    venue_filter: list[str] | None = None,
    max_meetings: int | None = None,
) -> list[dict]:
    """Discover meetings by probing Racenet for each venue + date.
    
    This is slow and human-like — probes one URL at a time with delays.
    """
    if venue_filter is None:
        venue_filter = TARGET_VENUES
    
    # Build list of (date, slug) pairs to probe
    all_slugs = []
    for venue_name in venue_filter:
        slug_list = VENUE_SLUG_MAP.get(venue_name.lower(), [])
        all_slugs.extend(slug_list)
    all_slugs = list(dict.fromkeys(all_slugs))  # dedupe
    
    discovered = []
    consecutive_blocks = 0
    total_probed = 0
    
    print(f"\n🔍 Full-season discovery: {len(dates)} dates × {len(all_slugs)} slugs")
    print(f"   Estimated probes: {len(dates) * len(all_slugs)}")
    print(f"   Human-like delay: {MIN_DELAY}-{MAX_DELAY}s between requests")
    
    for date_str in dates:
        if max_meetings and len(discovered) >= max_meetings:
            print(f"\n✅ Reached max meetings limit ({max_meetings})")
            break
        
        for slug in all_slugs:
            if max_meetings and len(discovered) >= max_meetings:
                break
            
            date_compact = date_str.replace("-", "")
            probe_label = f"{slug}-{date_compact}"
            
            # Skip if already processed (check for existing folder)
            if _check_existing_folder(date_str, slug):
                print(f"  ⏭️  {probe_label} — already exists, skipping")
                continue
            
            total_probed += 1
            print(f"  🔎 [{total_probed}] Probing {probe_label}...", end=" ", flush=True)
            
            try:
                meeting = _probe_meeting_from_results(date_str, slug)
                if meeting:
                    print(f"✅ Found: {meeting['name']} ({meeting['event_count']} races)")
                    discovered.append(meeting)
                    consecutive_blocks = 0
                else:
                    print(f"—")
            except RacenetBlockedError:
                print(f"🚫 BLOCKED")
                consecutive_blocks += 1
                if consecutive_blocks >= MAX_CONSECUTIVE_BLOCKS:
                    print(f"\n🛑 {consecutive_blocks} consecutive blocks — stopping discovery")
                    _block_recovery_wait()
                    consecutive_blocks = 0
                    # Resume after wait
                    continue
                _block_recovery_wait()
                continue
            
            # Human-like delay between probes
            _human_delay("probe")
    
    print(f"\n📋 Discovery complete: {len(discovered)} meetings found from {total_probed} probes")
    return discovered


def _check_existing_folder(date_str: str, slug: str) -> bool:
    """Check if a meeting folder already exists with Logic files."""
    display_name = VENUE_DISPLAY_NAMES.get(slug, slug.replace("-", " ").title())
    # Check both the old SCRIPT_DIR location and the new AU_OUTPUT_DIR location
    search_dirs = [SCRIPT_DIR, AU_OUTPUT_DIR]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for child in search_dir.iterdir():
            if not child.is_dir():
                continue
            if child.name.startswith(date_str) and display_name.lower() in child.name.lower():
                logic_files = list(child.glob("Race_*_Logic.json"))
                if logic_files:
                    return True
    return False


# ─── Main Batch Processing ──────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AU Batch Archive Analyzer — discover + process past meetings"
    )
    parser.add_argument(
        "--mode", type=str, default="listing",
        choices=["listing", "full-season"],
        help="Discovery mode: 'listing' (results page) or 'full-season' (probe all dates)"
    )
    parser.add_argument(
        "--venues", type=str, default=None,
        help="Comma-separated venue filter (e.g. 'rosehill,eagle farm,warwick farm')"
    )
    parser.add_argument(
        "--date-range", type=str, default=None,
        help="Date range YYYY-MM-DD:YYYY-MM-DD"
    )
    parser.add_argument(
        "--max-meetings", type=int, default=None,
        help="Max meetings to process"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only list meetings, don't process"
    )
    parser.add_argument(
        "--resume", action="store_true", default=True,
        help="Skip meetings that already have output (default: True)"
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Re-process all meetings even if output exists"
    )
    parser.add_argument(
        "--skip-results", action="store_true",
        help="Skip results extraction (only do form-guide analysis)"
    )
    parser.add_argument(
        "--delay-min", type=float, default=MIN_DELAY,
        help=f"Min delay between requests (default: {MIN_DELAY}s)"
    )
    parser.add_argument(
        "--delay-max", type=float, default=MAX_DELAY,
        help=f"Max delay between requests (default: {MAX_DELAY}s)"
    )
    args = parser.parse_args()

    # Update delay settings via module-level vars
    _update_delays(args.delay_min, args.delay_max)

    venue_filter = None
    if args.venues:
        venue_filter = [v.strip().lower() for v in args.venues.split(",")]
    else:
        venue_filter = TARGET_VENUES

    date_start = date_end = None
    if args.date_range:
        parts = args.date_range.split(":")
        if len(parts) == 2:
            date_start = parts[0].strip()
            date_end = parts[1].strip()

    resume = args.resume and not args.no_resume

    # ─── Discovery Phase ─────────────────────────────────────
    if args.mode == "full-season":
        # Full season mode: probe all venue+date combinations
        if not date_start:
            date_start = "2025-08-01"
        if not date_end:
            date_end = datetime.now().strftime("%Y-%m-%d")
        
        dates = generate_season_dates(date_start, date_end)
        filtered = discover_full_season_meetings(
            dates, venue_filter, args.max_meetings
        )
    else:
        # Listing mode: fetch from results listing page
        try:
            results_nuxt = fetch_results_listing()
        except RacenetBlockedError as exc:
            print(f"\n❌ Cannot fetch results listing: {exc}")
            sys.exit(2)

        # Discover meetings from results page
        apollo = results_nuxt.get("apollo", {}).get("defaultClient",
                 results_nuxt.get("apollo", {}).get("horseClient", {}))

        # Collect all Event:* entries from Apollo cache
        all_events = {}
        for key, val in apollo.items():
            if key.startswith("Event:") and not key.startswith("$") and isinstance(val, dict):
                ev_num = val.get("eventNumber")
                if ev_num is not None:
                    all_events[val.get("id", key.split(":")[1])] = {
                        "eventNumber": ev_num,
                        "slug": val.get("slug", ""),
                        "name": val.get("name", ""),
                        "distance": val.get("distance", "?"),
                        "event_class": val.get("eventClass", ""),
                        "prize": val.get("racePrizeMoney", 0) or 0,
                        "starters": val.get("starters", 0),
                    }

        # Find all meetings and link their events from the Apollo cache
        all_meetings = []
        for key, val in apollo.items():
            if not key.startswith("Meeting:") or not isinstance(val, dict):
                continue
            slug = val.get("slug", "")
            name = val.get("name", "Unknown")
            date_local = val.get("meetingDateLocal", val.get("meetingDateUtc", ""))
            date_str = date_local[:10] if date_local else ""

            # Link events: try both __ref dict format and raw ID format
            meeting_event_ids = set()
            events_raw = val.get("events", [])
            for ev_ref in events_raw:
                if isinstance(ev_ref, dict):
                    eid = ev_ref.get("id") or ev_ref.get("__ref", "").replace("Event:", "")
                    if eid:
                        meeting_event_ids.add(eid)
                elif isinstance(ev_ref, str):
                    meeting_event_ids.add(ev_ref.replace("Event:", ""))

            events = {}
            for eid in meeting_event_ids:
                if eid in all_events:
                    ev = all_events[eid]
                    events[ev["eventNumber"]] = {
                        "id": eid,
                        "slug": ev["slug"],
                        "name": ev["name"],
                        "distance": ev["distance"],
                        "event_class": ev["event_class"],
                        "prize": ev["prize"],
                        "starters": ev["starters"],
                    }

            all_meetings.append({
                "name": name,
                "slug": slug,
                "date": date_str,
                "rail": val.get("railPosition", "Unknown"),
                "track_comments": val.get("trackComments", ""),
                "events": events,
            })

        # Filter by venue
        filtered = [m for m in all_meetings if _venue_match(m["name"], venue_filter)]

        # Filter by date range
        if date_start:
            filtered = [m for m in filtered if m["date"] >= date_start]
        if date_end:
            filtered = [m for m in filtered if m["date"] <= date_end]

        # Sort by date ascending (oldest first — process in chronological order)
        filtered.sort(key=lambda m: m["date"])

        if args.max_meetings:
            filtered = filtered[: args.max_meetings]

    # ─── Display Found Meetings ──────────────────────────────
    print(f"\n📋 Found {len(filtered)} target meetings")
    for m in filtered:
        event_count = len(m.get("events", {}))
        races_str = f"({event_count} races)" if event_count else "(races TBD)"
        print(f"  📅 {m['date']} — {m['name']} {races_str}")

    if args.dry_run:
        print("\n🔍 Dry run — no processing done")
        # Save discovered meetings for reference
        summary_path = SCRIPT_DIR / "discovered_meetings.json"
        summary_path.write_text(
            json.dumps(filtered, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"📄 Discovered meetings saved: {summary_path}")
        return

    if not filtered:
        print("\n⚠️ No meetings to process")
        return

    # ─── Process each meeting ───────────────────────────────
    progress = _load_progress()
    processed = []
    consecutive_blocks = 0

    for idx, meeting in enumerate(filtered, 1):
        slug = meeting["slug"]
        date_str = meeting["date"]
        venue = meeting["name"]
        event_count = len(meeting.get("events", {}))

        # Skip if already processed in a previous run
        progress_key = f"{date_str}_{slug}"
        if resume and progress_key in progress.get("processed_slugs", []):
            print(f"\n  ⏭️  [{idx}/{len(filtered)}] {date_str} — {venue} — already in progress log, skipping")
            continue

        print(f"\n{'='*68}")
        print(f"🏇 [{idx}/{len(filtered)}] {date_str} — {venue} ({event_count} races)")
        print(f"{'='*68}")

        # Build form-guide overview URL from meeting slug
        date_compact = date_str.replace("-", "")
        fg_overview_url = (
            f"https://www.racenet.com.au/form-guide/horse-racing/{slug}-{date_compact}/overview"
        )

        # Create output directory
        venue_clean = _venue_folder_name(venue)
        # Use event_count from discovery (full-season mode) or events dict (listing mode)
        effective_count = event_count or meeting.get("event_count", 0)
        if effective_count:
            race_range = f"1-{effective_count}"
        else:
            race_range = "1-N"
        output_dir_name = f"{date_str} {venue_clean} Race {race_range}"
        output_dir = AU_OUTPUT_DIR / output_dir_name

        if resume and output_dir.exists():
            existing = list(output_dir.glob("Race_*_Logic.json"))
            if existing:
                print(f"  ⏭️  Already processed ({len(existing)} logic files) — skipping")
                progress["processed_slugs"].append(progress_key)
                _save_progress(progress)
                continue

        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ── Step 1: Extract form-guide data (race-by-race) ──
            print(f"  📥 Step 1: Extracting form-guide data...")
            _human_delay("before form-guide fetch")
            
            extractor_script = (
                PROJECT_ROOT / ".agents" / "skills" / "au_racing"
                / "au_race_extractor" / "scripts" / "extractor.py"
            )
            try:
                # Run extractor from AU_OUTPUT_DIR so it creates dirs at the correct level
                rc = _run_subprocess(
                    [PYTHON, str(extractor_script), fg_overview_url, "all"],
                    cwd=str(AU_OUTPUT_DIR),
                )
                if rc != 0:
                    raise SystemExit(rc)
                print(f"  ✅ Form-guide extraction complete")
                consecutive_blocks = 0
                
                # Detect actual output directory created by extractor
                # (extractor creates its own dir based on actual race count)
                actual_output = _detect_extractor_output(date_str, venue_clean, output_dir)
                if actual_output and actual_output != output_dir:
                    print(f"  📁 Extractor created: {actual_output.name}")
                    # Move files from subdirectory to correct output_dir if needed
                    _move_extracted_files(actual_output, output_dir)
            except RacenetBlockedError as exc:
                print(f"  ❌ Form-guide extraction blocked: {exc}")
                consecutive_blocks += 1
                if consecutive_blocks >= MAX_CONSECUTIVE_BLOCKS:
                    print(f"\n🛑 {consecutive_blocks} consecutive blocks — stopping")
                    _block_recovery_wait()
                    consecutive_blocks = 0
                _restore_cwd_if_needed()
                continue
            except SystemExit as exc:
                print(f"  ❌ Form-guide extraction failed (exit {exc.code})")
                _restore_cwd_if_needed()
                continue
            except Exception as exc:
                print(f"  ❌ Form-guide extraction error: {exc}")
                _restore_cwd_if_needed()
                continue

            # ── Step 2: Generate Facts (per race) ───────────────
            print(f"  📊 Step 2: Generating Facts...")
            facts_injector = PROJECT_ROOT / ".agents" / "scripts" / "inject_fact_anchors.py"
            racecards = sorted(output_dir.glob("*Racecard.md"))
            formguides = sorted(output_dir.glob("*Formguide.md"))

            for racecard in racecards:
                race_num = _race_num_from_name(racecard.name)
                if race_num is None:
                    continue
                formguide = _matching_file(formguides, race_num)
                if not formguide:
                    print(f"    ⚠️ No formguide for Race {race_num} — skipping facts")
                    continue
                facts_candidates = sorted(output_dir.glob(f"*Race {race_num} Facts.md"))
                if facts_candidates and not _is_stale(facts_candidates[0], racecard, formguide):
                    continue  # Facts already up-to-date
                print(f"    🧩 Race {race_num}: Generating Facts...")
                distance = _extract_distance(racecard, formguide)
                cmd = [
                    PYTHON, str(facts_injector),
                    str(racecard), str(formguide),
                    "--max-display", "5",
                    "--venue", venue,
                ]
                if distance:
                    cmd.extend(["--distance", str(distance)])
                _run_subprocess(cmd)

            # ── Step 3: Build Logic (per race) ──────────────────
            print(f"  🧠 Step 3: Building Logic...")
            logic_builder = (
                PROJECT_ROOT / ".agents" / "skills" / "au_racing"
                / "au_wong_choi_auto" / "scripts" / "build_au_logic.py"
            )
            facts_files = sorted(output_dir.glob("*Facts.md"),
                                 key=lambda p: (_race_num_from_name(p.name) or 999))
            for facts in facts_files:
                race_num = _race_num_from_name(facts.name)
                if race_num is None:
                    continue
                logic_path = output_dir / f"Race_{race_num}_Logic.json"
                if (logic_path.exists()
                        and not _is_stale(logic_path, facts)
                        and _logic_has_horses(logic_path)):
                    continue
                print(f"    🧠 Race {race_num}: Building Logic...")
                _run_subprocess([
                    PYTHON, str(logic_builder),
                    str(facts), "--output", str(logic_path),
                ])

            # ── Step 4: Auto Score & Analysis (per race) ────────
            print(f"  🏆 Step 4: Auto scoring & analysis...")
            auto_orch = (
                PROJECT_ROOT / ".agents" / "skills" / "au_racing"
                / "au_wong_choi_auto" / "scripts" / "au_auto_orchestrator.py"
            )
            _run_subprocess([PYTHON, str(auto_orch), str(output_dir)])

            # ── Step 5: Extract Results ─────────────────────────
            if not args.skip_results:
                print(f"  📋 Step 5: Extracting race results...")
                _human_delay("before results fetch")
                
                try:
                    results_data = fetch_nuxt_data(
                        f"{RESULTS_LISTING_URL}/{slug}-{date_compact}/all-races",
                        context_label="Race results",
                    )
                    r_apollo = results_data.get("apollo", {}).get("defaultClient",
                               results_data.get("apollo", {}).get("horseClient", {}))

                    r_meeting = results_extract_meeting(r_apollo)
                    r_events = results_extract_events(r_apollo)
                    all_results = {}
                    for rnum, rev in sorted(r_events.items()):
                        rsel = {
                            "selections_refs": rev.get("selections_refs", []),
                        }
                        rs = extract_race_results(r_apollo, rsel)
                        all_results[rnum] = rs
                        active = [r for r in rs if not r.get("is_scratched")]
                        winner = (f"#{active[0]['competitor_number']} {active[0]['horse_name']}"
                                  if active else "N/A")
                        print(f"    🏁 Race {rnum}: {len(active)} runners | Winner: {winner}")

                    venue_slug = r_meeting.get("name", venue).replace(" ", "_")
                    results_md = results_format_markdown(r_meeting, r_events, all_results)
                    results_path = output_dir / f"Race_Results_{venue_slug}_{date_str}.md"
                    results_path.write_text(results_md, encoding="utf-8")
                    print(f"    ✅ Results saved: {results_path.name}")

                    refl_md = format_reflector_results(r_meeting, r_events, all_results)
                    refl_path = output_dir / "Race_Results_Reflector.md"
                    refl_path.write_text(refl_md, encoding="utf-8")
                    print(f"    ✅ Reflector results saved")

                    json_path = output_dir / f"Race_Results_{venue_slug}_{date_str}.json"
                    json_data = {
                        "meeting": r_meeting,
                        "events": {str(k): v for k, v in r_events.items()},
                        "results": {str(k): v for k, v in all_results.items()},
                    }
                    for ev in json_data["events"].values():
                        ev.pop("selections_refs", None)
                    json_path.write_text(
                        json.dumps(json_data, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
                    print(f"    ✅ JSON results saved")

                except RacenetBlockedError as exc:
                    print(f"    ⚠️ Results extraction blocked: {exc}")
                except Exception as exc:
                    print(f"    ⚠️ Results extraction error: {exc}")

            # ── Summary ─────────────────────────────────────────
            analysis_files = list(output_dir.glob("Race_*_Auto_Analysis.md"))
            scoring_files = list(output_dir.glob("Race_*_Auto_Scoring.csv"))
            logic_files = list(output_dir.glob("Race_*_Logic.json"))
            print(f"\n  📁 Output: {output_dir}")
            print(f"     Logic: {len(logic_files)} | Analysis: {len(analysis_files)} | Scoring: {len(scoring_files)}")

            processed.append({
                "date": date_str,
                "venue": venue,
                "slug": slug,
                "races": event_count,
                "output_dir": str(output_dir),
            })

            # Update progress
            progress["processed_slugs"].append(progress_key)
            _save_progress(progress)

        except KeyboardInterrupt:
            print("\n⛔ Interrupted by user — saving progress...")
            _save_progress(progress)
            sys.exit(130)
        except Exception as exc:
            print(f"\n❌ Unexpected error processing {date_str} {venue}: {exc}")
            import traceback
            traceback.print_exc()
            _save_progress(progress)

        # Delay between meetings (human-like)
        if idx < len(filtered):
            _meeting_delay()

    # ─── Final Summary ──────────────────────────────────────
    print(f"\n{'='*68}")
    print(f"✅ Batch processing complete — {len(processed)} meetings processed")
    print(f"{'='*68}")

    if processed:
        summary_path = SCRIPT_DIR / "batch_processing_summary.json"
        summary_path.write_text(
            json.dumps(processed, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"📄 Summary: {summary_path}")

    return 0


# ─── Helpers ─────────────────────────────────────────────────

def _restore_cwd_if_needed():
    """Safely restore CWD if it was changed."""
    try:
        os.chdir(str(SCRIPT_DIR))
    except OSError:
        pass


def _run_subprocess(cmd: list[str], cwd: str | None = None) -> int:
    """Run a subprocess and return its exit code."""
    result = subprocess.run(cmd, cwd=cwd or str(PROJECT_ROOT), text=True)
    return result.returncode


def _race_num_from_name(name: str) -> int | None:
    """Extract race number from filename like '05-24 Race 3 Racecard.md'."""
    match = re.search(r"Race[ _](\d+)", name)
    return int(match.group(1)) if match else None


def _matching_file(files: list[Path], race_num: int) -> Path | None:
    """Find file matching a race number."""
    for path in files:
        if _race_num_from_name(path.name) == race_num:
            return path
    return None


def _is_stale(output: Path, *sources: Path) -> bool:
    """Check if output is older than any source file."""
    if not output.exists():
        return True
    out_mtime = output.stat().st_mtime_ns
    return any(s.exists() and s.stat().st_mtime_ns > out_mtime for s in sources)


def _logic_has_horses(logic_path: Path) -> bool:
    """Check if Logic JSON has horse data."""
    try:
        data = json.loads(logic_path.read_text(encoding="utf-8"))
        horses = data.get("horses")
        return isinstance(horses, dict) and bool(horses)
    except (json.JSONDecodeError, OSError):
        return False


def _move_extracted_files(src_dir: Path, dest_dir: Path):
    """Move ALL files from extractor subdirectory to parent."""
    import shutil
    moved = 0
    for child in src_dir.iterdir():
        if child.is_file():
            # Move all output files: md, csv, json
            if any(child.name.endswith(ext) for ext in 
                   (".md", ".csv", ".json")) and not dest_dir.name.startswith("Race_Results"):
                dest = dest_dir / child.name
                if not dest.exists():
                    shutil.move(str(child), str(dest))
                    moved += 1
    if moved:
        print(f"    📦 Moved {moved} files to {dest_dir.name}")
    # Remove empty subdirectory
    try:
        remaining = list(src_dir.iterdir())
        if not remaining:
            src_dir.rmdir()
    except OSError:
        pass


def _detect_extractor_output(date_str: str, venue_clean: str, expected_dir: Path) -> Path | None:
    """Detect the actual output directory created by the extractor.
    
    The extractor creates its own directory based on actual race count,
    which may differ from what the batch analyzer expects.
    The extractor may create a subdirectory inside expected_dir or in AU_OUTPUT_DIR.
    This function searches all likely locations.
    """
    # Search locations: expected_dir, subdirs of expected_dir, AU_OUTPUT_DIR
    search_items = []
    
    # Add expected_dir and its subdirectories
    if expected_dir.exists():
        search_items.append(expected_dir)
        for child in expected_dir.iterdir():
            if child.is_dir():
                search_items.append(child)
    
    # Add matching dirs from AU_OUTPUT_DIR
    if AU_OUTPUT_DIR.exists():
        for child in AU_OUTPUT_DIR.iterdir():
            if child.is_dir() and child.name.startswith(date_str) and venue_clean.lower() in child.name.lower():
                if child not in search_items:
                    search_items.append(child)
                # Also check subdirs
                for sub in child.iterdir():
                    if sub.is_dir() and sub not in search_items:
                        search_items.append(sub)
    
    # Add matching dirs from SCRIPT_DIR (old location)
    if SCRIPT_DIR.exists():
        for child in SCRIPT_DIR.iterdir():
            if child.is_dir() and child.name.startswith(date_str) and venue_clean.lower() in child.name.lower():
                if child not in search_items:
                    search_items.append(child)
    
    for search_dir in search_items:
        if not search_dir or not search_dir.exists():
            continue
        has_racecard = any(search_dir.glob("*Racecard.md"))
        has_formguide = any(search_dir.glob("*Formguide.md"))
        if has_racecard or has_formguide:
            return search_dir
    
    return None


def _extract_distance(racecard: Path, formguide: Path | None) -> int | None:
    """Extract race distance from racecard or formguide header."""
    for path in (racecard, formguide):
        if not path or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in (
            r"^RACE\s+\d+\s*[—–-]\s*(\d{3,5})m",
            r"^\s*RACE\s+\d+\s*\|?\s*(\d{3,5})m",
            r"^\s*RACE\s+\d+\s*\n.*?(\d{3,5})m",
            r"\b(\d{3,5})m\s*\|",
        ):
            match = re.search(pattern, text, re.M | re.S)
            if match:
                return int(match.group(1))
    return None


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("\n⛔ Interrupted by user")
        sys.exit(130)
    finally:
        _restore_cwd_if_needed()