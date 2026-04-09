import json

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

horseClient = nuxt.get('apollo', {}).get('horseClient', {})

# Find all competitors
competitors = [v for k, v in horseClient.items() if k.startswith("Competitor:")]
print(f"Total competitors: {len(competitors)}")

if competitors:
    c = competitors[0]
    
    # Let's resolve the animal
    animal_ref = c.get('animal', {}).get('__ref')
    animal = horseClient.get(animal_ref, {}) if animal_ref else {}
    
    name = animal.get('name', 'Unknown')
    
    print(f"Horse: {name}")
    print(f"Age/Sex/Colour: {c.get('age')}yo{c.get('sex')} {c.get('colour')}")
    
    # Career stats are probably in the competitor or animal
    print(f"Stats Keys on Competitor: {[k for k in c.keys() if 'stat' in k.lower() or 'career' in k.lower()]}")
    
    # Form guide past runs
    past_runs_refs = c.get('pastRuns', [])
    print(f"Past runs count: {len(past_runs_refs)}")
    
    if past_runs_refs:
        pr_ref = past_runs_refs[0].get('__ref')
        pr = horseClient.get(pr_ref, {})
        print("Past Run Keys:", list(pr.keys()))
        print(f"Track: {pr.get('track')}")
        print(f"Pos: {pr.get('position')}/{pr.get('starters')}")
        
    print("\n--- Animal Keys ---")
    print(list(animal.keys()))
    print("\n--- Competitor Keys ---")
    print(list(c.keys()))
