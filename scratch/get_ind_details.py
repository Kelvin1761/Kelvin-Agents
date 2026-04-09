import json

with open("nba_analysis_20260410/nba_game_data_IND_BKN.json", 'r') as f:
    data = json.load(f)

for p in data['players']['IND']:
    if p['name'] in ['Jarace Walker', 'Kobe Brown', 'Quenton Jackson']:
        print(f"--- {p['name']} ---")
        pts = p.get('prop_analytics', {}).get('PTS', {})
        print(f"L10: {pts.get('raw')}")
        print(f"CoV: {pts.get('cov_label')}")
        print(f"PTS stats: {pts.get('med')}")
