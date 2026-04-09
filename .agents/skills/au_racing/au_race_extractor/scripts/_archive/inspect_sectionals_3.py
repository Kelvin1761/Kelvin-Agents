import json

with open('./.agents/skills/au_race_extractor/scripts/sectionals_nuxt.json', 'r') as f:
    nuxt = json.load(f)

horse_client = nuxt.get('apollo', {}).get('horseClient', {})

def get_keys_starting_with(prefix):
    return [k for k in horse_client.keys() if k.startswith(prefix)]

print("Sample SelectionResult objects with sectionalTime:")
sr_keys = [k for k in horse_client.keys() if k.startswith('SelectionResult:') and 'sectionalTime' in horse_client[k]]
for k in sr_keys[:3]:
    print(f"\n--- {k} ---")
    print(json.dumps(horse_client[k]['sectionalTime'], indent=2))
    
    # Try to find corresponding $SelectionResult
    print(f"Deep linked sectionals for {k}:")
    deep_keys = get_keys_starting_with(f"${k}.sectionalTime")
    for dk in deep_keys:
        print(f"  {dk}: {horse_client[dk]}")

# Also let's check what a SelectionResult actually maps to
if sr_keys:
    print(f"\nWhat is {sr_keys[0]}?")
    print(horse_client[sr_keys[0]])
