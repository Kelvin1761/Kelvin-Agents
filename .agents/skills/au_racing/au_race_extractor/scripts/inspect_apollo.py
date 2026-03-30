import json

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

apollo = nuxt.get('apollo', {}).get('defaultClient', {})

print(f"Total entries in Apollo cache: {len(apollo)}")

horses = [v for k, v in apollo.items() if k.startswith("Competitor:")]
print(f"Found {len(horses)} competitors in apollo cache")

if horses:
    h = horses[0]
    print(f"Competitor ID: {h.get('id')}")
    print(f"Name: {h.get('animal', {}).get('name')}")
    
    animal_ref = h.get('animal')
    if animal_ref and isinstance(animal_ref, dict) and '__ref' in animal_ref:
        ref = animal_ref['__ref']
        animal = apollo.get(ref, {})
        print(f"Resolved Animal: {animal.get('name')}")
    
    # Check for past runs
    past_runs = [v for k, v in apollo.items() if k.startswith("PastRun:")]
    print(f"Found {len(past_runs)} total past runs in cache.")
    
    if past_runs:
         run = past_runs[0]
         # Resolve references
         pos = run.get('position')
         print(f"Sample run pos: {pos}")
         run_keys = list(run.keys())
         print(f"Run keys: {run_keys}")
