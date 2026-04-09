import json
from bs4 import BeautifulSoup

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

scripts = soup.find_all('script')
print(f"Found {len(scripts)} script tags")

for i, script in enumerate(scripts):
    content = script.string
    if content and "window.__PRELOADED_STATE__" in content:
        print(f"Found window.__PRELOADED_STATE__ in script {i}")
        # Extract the JSON part
        try:
            json_str = content.split("window.__PRELOADED_STATE__ = ")[1].split(";window.__APOLLO_STATE__")[0]
            print(f"Extracted JSON string, length: {len(json_str)}")
            data = json.loads(json_str)
            print(f"Successfully parsed JSON. Keys: {data.keys()}")
            
            with open('./.agents/skills/au_race_extractor/scripts/preloaded_state.json', 'w') as out:
                json.dump(data, out, indent=2)
            print("Saved exactly to preloaded_state.json")
            break
        except Exception as e:
            print(f"Error parsing json: {e}")
