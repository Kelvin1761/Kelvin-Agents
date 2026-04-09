import json

try:
    with open('nba_analysis_20260410/sportsbet_latest.json', 'r') as f:
        data = json.load(f)
except Exception as e:
    print(e)
    exit(1)

props = data.get("player_props", {})
targets = ["Tre Jones", "Bilal Coulibaly", "Bub Carrington", "Jalen Smith", "Guerschon Yabusele"]

for category, players in props.items():
    for player, details in players.items():
        if player in targets:
            lines = details.get("lines", {})
            print(f"{player} - {category}: {json.dumps(lines)}")
