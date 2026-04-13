import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing = data.get("horses", {}).get("5", {})
nonce = existing.get("_validation_nonce", "")

data["horses"]["5"].update({
    "_validation_nonce": nonce,
    "scenario_tags": ["初出馬", "試閘勝出", "前速型", "偏外檔"],
    "status_cycle": "初出即用",
    "trend_summary": "第一仗初出，賽前唯一一次試閘於 Kembla Grange 800m 輕鬆勝出，具備不俗前速。",
    "analytical_breakdown": {
        "class_weight": "未有賽績，無法評估級數。",
        "engine_distance": "唯一試閘為 800m 短途，今仗 1000m 距離算是射程範圍。估計為 Type A 帶前速型。",
        "track_surface_gait": "未知場地性能。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Kerry Parker 配 Andrew Adkins，非一線大倉組合，但有一定戰意。"
    },
    "sectional_forensic": {
        "raw_L400": "N/A",
        "correction_factor": "無",
        "corrected_assessment": "欠缺正式賽事段速數據。",
        "trend": ""
    },
    "eem_energy": {
        "last_run_position": "F1 (試閘)",
        "cumulative_drain": "0",
        "assessment": "初出體力 100%，試閘展現前速。排 7 檔偏外，若要切入領放需消耗一定初段 EEM。"
    },
    "forgiveness_archive": {
        "factors": "無",
        "conclusion": "初出馬，無需寬恕"
    },
    "matrix": {
        "狀態與穩定性": {"score": "➖", "reasoning": "試閘表現不俗但初出穩定性成疑"},
        "段速與引擎": {"score": "➖", "reasoning": "未有正式賽事數據"},
        "EEM與形勢": {"score": "➖", "reasoning": "7檔偏外，切入有難度"},
        "騎練訊號": {"score": "➖", "reasoning": "二線級數配搭"},
        "級數與負重": {"score": "➖", "reasoning": "級數未知"},
        "場地適性": {"score": "➖", "reasoning": "場地性能未知"},
        "賽績線": {"score": "➖", "reasoning": "無賽績線"},
        "裝備與距離": {"score": "➖", "reasoning": "1000m 適合初出"}
    },
    "base_rating": "C",
    "fine_tune": {
        "direction": "-",
        "trigger": "檔位偏外，騎練班底稍弱"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "C-",
    "core_logic": "初出馬賽前僅試了一課 800m 閘便勝出，反映有一定前速及早熟程度。然而，今仗抽得 7 檔，在 Hawkesbury 1000m 這個極度偏向內檔及前領的場地，要從 7 檔切入並不容易，若強行搶放隨時消耗過多 EEM 導致末段乏力。加上騎練組合 Kerry Parker 及 Andrew Adkins 在這類處女馬賽中未算最具統治力，宜先作觀望。",
    "advantages": ["試閘曾勝出，有前速", "初出體力充沛"],
    "disadvantages": ["7檔偏外容易被頂出外疊", "欠缺實戰經驗", "騎練班底一般"],
    "stability_index": "低",
    "tactical_plan": {
        "start": "憑前速嘗試爭奪領先位置",
        "middle": "若未能切入則可能被迫在外疊競跑",
        "straight": "視乎早段消耗決定是否有餘力衝刺"
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

print("Horse 5 logic filled.")
