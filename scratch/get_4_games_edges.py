import json

games = ["IND_BKN", "BOS_NY", "PHI_HOU", "LAL_GS"]
sportsbet_file = "nba_analysis_20260410/sportsbet_latest.json"

try:
    with open(sportsbet_file, 'r') as f:
        sb_data = json.load(f).get("player_props", {})
except Exception as e:
    exit(1)

for game in games:
    print(f"\n======== {game} ========")
    l10_file = f"nba_analysis_20260410/nba_game_data_{game}.json"
    try:
        with open(l10_file, 'r') as f:
            l10_data = json.load(f)
    except:
        print("l10 data not found")
        continue
    
    players = []
    for team, p_list in l10_data.get('players', {}).items():
        if isinstance(p_list, list):
            for p in p_list:
                players.append((team, p))
            
    for team, p in players:
        name = p.get("name")
        analytics = p.get("prop_analytics", {})
        
        for stat, stat_name in [("PTS", "Points"), ("REB", "Rebounds"), ("AST", "Assists"), ("FG3M", "Threes Made")]:
            sb_lines = sb_data.get(stat_name, {}).get(name, {}).get("lines", {})
            if not sb_lines: continue
            
            l10_raw = analytics.get(stat, {}).get("raw", [])
            if not l10_raw: continue
            
            for line, odds in sb_lines.items():
                if not isinstance(odds, (int, float)): continue
                if odds < 1.15: continue  # skip completely unbettable
                
                threshold = int(line)
                hit_count = sum(1 for val in l10_raw if val >= threshold)
                hit_rate = (hit_count / len(l10_raw)) * 100 if l10_raw else 0
                
                implied_prob = (1 / odds) * 100
                edge = hit_rate - implied_prob
                
                if hit_rate >= 70 and edge > 5:
                    print(f"[{team}] {name}: {threshold}+ {stat} | Odds: {odds} | L10: {hit_count}/10 ({hit_rate}%) | Edge: {edge:.1f}%")

