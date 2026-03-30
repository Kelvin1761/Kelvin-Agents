import json

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

apollo = nuxt.get('apollo', {}).get('horseClient', {})
selections = nuxt.get('fetch', {}).get('FormGuidePrint:0', {}).get('selections', [])

sel = selections[0] # Absolute power
c_id = sel.get('competitor', {}).get('id') if isinstance(sel.get('competitor'), dict) else str(sel.get('competitor', {}).get('__ref', '')).replace('Competitor:', '')
comp = apollo.get(f"Competitor:{c_id}", {})

print("--- Sire / Dam Refs ---")
print(f"Sire: {comp.get('sire')}")
print(f"Dam: {comp.get('dam')}")

print("\n--- Trainer / Jockey Refs ---")
print(f"Trainer on sel: {sel.get('trainer')}")
print(f"Jockey on sel: {sel.get('jockey')}")

print("\n--- Flucs ---")
# Flucs look like a list of dicts. How do we get the prices? Let's just grab the 'value' from each dict
flucs = sel.get('flucOdds', [])
if flucs:
     print(f"Raw Flucs type: {type(flucs[0])}")
     print([f.get('value') for f in flucs if isinstance(f, dict)])
     
print("\n--- Position summary ---")
runs = sel.get('forms', [])
pr = runs[2]
pos_refs = pr.get('competitorPositionSummary', [])
print(f"Pos refs: {pos_refs}")
if pos_refs:
     for pref in pos_refs:
          pid = pref.get('id')
          if pid:
               pdata = apollo.get(f"CompetitorPositionSummary:{pid}")
               print(pdata)
