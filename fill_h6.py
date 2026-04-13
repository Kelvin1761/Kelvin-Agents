import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing = data.get("horses", {}).get("6", {})
nonce = existing.get("_validation_nonce", "")

data["horses"]["6"].update({
    "_validation_nonce": nonce,
    "scenario_tags": ["初出馬", "試閘包尾", "陪跑份子"],
    "status_cycle": "未達水準",
    "trend_summary": "賽前唯一一次試閘於 Hawkesbury 800m 包尾大敗(9/9)，進度嚴重未足。",
    "analytical_breakdown": {
        "class_weight": "試閘表現如斯，估計連處女馬賽水準亦未達。",
        "engine_distance": "未能評估引擎，完全缺乏競爭力。",
        "track_surface_gait": "未知。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Michael Vella 加 Deon Le Roux，極為冷門之騎練組合。"
    },
    "sectional_forensic": {
        "raw_L400": "N/A",
        "correction_factor": "無",
        "corrected_assessment": "無任何段速數據支持。",
        "trend": ""
    },
    "eem_energy": {
        "last_run_position": "-",
        "cumulative_drain": "0",
        "assessment": "初出馬體能充足，但排 4 檔亦無法搭救進度問題。"
    },
    "forgiveness_archive": {
        "factors": "無",
        "conclusion": "無需寬恕"
    },
    "matrix": {
        "狀態與穩定性": {"score": "❌", "reasoning": "試閘包尾"},
        "段速與引擎": {"score": "❌", "reasoning": "毫無展現"},
        "EEM與形勢": {"score": "➖", "reasoning": "4檔屬好檔，但無補於事"},
        "騎練訊號": {"score": "❌", "reasoning": "全無賣點"},
        "級數與負重": {"score": "❌", "reasoning": "連試閘都無法應付"},
        "場地適性": {"score": "➖", "reasoning": "未知"},
        "賽績線": {"score": "➖", "reasoning": "無賽績線"},
        "裝備與距離": {"score": "❌", "reasoning": "進度未夠跑 1000m"}
    },
    "base_rating": "D",
    "fine_tune": {
        "direction": "-",
        "trigger": "試閘包尾大敗"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "D-",
    "core_logic": "此駒為初出馬，練馬師及騎師名氣極弱。賽前唯一一次準備係喺同場 Hawkesbury 試 800m 閘，結果包尾而回。現階段進度完全未及格，只屬陪跑份子，完全不作考慮。",
    "advantages": ["排4檔形勢正常"],
    "disadvantages": ["試閘包尾", "進度未足", "冷門騎練配搭"],
    "stability_index": "低",
    "tactical_plan": {
        "start": "順其自然起步",
        "middle": "跟隨大隊，未能跟上步速",
        "straight": "提早力弱"
    },
    "dual_track": {
        "triggered": False
    },
    "underhorse": {
        "triggered": True,
        "condition": "任何情況",
        "reason": "進度嚴重未足，試閘包尾，缺乏任何爭勝條件。"
    }
})

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Horse 6 logic filled.")
