import json
import sys

def main():
    try:
        with open('nba_analysis_20260410/nba_game_data_MIA_TOR.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("JSON file not found.")
        return

    players = data.get('players', {}).get('TOR', [])
    targets = ['Immanuel Quickley', 'Jakob Poeltl', 'RJ Barrett', 'Scottie Barnes']
    
    for p in players:
        name = p.get('name')
        if name in targets:
            print(f"--- {name} ---")
            analytics = p.get('prop_analytics', {})
            for stat in ['PTS', 'REB', 'AST', 'FG3M']:
                stat_data = analytics.get(stat, {})
                if not stat_data: continue
                l10 = stat_data.get('raw', [])
                cov = stat_data.get('cov_label', '')
                print(f"  {stat}: L10 = {l10} | cov = {cov}")

if __name__ == '__main__':
    main()
