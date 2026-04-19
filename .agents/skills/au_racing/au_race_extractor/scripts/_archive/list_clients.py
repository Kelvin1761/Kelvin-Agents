import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    text = f.read()

import ijson
f = open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'rb')
parser = ijson.parse(f)
for prefix, event, value in parser:
    if event == 'map_key' and value == 'apollo':
        print(f"Found apollo")
    elif prefix == 'apollo' and event == 'map_key':
        print(f"Apollo client: {value}")
