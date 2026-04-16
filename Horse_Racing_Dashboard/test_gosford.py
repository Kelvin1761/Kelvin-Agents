import sys
sys.path.append('backend')
from services.meeting_detector import discover_meetings, load_meeting_races

meetings = discover_meetings('..')
for m in meetings:
    if "Gosford" in m.venue:
        print(f"Meeting: {m.date} {m.venue}")
        races = load_meeting_races(m)
        for analyst, rs in races.items():
            print(f"  Analyst: {analyst}, found {len(rs)} races")
            for r in rs:
                print(f"    Race {r.race_number}: {len(r.horses)} horses, {len(r.top_picks)} top picks")
