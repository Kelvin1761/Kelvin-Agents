import json

with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

# The Apollo cache usually stores all the complex entities
apollo = nuxt.get('apollo', {}).get('defaultClient', {})

# Data also has the initial page load data
data = nuxt.get('data', [{}])[0]
event = data.get('event', {})

print(f"Event Name: {event.get('name')}")
runners = event.get('competitors', [])
print(f"Num runners: {len(runners)}")

if runners:
    runner = runners[0]
    print(f"First Runner ID: {runner.get('id')}")
    # Print keys of the runner object
    print("Runner Keys:", list(runner.keys()))
    
    # Check if form guide data is present
    print(f"Horse Name: {runner.get('animal', {}).get('name')}")
    print(f"Form guide past runs count: {len(runner.get('pastRuns', []))}")
    if runner.get('pastRuns'):
        run = runner['pastRuns'][0]
        print(f"Sample past run keys: {list(run.keys())}")
        print(f"Date: {run.get('event', {}).get('startTime')}")
        print(f"Track: {run.get('meeting', {}).get('venue', {}).get('name')}")
        print(f"Distance: {run.get('event', {}).get('distance')}")
        print(f"Position: {run.get('position')} / {run.get('starters')}")
