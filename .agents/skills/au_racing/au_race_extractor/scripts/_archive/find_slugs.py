import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
import re

def find_race_slugs(data, results):
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and '-race-' in v and 'caulfield' not in v:
                results.add(v)
            else:
                find_race_slugs(v, results)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str) and '-race-' in item and 'caulfield' not in item:
                results.add(item)
            else:
                find_race_slugs(item, results)

with open('nuxt_overview.json', 'r') as f:
    data = json.load(f)

slugs = set()
find_race_slugs(data, slugs)
for s in sorted(slugs):
    if re.search(r'-race-\d+$', s):
        print(s)
