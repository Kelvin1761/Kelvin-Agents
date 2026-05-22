import json
import sys
from pathlib import Path
from collections import defaultdict
import re

from au_archive_calibrator import load_historical_results, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_track, normalize_horse_name, ARCHIVE_ROOT

def detect_meeting_date(meeting_dir):
    match = re.search(r"202\d-\d{2}-\d{2}", meeting_dir.name)
    return match.group(0) if match else None

total_logic = 0
found_in_csv = 0
found_enough_horses = 0

hist = load_historical_results(HISTORICAL_RESULTS_CSV)

for meeting_dir in ARCHIVE_ROOT.iterdir():
    if not meeting_dir.is_dir(): continue
    for logic_path in meeting_dir.glob("Race_*_Logic.json"):
        total_logic += 1
        date = detect_meeting_date(meeting_dir)
        race_no = int(re.search(r"Race_(\d+)_Logic.json", logic_path.name).group(1))
        
        sample = json.loads(logic_path.read_text())
        track = detect_meeting_track(meeting_dir, sample)
        
        rows = choose_track_rows(hist.get((date, race_no), []), track)
        if rows:
            found_in_csv += 1
            
            lookup = {normalize_horse_name(r["horse_slug"]): r for r in rows}
            matched_horses = 0
            for h in sample.get("horses", {}).values():
                if normalize_horse_name(h.get("horse_name")) in lookup:
                    matched_horses += 1
            
            if matched_horses >= 4:
                found_enough_horses += 1

print(f"Total logic files: {total_logic}")
print(f"Races found in CSV: {found_in_csv}")
print(f"Races with >= 4 matched horses: {found_enough_horses}")
