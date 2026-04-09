import json

games = ["IND_BKN", "BOS_NY", "PHI_HOU", "LAL_GS"]
sportsbet_file = "nba_analysis_20260410/sportsbet_latest.json"

with open(sportsbet_file, 'r') as f:
    sb_data = json.load(f).get("player_props", {})

for game in games:
    print(f"\n======== {game} ========")
    l10_file = f"nba_analysis_20260410/nba_game_data_{game}.json"
    with open(l10_file, 'r') as f:
        l10_data = json.load(f)
        
    for team, p_list in l10_data.get('players', {}).items():
        if isinstance(p_list, list):
            for p in p_list:
                name = p.get("name")
                for stat, stat_name in [("PTS", "Points")]:
                    sb_lines = sb_data.get(stat_name, {}).get(name, {}).get("lines", {})
                    l10_raw = p.get("prop_analytics", {}).get(stat, {}).get("raw", [])
                    if sb_lines and l10_raw:
                        for line, odds in sb_lines.items():
                            if isinstance(odds, (int, float)) and odds >= 1.25:
                                threshold = int(line)
                                hit_rate = (sum(1 for val in l10_raw if val >= threshold) / len(l10_raw)) * 100
                                edge = hit_rate - ((1/odds)*100)
                                if hit_rate >= 60 and edge > -10:
                                    print(f"[{team}] {name}: {threshold}+ PTS | Odds: {odds} | Hit: {hit_rate}% | Edge: {edge:.1f}%")
