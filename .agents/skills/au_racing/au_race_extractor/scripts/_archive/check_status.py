import json

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

selections = nuxt.get('fetch', {}).get('FormGuidePrint:0', {}).get('selections', [])
for sel in selections:
    name = sel.get('name', 'Unknown')
    # Try finding the name dynamically if we can't
    c_id = sel.get('competitor', {}).get('id') if isinstance(sel.get('competitor'), dict) else str(sel.get('competitor', {}).get('__ref', '')).replace('Competitor:', '')
    apollo = nuxt.get('apollo', {}).get('horseClient', {})
    if name == 'Unknown':
         name = apollo.get(f"Competitor:{c_id}", {}).get('name', 'Unknown')
         
    status = sel.get('status')
    statusAbv = sel.get('statusAbv')
    print(f"Horse: {name} | status: {status} | statusAbv: {statusAbv}")
