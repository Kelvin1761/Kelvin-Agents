import json

games = [
    'nba_analysis_20260410/nba_game_data_IND_BKN.json',
    'nba_analysis_20260410/nba_game_data_BOS_NY.json',
    'nba_analysis_20260410/nba_game_data_PHI_HOU.json',
    'nba_analysis_20260410/nba_game_data_LAL_GS.json'
]

for g in games:
    print(f"\n--- {g} ---")
    try:
        with open(g, 'r') as f:
            data = json.load(f)
    except: continue

    for team, players in data.get('players', {}).items():
        if not isinstance(players, list): continue
        for p in players:
            name = p.get('name')
            analytics = p.get('prop_analytics', {})
            for stat in ['PTS', 'REB', 'AST', 'FG3M']:
                stat_data = analytics.get(stat, {})
                if not stat_data: continue
                lines = stat_data.get('bet365_lines', [])
                if not isinstance(lines, list): continue
                for line in lines:
                    if line.get('direction') == 'Over':
                        l10_hit = line.get('hit_rate_L10', 0)
                        edge = line.get('edge', 0)
                        odds = line.get('est_odds', 0)
                        if l10_hit >= 70 and edge >= 15:
                            print(f"{name} ({team}) - {stat} {line['line']} Over | L10 Hit: {l10_hit}% | Edge: {edge} | Odds: {odds} | L10: {stat_data.get('raw')}")
