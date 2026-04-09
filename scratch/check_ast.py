import json

try:
    with open('nba_analysis_20260410/sportsbet_latest.json', 'r') as f:
        data = json.load(f)
except Exception as e:
    exit(1)

props = data.get("player_props", {})
for player, details in props.get("Assists", {}).items():
    print(f"{player} - AST: {details.get('lines', {})}")
