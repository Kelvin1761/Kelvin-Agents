import json

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    text = f.read()

# Let's find "pastRuns" 
import ijson
def get_path_to_key():
    f = open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'rb')
    parser = ijson.parse(f)
    for prefix, event, value in parser:
        if event == 'map_key' and value == 'pastRuns':
            print(f"Found it! Path: {prefix}")
            break
            
get_path_to_key()
