"""
AU Wong Choi - Single Meeting Runner
For testing and ad-hoc runs of one specific meeting.
Usage:
    python3 au_run_single.py <slug> <date YYYY-MM-DD>
    python3 au_run_single.py sandown-lakeside 2026-05-31
"""

import os
import sys
import subprocess
import glob
import shutil

# Add the v2 module path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from au_season_batch_crawler_v2 import (
    process_meeting,
    SLUG_TO_DISPLAY,
    make_env,
    find_existing_folder,
    is_meeting_complete,
    move_orchestrator_output,
    ARCHIVE_DIR,
    REFLECTOR_PATH,
    RESULTS_SCRIPT_PATH,
    ORCHESTRATOR_PATH,
)
import datetime


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 au_run_single.py <slug> <YYYY-MM-DD>")
        print("Example: python3 au_run_single.py sandown-lakeside 2026-05-31")
        print("\nAvailable slugs:")
        for slug, display in SLUG_TO_DISPLAY.items():
            print(f"  {slug:25} -> {display}")
        sys.exit(1)

    slug = sys.argv[1].lower().strip()
    date_str = sys.argv[2]
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"❌ Invalid date format: {date_str} (use YYYY-MM-DD)")
        sys.exit(1)

    if slug not in SLUG_TO_DISPLAY:
        print(f"❌ Unknown slug: {slug}")
        print("\nAvailable slugs:")
        for s, d in SLUG_TO_DISPLAY.items():
            print(f"  {s:25} -> {d}")
        sys.exit(1)

    display = SLUG_TO_DISPLAY[slug]
    print(f"=" * 70)
    print(f"🎯 Single Meeting Runner: {display} on {date_obj}")
    print(f"=" * 70)

    process_meeting(slug, date_obj)
    print(f"\n✅ Done!")


if __name__ == "__main__":
    main()
