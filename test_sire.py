import sys
from pathlib import Path
import json

SCRIPT_DIR = Path("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/skills/au_racing/au_race_extractor/scripts")
SKILL_ROOT = SCRIPT_DIR.parents[1]
sys.path.append(str(SKILL_ROOT))

from racenet_transport import RacenetBlockedError, fetch_nuxt_data

url = "https://www.racenet.com.au/form-guide/horse-racing/canterbury-20260527/race-1"
data = fetch_nuxt_data(url)
apollo = data.get('apollo', {}).get('defaultClient', data.get('apollo', {}).get('horseClient', {}))

found = False
for key, val in apollo.items():
    if isinstance(val, dict):
        if "sire" in val or "Sire" in val or "sireName" in val:
            print(f"Found sire key in {key}")
            found = True
        
        # Check if any string value contains 'starts'
        for k, v in val.items():
            if isinstance(v, str) and "starts" in v.lower():
                print(f"Found starts string in {key}: {k} = {v}")
                found = True
if not found:
    print("No Sire or starts info found in apollo payload.")
