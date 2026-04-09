import json

def get_best_props(filename):
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    print("=== BEST OVER (Milestone) PROPS ===")
    for team, players in data.get('players', {}).items():
        if not isinstance(players, list): continue
        for p in players:
            name = p.get('name')
            analytics = p.get('prop_analytics', {})
            for stat in ['PTS', 'REB', 'AST', 'FG3M']:
                stat_data = analytics.get(stat, {})
                if not stat_data: continue
                l10_arr = stat_data.get('raw', [])
                lines = stat_data.get('bet365_lines', [])
                if not isinstance(lines, list): continue
                for line in lines:
                    if line.get('direction') == 'Over':
                        l10_hit = line.get('hit_rate_L10', 0)
                        edge = line.get('edge', 0)
                        odds = line.get('est_odds', 0)
                        if l10_hit >= 70 and odds >= 1.2:
                            print(f"{name} ({team}) - {stat} {line['line']} Over | L10 Hit: {l10_hit}% | Edge: {edge} | Odds: {odds} | L10: {l10_arr}")

if __name__ == '__main__':
    get_best_props('nba_analysis_20260410/nba_game_data_CHI_WSH.json')
