import json

with open("nba_analysis_20260410/sportsbet_latest.json", 'r') as f:
    data = json.load(f)

print("Categories present in sportsbet_latest:")
for cat_name, cat_data in data.get("player_props", {}).items():
    players_count = len(cat_data.keys())
    print(f" - {cat_name}: {players_count} players")

print("\nRaw keys in sportsbet JSON:")
print(data.keys())
