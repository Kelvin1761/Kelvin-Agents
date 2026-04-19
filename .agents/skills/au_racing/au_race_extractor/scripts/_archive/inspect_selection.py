import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

selections = nuxt.get('fetch', {}).get('FormGuidePrint:0', {}).get('selections', [])

if selections:
    sel = selections[0]
    print(f"Selection Keys: {list(sel.keys())}")
    
    print("\nSample Selection Data:")
    for k, v in list(sel.items())[:10]:
        print(f"  {k}: {v}")
        
    runs = sel.get('forms', [])
    if runs:
        print("\nSample Form Keys:")
        print(f"  Keys: {list(runs[0].keys())}")
        for k, v in list(runs[0].items())[:10]:
            print(f"    {k}: {v}")
