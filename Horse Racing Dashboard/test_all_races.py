import sys
sys.path.append('backend')
from services.meeting_detector import discover_meetings, load_meeting_races

meetings = discover_meetings('..')
m = next(m for m in meetings if 'Gosford' in m.venue)
races = load_meeting_races(m).get('Kelvin', [])

for r in sorted(races, key=lambda x: x.race_number):
    print(f"Race {r.race_number}:")
    print(f"  Top Picks: {len(r.top_picks)}")
    print(f"  Alt Top Picks: {len(r.alt_top_picks) if r.alt_top_picks else 0}")
    if r.scenario_top_picks:
        for k, v in r.scenario_top_picks.items():
            print(f"  Scenario {k}: {len(v)} picks")
            
