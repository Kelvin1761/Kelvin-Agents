import json
try:
    with open('nba_analysis_20260410/sportsbet_latest.json', 'r') as f:
        data = json.load(f)
    pts = data.get("player_props", {}).get("Points", {})
    for p, lines in pts.items():
        print(f"{p}: {json.dumps(lines)}")
except Exception as e:
    print(e)
