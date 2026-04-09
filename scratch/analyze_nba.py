import json, sys, glob

games = ['nba_game_data_MIA_TOR.json', 'nba_game_data_IND_BKN.json', 'nba_game_data_CHI_WSH.json']
for game_file in games:
    path = f"nba_analysis_20260410/{game_file}"
    try:
        data = json.load(open(path))
    except Exception as e:
        print(f"Error loading {game_file}: {e}")
        continue
    
    meta = data.get('meta', {})
    print(f"\n====================================")
    print(f"GAME: {meta.get('game')} ({game_file})")
    print(f"Odds: {data.get('odds', {})}")
    
    props_list = []
    players = data.get('players', {})
    if isinstance(players, dict):
        for team, players_list in players.items():
            if type(players_list) is not list: continue
            if team == 'MIA': continue
            for p_data in players_list:
                p_name = p_data.get('name')
                for prop_name, prop_data in p_data.get('prop_analytics', {}).items():
                    lines = prop_data.get('bet365_lines', [])
                    if isinstance(lines, list):
                        for line_info in lines:
                            edge = line_info.get('edge', 0)
                            if edge > 0:
                                props_list.append({
                                    'player': p_name,
                                    'team': team,
                                    'prop': prop_name,
                                    'line': f"{line_info.get('direction')} {line_info.get('line')}",
                                    'edge': edge,
                                    'odds': line_info.get('est_odds'),
                                    'l10_hit': line_info.get('hit_rate_L10'),
                                    'adj_prob': line_info.get('estimated_prob'),
                                    'tier': line_info.get('tier', ''),
                                    'cov_grade': prop_data.get('cov_label', 'N/A')
                                })
    
    props_list.sort(key=lambda x: x['edge'], reverse=True)
    # Filter out redundant lines (keep best over and best under per player/prop if needed, but here just top 15)
    print(f"\nTop 15 Player Props by Edge (excluding MIA):")
    seen = set()
    count = 0
    for p in props_list:
        key = f"{p['player']}_{p['prop']}_{p['line']}"
        if key in seen: continue
        seen.add(key)
        tier_str = f" [{p['tier']}]" if p['tier'] else ""
        print(f"{p['player']} ({p['team']}): {p['prop']} {p['line']} @ {p['odds']} | Edge: {p['edge']:.2f}% | L10: {p['l10_hit']}% | Adj: {p['adj_prob']}% | COV: {p['cov_grade']}{tier_str}")
        count += 1
        if count >= 15: break
