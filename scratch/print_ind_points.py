import json

with open("nba_analysis_20260410/sportsbet_latest.json", 'r') as f:
    data = json.load(f).get("player_props", {}).get("Points", {})

with open("nba_analysis_20260410/nba_game_data_IND_BKN.json", 'r') as f:
    l10_data = json.load(f)

# Build a fast mapping of L10 Hit Rates
hits = {}
for t, plist in l10_data.get('players', {}).items():
    if isinstance(plist, list):
        for p in plist:
            name = p.get('name')
            raw = p.get('prop_analytics', {}).get('PTS', {}).get('raw', [])
            hits[name] = raw

for player, details in data.items():
    if player in hits:
        lines = details.get("lines", {})
        raw = hits[player]
        print(f"\n{player} (L10: {raw}):")
        for k, v in lines.items():
            if isinstance(v, (int, float)):
                thr = int(k)
                hit_rate = (sum(1 for x in raw if x >= thr) / 10) * 100
                print(f"  {thr}+ PTS | Odds: {v} | Hit: {hit_rate}% | Edge: {hit_rate - (1/v)*100:.1f}")
