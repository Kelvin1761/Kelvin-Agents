import json

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
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
