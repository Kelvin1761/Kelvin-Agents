import os
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.meeting_detector import discover_meetings, load_meeting_races
meetings = discover_meetings()
for m in meetings:
    if m.venue == 'Gosford':
        races = load_meeting_races(m).get('Kelvin', [])
        for r in races:
            if r.race_number == 5:
                print("Race 5 scenario top picks:")
                for label, picks in r.scenario_top_picks.items():
                    print(f"  {label}: {[p.dict() for p in picks]}")
