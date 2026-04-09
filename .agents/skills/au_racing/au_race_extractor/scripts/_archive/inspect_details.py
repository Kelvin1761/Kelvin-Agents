import json

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

apollo = nuxt.get('apollo', {}).get('horseClient', {})

# Let's inspect the selection for Absolute Power (Competitor:943628) 
# The selection object itself has stats at Selection:28421448
selections = nuxt.get('fetch', {}).get('FormGuidePrint:0', {}).get('selections', [])

if selections:
    sel = selections[0]
    print(f"Horse: {sel.get('name')}")
    
    # Check stats object
    stats = sel.get('stats', {})
    print("\n--- Stats keys ---")
    for k, v in list(stats.items())[:20]:
        print(f"{k}: {v}")
        
    print("\n--- Additional Stats in Apollo? ---")
    c_id = sel.get('competitor', {}).get('id') if isinstance(sel.get('competitor'), dict) else str(sel.get('competitor', {}).get('__ref', '')).replace('Competitor:', '')
    comp = apollo.get(f"Competitor:{c_id}", {})
    print(f"Competitor Keys: {list(comp.keys())}")
    
    # Let's check Trainer and Jockey LY stats
    trainer_ref = sel.get('trainer', {}).get('__ref', '')
    if trainer_ref:
        print(f"\nTrainer: {apollo.get(trainer_ref)}")
        
    # Sire / Dam info is usually on the animal object inside Competitor
    print(f"\nSireOfDam: {comp.get('sireOfDam')} ({comp.get('sireOfDamCountry')})")
    
    # Let's look at one past run detail
    runs = sel.get('forms', [])
    if runs:
        pr = runs[0]
        print("\n--- Past Run details ---")
        for k, v in list(pr.items())[:30]:
            print(f"{k}: {v}")
            
        print("\nMore past run details:")
        for k, v in list(pr.items())[30:70]:
            print(f"{k}: {v}")
