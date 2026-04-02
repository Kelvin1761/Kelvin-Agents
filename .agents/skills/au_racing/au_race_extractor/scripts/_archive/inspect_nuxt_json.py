import json

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    data = json.load(f)

# The Apollo cache usually holds the race data
# or data inside "data"
print("Data keys:", data.get("data", [{}])[0].keys())

if "apollo" in data:
    apollo_cache = data["apollo"]["defaultClient"]
    for k, v in list(apollo_cache.items())[:5]:
        print(f"Apollo KeY: {k}")
        
    # Find any key related to form guide
    for k, v in apollo_cache.items():
        if "PrintFormGuide" in k or "Meeting" in k or "Event" in k:
            print(f"Interesting Key: {k}")
