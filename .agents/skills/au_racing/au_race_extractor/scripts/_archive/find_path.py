import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json

def find_paths(d, target_key, current_path=""):
    if isinstance(d, dict):
        if target_key in d:
            print(f"Found key at: {current_path}")
        for k, v in d.items():
            find_paths(v, target_key, f"{current_path}['{k}']")
    elif isinstance(d, list):
        for i, item in enumerate(d):
            find_paths(item, target_key, f"{current_path}[{i}]")

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

find_paths(nuxt, "Competitor:943628")
