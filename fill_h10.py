import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing = data.get("horses", {}).get("10", {})
nonce = existing.get("_validation_nonce", "")

data["horses"]["10"].update({
    "_validation_nonce": nonce,
    "scenario_tags": ["初出馬", "大馬房", "試閘上名", "3檔慳位"],
    "status_cycle": "初出即用",
    "trend_summary": "賽前經過 4 次試閘打磨，最近一次同場 800m 試閘跑獲亞軍，進度理想。",
    "analytical_breakdown": {
        "class_weight": "未有賽績，無法評估級數。",
        "engine_distance": "最近試閘跑 800m 展現前速，估計為 Type A/B 居中前領型。",
        "track_surface_gait": "未知。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Ciaron Maher 配 Keagan Latham。同廄有大師傅壓陣的 Horse 2，此駒似是副車，但排檔佳。"
    },
    "sectional_forensic": {
        "raw_L400": "N/A",
        "correction_factor": "無",
        "corrected_assessment": "欠缺正式賽事段速數據。",
        "trend": ""
    },
    "eem_energy": {
        "last_run_position": "F2 (試閘)",
        "cumulative_drain": "0",
        "assessment": "初出體力充沛。排 3 檔屬極佳檔位，預期出閘後能從容貼欄或跟隨放頭馬，EEM 消耗將能降至最低。"
    },
    "forgiveness_archive": {
        "factors": "無",
        "conclusion": "無需寬恕"
    },
    "matrix": {
        "狀態與穩定性": {"score": "➖", "reasoning": "試閘表現不俗，但需實戰印證"},
        "段速與引擎": {"score": "➖", "reasoning": "缺正式數據"},
        "EEM與形勢": {"score": "✅", "reasoning": "3檔屬極佳好位，慳力"},
        "騎練訊號": {"score": "➖", "reasoning": "大馬房，但配搭不及同廄的 2 號馬"},
        "級數與負重": {"score": "➖", "reasoning": "未知"},
        "場地適性": {"score": "➖", "reasoning": "未知"},
        "賽績線": {"score": "➖", "reasoning": "未知"},
        "裝備與距離": {"score": "➖", "reasoning": "1000m 適合初出"}
    },
    "base_rating": "C+",
    "fine_tune": {
        "direction": "+",
        "trigger": "3檔好位及大馬房效應"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "B-",
    "core_logic": "此駒為 Ciaron Maher 訓練之初出馬，與同場大熱分子 Horse 2 同主帥。賽前一共試了四課閘，最近一次於同場 800m 跑獲亞軍，顯示進度已經到位。今仗抽得極具優勢的 3 檔，出閘後能輕易搵到遮擋慳水慳力。雖然從頭盔判斷，主帥 Tommy Berry 揀咗騎 Horse 2，此駒表面屬廄內副車，但喺 3 檔完美形勢下絕對有力威脅大局，至少屬位置之材。",
    "advantages": ["抽得3檔靚位，形勢極佳", "近試同場大閘獲亞，準備充足", "Ciaron Maher大馬房"],
    "disadvantages": ["似乎是馬房副車", "缺實戰經驗"],
    "stability_index": "中",
    "tactical_plan": {
        "start": "順步出閘，讓內側馬匹上前",
        "middle": "守在 3 檔內欄有利位置（可能是領放馬背後），慳力",
        "straight": "移出望空衝刺"
    },
    "dual_track": {
        "triggered": False
    },
    "underhorse": {
        "triggered": False,
        "condition": "",
        "reason": ""
    }
})

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Horse 10 logic filled.")
