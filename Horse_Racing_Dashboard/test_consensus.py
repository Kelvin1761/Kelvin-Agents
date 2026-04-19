import sys
sys.path.insert(0, 'backend')
from services.parser_hkjc import parse_hkjc_analysis
from services.consensus import find_consensus_horses

kelvin_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-19_ShaTin/04-19_ShaTin Race 6 Analysis.md"
heison_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-19_ShaTin (Heison)/04-19_ShaTin Race 6 Analysis.md"

k_race = parse_hkjc_analysis(kelvin_path)
h_race = parse_hkjc_analysis(heison_path)

print("Kelvin Top 4:")
if k_race and k_race.top_picks:
    for p in k_race.top_picks:
        print(f"  {p.rank}: {p.horse_number} {p.horse_name} ({p.grade})")
else:
    print("  None")

print("Heison Top 4:")
if h_race and h_race.top_picks:
    for p in h_race.top_picks:
        print(f"  {p.rank}: {p.horse_number} {p.horse_name} ({p.grade})")
else:
    print("  None")

if k_race and h_race:
    res = find_consensus_horses(k_race, h_race)
    print("\nConsensus Top 2:")
    for h in res['consensus_horses']:
        if h['is_top2_consensus']:
            print(f"  {h['horse_number']} {h['horse_name']}")
    print("\nConsensus Top 4 overlap:")
    for h in res['consensus_horses']:
        if not h['is_top2_consensus']:
            print(f"  {h['horse_number']} {h['horse_name']}")
