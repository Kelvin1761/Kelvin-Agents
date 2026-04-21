import re

file_path = '/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-22_HappyValley/Race_1_Logic.json'

with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# I see lines 206 to 209 are:
#         "stability": {
#           "score": "➖",
#           "reasoning": "近績不算好，但頭馬距離收窄中且評分大幅下調"
#        "scenario_tags": "[\"升班\", \"有利檔位\", \"最佳路程\"]",
# This means I accidentally removed the rest of Horse 2 matrix and start of Horse 3.

# Actually, the easiest way to reset the file is to copy from a backup if it exists, or just truncate it at the end of horses.1 and let the orchestrator regenerate.
# If I delete "2" and "3" entirely, and set "horses" to just contain "1".
# But wait, the orchestrator might be waiting for "3" and if it doesn't find "3" it might crash or recreate it.

# Let's extract "1" and reconstruct the json.
import json
# I can try to find the valid JSON block for "1"
match = re.search(r'("1": \{.*?\n    \})', text, re.DOTALL)
if match:
    horse_1 = match.group(1)
    new_json_str = '{\n  "race_analysis": {\n    "race_number": 1,\n    "race_class": "C4",\n    "distance": "1200m",\n    "speed_map": {\n      "predicted_pace": "Moderate",\n      "leaders": [\n        "5"\n      ],\n      "on_pace": [\n        "3",\n        "4",\n        "8"\n      ],\n      "mid_pack": [\n        "2",\n        "7",\n        "9",\n        "11",\n        "12"\n      ],\n      "closers": [\n        "1",\n        "6",\n        "10"\n      ],\n      "track_bias": "C+3跑道，1200m。直路短，預計內疊前領或跟前馬佔優，後追馬需走位順暢及步速配合。",\n      "tactical_nodes": "#5 預計單騎領放，#3,#4,#8 緊隨其後。步速正常下，前置馬有一定優勢。",\n      "collapse_point": "除非 #5 狂放耗力，否則步速未必崩潰，後追馬需靠對手失誤或自己有極強爆發力。"\n    }\n  },\n  "horses": {\n    ' + horse_1 + '\n  }\n}'
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_json_str)
    print("Fixed via regex reconstruction.")
else:
    print("Could not find horse 1 block.")
