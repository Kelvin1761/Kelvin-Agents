import json

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

def recursive_find_competitors(d, depth=0):
    if depth > 10: return
    if isinstance(d, dict):
        if "animal" in d and "name" in d["animal"]:
             print(f"Found horse locally: {d['animal']['name']}")
             
        for k, v in d.items():
            if k == "competitors" and isinstance(v, list) and len(v) > 0:
                print(f"Found non-empty competitors list at depth {depth}")
            recursive_find_competitors(v, depth + 1)
    elif isinstance(d, list):
        for item in d:
             recursive_find_competitors(item, depth + 1)

recursive_find_competitors(nuxt)
print("Finished searching")
