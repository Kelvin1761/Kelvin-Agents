import json

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    text = f.read()
    
# Let's find the exact path to "Competitor:943628"
import ijson

def get_path_to_key():
    f = open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'rb')
    parser = ijson.parse(f)
    for prefix, event, value in parser:
        if prefix.endswith('Competitor:943628'):
            print(f"Found it! Path: {prefix}")
            break
            
get_path_to_key()
