import json

with open('./.agents/skills/au_race_extractor/scripts/sectionals_nuxt.json', 'r') as f:
    nuxt = json.load(f)

print("Searching for 'sectional' keys in the sectionals JSON...")

def search_keys(v, path=""):
    if isinstance(v, dict):
        for k, val in v.items():
            if 'sectional' in k.lower() or 'time' in k.lower():
                print(f"Found related key: {k} at path: {path}")
                # Don't recurse into it fully just print type
                if isinstance(val, list) and len(val) > 0:
                     print(f"  -> List of {type(val[0])} of length {len(val)}")
                elif isinstance(val, dict):
                     print(f"  -> Dict with keys {list(val.keys())}")
            search_keys(val, path + f"['{k}']")
    elif isinstance(v, list):
        for i, item in enumerate(v):
            search_keys(item, path + f"[{i}]")

# Let's just look at the highest level apollo cache objects
apollo = nuxt.get('apollo', {})
for k in apollo.keys():
    print(f"Apollo client: {k}")

horse_client = apollo.get('horseClient', {})
for k, v in list(horse_client.items())[:5]:
    print(f"Key in horseClient: {k}")
    
# Specifically, we know the main data is often in fetch or state
fetch = nuxt.get('fetch', {})
print(f"Fetch keys: {list(fetch.keys())}")

if 'Sectionals:0' in fetch:
     print("Found Sectionals:0 in fetch")
     sect = fetch['Sectionals:0']
     print(f"Keys: {list(sect.keys())}")
     
     selections = sect.get('competitors', []) or sect.get('selections', [])
     print(f"Has selections/competitors? len={len(selections)}")
     if len(selections) > 0:
          print(f"Sample selection keys: {list(selections[0].keys())}")
