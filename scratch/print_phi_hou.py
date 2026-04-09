import json

with open("nba_analysis_20260410/sportsbet_latest.json", 'r') as f:
    sb_data = json.load(f).get("player_props", {}).get("Points", {})

with open("nba_analysis_20260410/nba_game_data_PHI_HOU.json", 'r') as f:
    l10_data = json.load(f)

for t, plist in l10_data.get('players', {}).items():
    if isinstance(plist, list):
        for p in plist:
            name = p.get('name')
            raw = p.get('prop_analytics', {}).get('PTS', {}).get('raw', [])
            cov = p.get('prop_analytics', {}).get('PTS', {}).get('cov_label', '')
            if name in sb_data:
                print(f"\n{name} (L10: {raw}, CoV: {cov}):")
                for k, v in sb_data[name].get("lines", {}).items():
                    if isinstance(v, (int, float)):
                        thr = int(k)
                        hit_rate = (sum(1 for x in raw if x >= thr) / 10) * 100
                        print(f"  {thr}+ PTS | Odds: {v} | Hit: {hit_rate}%")
