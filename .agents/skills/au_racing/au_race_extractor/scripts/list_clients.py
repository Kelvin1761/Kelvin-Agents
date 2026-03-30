import json

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    text = f.read()

import ijson
f = open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'rb')
parser = ijson.parse(f)
for prefix, event, value in parser:
    if event == 'map_key' and value == 'apollo':
        print(f"Found apollo")
    elif prefix == 'apollo' and event == 'map_key':
        print(f"Apollo client: {value}")
