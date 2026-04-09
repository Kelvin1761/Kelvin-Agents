import json

def search(d, path=""):
    if isinstance(d, dict):
        if "winnerName" in d or "secondName" in d:
             print(f"Found Run data at {path} -> Keys: {list(d.keys())[:5]}")
             # return to avoid flooding
             return True
        for k, v in d.items():
            if search(v, f"{path}['{k}']"): return True
    elif isinstance(d, list):
        for i, v in enumerate(d):
            if search(v, f"{path}[{i}]"): return True
    return False

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

search(nuxt)
