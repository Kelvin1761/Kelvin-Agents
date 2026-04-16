import sys
import traceback
sys.path.append('backend')
from services.parser_au import parse_au_analysis

try:
    res = parse_au_analysis("../2026-04-02 Gosford Race 1-7/2026-04-02_Gosford_Race_7_Analysis.md")
    if res:
        print(f"Top Picks: {len(res.top_picks)}")
        print(f"Is Dual Track: {res.is_dual_track}")
        if res.scenario_top_picks:
            for k, v in res.scenario_top_picks.items():
                print(f"Scenario {k}: {len(v)} picks")
        else:
            print("Scenario Top Picks: None")
    else:
        print("Failed to parse.")
except Exception as e:
    print("EXCEPTION:")
    traceback.print_exc()
