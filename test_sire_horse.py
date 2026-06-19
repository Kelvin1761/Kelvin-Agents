import sys
from pathlib import Path

SCRIPT_DIR = Path("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/skills/au_racing/au_race_extractor/scripts")
sys.path.append(str(SCRIPT_DIR.parents[1]))

from racenet_transport import fetch_nuxt_data

url = "https://www.racenet.com.au/horse/celestial-charm"
data = fetch_nuxt_data(url)
apollo = data.get('apollo', {}).get('defaultClient', data.get('apollo', {}).get('horseClient', {}))

found = False
for key, val in apollo.items():
    if isinstance(val, dict):
        for k, v in val.items():
            if isinstance(v, str) and "15%" in v:
                print(f"Found 15% in {key}: {k} = {v}")
                found = True
            if k == "sireName":
                print(f"Found sireName in {key}: {v}")

if not found:
    print("No Sire stats found in horse profile apollo payload.")
