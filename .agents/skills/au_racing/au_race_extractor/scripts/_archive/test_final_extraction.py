import json

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

print("Let's look at FormGuidePrint:0")
form_data = nuxt.get('fetch', {}).get('FormGuidePrint:0', {})

print(f"Data keys: {form_data.keys()}")

selections = form_data.get('selections', [])
print(f"Found {len(selections)} selections (horses) in this race.")

if selections:
    sel = selections[0]
    print(f"\n--- Horse: {sel.get('competitorName')} ---")
    print(f"Number: {sel.get('competitorNumber')} | Barrier: {sel.get('barrier')}")
    print(f"Trainer: {sel.get('trainerName')} | Jockey: {sel.get('jockeyName')}")
    print(f"Weight: {sel.get('weight')} | Age: {sel.get('age')}")
    print(f"Win%: {sel.get('winPercentage')} | Place%: {sel.get('placePercentage')}")
    print(f"Status: {sel.get('statusAbv')}") # e.g. 'S' for scratched
    
    past_runs = sel.get('forms', [])
    print(f"\nPast Runs ({len(past_runs)}):")
    if past_runs:
        for pr in past_runs[:2]:
            print(f"  {pr.get('finishPosition')}/{pr.get('eventStarters')} | {pr.get('eventDistance')}m | {pr.get('meetingVenueName')} | {pr.get('videoComments')} | {pr.get('startingWinPriceString')}")
    
