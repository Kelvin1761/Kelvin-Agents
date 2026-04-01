import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'G:\.shortcut-targets-by-id\1hKLy5yBvy7czsQJKGZULAqAgYmUqKC3q\Antigravity\2026-03-28 Meydan Race 5-5\raw_overview_nuxt.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

meeting = data['data'][0]['meeting']
events = meeting.get('events', [])
print(f"Total events: {len(events)}")
for i, evt in enumerate(events):
    name = evt.get('name', '?')
    dist = evt.get('distance', '?')
    slug = evt.get('slug', '?')
    sels = evt.get('selections', [])
    print(f"  [{i}] {name} | {dist}m | {len(sels)} runners | slug: {slug}")
