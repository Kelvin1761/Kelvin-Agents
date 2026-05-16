import os
import json
import re

found = set()
path = 'archive race analysis/hkjc results 2025 26'
for root, _, files in os.walk(path):
    for f in files:
        if f.endswith('.json'):
            print(f"Reading {f}...")
            with open(os.path.join(root, f), 'r', encoding='utf-8') as file:
                try:
                    data = json.load(file)
                    for r in data.values():
                        for h in r.get('results', []):
                            m = re.search(r'\(([A-Z]\d+)\)', h.get('horse_name', ''))
                            if m: found.add(m.group(1))
                except: pass
print(f"Total: {len(found)}")
