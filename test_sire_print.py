import sys
from pathlib import Path
import json

SCRIPT_DIR = Path("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/skills/au_racing/au_race_extractor/scripts")
sys.path.append(str(SCRIPT_DIR.parents[1]))

from racenet_transport import fetch_nuxt_data

url = "https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug=canterbury-20260527&eventSlug=hyland-race-colours-handicap-race-2&printSlug=print-form"
data = fetch_nuxt_data(url)
with open("test_payload_print.json", "w") as f:
    json.dump(data, f)
