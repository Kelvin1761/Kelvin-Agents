import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

for h_id, h in data.get("horses", {}).items():
    # Fix tactical_plan
    tactical = h.get("tactical_plan", {})
    if "expected_position" not in tactical:
        tactical["expected_position"] = tactical.get("start", "") + " " + tactical.get("middle", "")
    if "race_scenario" not in tactical:
        tactical["race_scenario"] = tactical.get("straight", "")
    h["tactical_plan"] = tactical
    
    # Fix formline_strength
    analysis = h.get("analytical_breakdown", {})
    if "formline_strength" not in analysis:
        analysis["formline_strength"] = "無資料 (強組比例: N/A)"
    h["analytical_breakdown"] = analysis

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Batch fixed missing keys!")
