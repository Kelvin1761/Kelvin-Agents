import json

games = ['nba_game_data_MIA_TOR.json', 'nba_game_data_IND_BKN.json', 'nba_game_data_CHI_WSH.json']
for game_file in games:
    path = f"nba_analysis_20260410/{game_file}"
    try:
        data = json.load(open(path))
    except Exception as e:
        continue
    
    meta = data.get('meta', {})
    print(f"\n====================================")
    print(f"GAME: {meta.get('game')}")
    
    props_list = []
    players = data.get('players', {})
    if isinstance(players, dict):
        for team, players_list in players.items():
            if type(players_list) is not list: continue
            if team == 'MIA': continue
            for p_data in players_list:
                p_name = p_data.get('name')
                # basic filter: only pick players with PTS > 10 in some gamelog or something?
                for prop_name, prop_data in p_data.get('prop_analytics', {}).items():
                    lines = prop_data.get('bet365_lines', [])
                    if isinstance(lines, list):
                        for line_info in lines:
                            edge = line_info.get('edge', 0)
                            # Only want props where L10 Hit > 60% and Odds > 1.4 for overs, 
                            # or just decent edges
                            if edge > 0 and line_info.get('est_odds', 0) > 1.4:
                                props_list.append({
                                    'player': p_name,
                                    'team': team,
                                    'prop': prop_name,
                                    'line': f"{line_info.get('direction')} {line_info.get('line')}",
                                    'edge': edge,
                                    'odds': line_info.get('est_odds'),
                                    'l10': prop_data.get('l10_stats', {}).get('l10', []),
                                    'l10_hit': line_info.get('hit_rate_L10'),
                                    'adj_prob': line_info.get('estimated_prob'),
                                    'cov_grade': prop_data.get('cov_label', 'N/A')
                                })
    
    props_list.sort(key=lambda x: (x['l10_hit'], x['odds']), reverse=True)
    print(f"Top Filtered Props:")
    count = 0
    seen = set()
    for p in props_list:
        key = f"{p['player']}_{p['prop']}"
        if key in seen: continue
        seen.add(key)
        # only over 70% hit
        if p['l10_hit'] < 70: continue
        print(f"- {p['player']} ({p['team']}): {p['prop']} {p['line']} @ {p['odds']} | L10 Hit: {p['l10_hit']}% | Edge: {p['edge']:.1f}% | L10: {p['l10']} | COV: {p['cov_grade']}")
        count += 1
        if count >= 6: break
