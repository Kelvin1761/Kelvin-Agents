import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json

with open('./.agents/skills/au_race_extractor/scripts/sectionals_nuxt.json', 'r') as f:
    nuxt = json.load(f)

fetch_data = nuxt.get('fetch', {})
print(f"Fetch keys: {list(fetch_data.keys())}")

for k, v in fetch_data.items():
    print(f"\n--- {k} ---")
    if isinstance(v, dict):
        print(f"Keys: {list(v.keys())}")
        if 'selections' in v:
             print(f"selections len: {len(v['selections'])}")
             if len(v['selections']) > 0:
                 print(v['selections'][0].keys())

