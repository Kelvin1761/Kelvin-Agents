import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json

with open('./.agents/skills/au_race_extractor/scripts/sectionals_nuxt.json', 'r') as f:
    nuxt = json.load(f)

def search_keys(v, path=""):
    if isinstance(v, dict):
        for k, val in v.items():
            if 'sectional' in k.lower():
                print(f"Found related key: {k} at path: {path}")
            search_keys(val, path + f"['{k}']")
    elif isinstance(v, list):
        for i, item in enumerate(v):
            search_keys(item, path + f"[{i}]")

search_keys(nuxt)
