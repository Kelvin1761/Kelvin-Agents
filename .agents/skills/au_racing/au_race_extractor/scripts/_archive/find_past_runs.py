import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    text = f.read()

# Let's find "pastRuns" 
import ijson
def get_path_to_key():
    f = open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'rb')
    parser = ijson.parse(f)
    for prefix, event, value in parser:
        if event == 'map_key' and value == 'pastRuns':
            print(f"Found it! Path: {prefix}")
            break
            
get_path_to_key()
