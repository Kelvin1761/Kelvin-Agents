import json
import glob

for f in glob.glob('nba_analysis_20260410/nba_game_data_*.json'):
    try:
        with open(f, 'r') as file:
            data = json.load(file)
            print(f"{f}: {data.get('meta', {}).get('date')}")
    except:
        pass
