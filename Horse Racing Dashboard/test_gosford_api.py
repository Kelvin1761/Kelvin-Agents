import sys
sys.path.append('backend')
from services.meeting_detector import discover_meetings, load_meeting_races
import json

meetings = discover_meetings('..')
for m in meetings:
    if "Gosford" in m.venue:
        races = load_meeting_races(m)
        r4 = next((r for r in races.get('Kelvin', []) if r.race_number == 4), None)
        print("Race 4:", "Found" if r4 else "Not Found")
        if r4:
            print("Top picks:", len(r4.top_picks))
            
