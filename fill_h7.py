import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing = data.get("horses", {}).get("7", {})
nonce = existing.get("_validation_nonce", "")

data["horses"]["7"].update({
    "_validation_nonce": nonce,
    "scenario_tags": ["初出馬", "試閘走勢平庸", "外檔大蝕位"],
    "status_cycle": "未達水準",
    "trend_summary": "兩次試閘走勢平庸，近試 818m 亦只能跑第4，未見有突出速度。",
    "analytical_breakdown": {
        "class_weight": "未有賽績，無法評估級數。",
        "engine_distance": "能力未見底，暫估為 Type B 均速型。",
        "track_surface_gait": "未知。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Richard & Will Freedman 配 Chad Schofield，屬合格至中上配搭。"
    },
    "sectional_forensic": {
        "raw_L400": "N/A",
        "correction_factor": "無",
        "corrected_assessment": "欠缺正式賽事段速數據。",
        "trend": ""
    },
    "eem_energy": {
        "last_run_position": "-",
        "cumulative_drain": "0",
        "assessment": "初出馬體力充沛。然而抽得 8 檔（外檔），出閘若要切入將消耗大量 EEM，若留後則在 1000m 賽事難以收復失地。"
    },
    "forgiveness_archive": {
        "factors": "無",
        "conclusion": "無需寬恕"
    },
    "matrix": {
        "狀態與穩定性": {"score": "➖", "reasoning": "試閘表現平平，未見冒勇"},
        "段速與引擎": {"score": "➖", "reasoning": "缺乏速度展現"},
        "EEM與形勢": {"score": "❌", "reasoning": "8檔外檔極劣勢"},
        "騎練訊號": {"score": "➖", "reasoning": "正常班底，未見特別殺機"},
        "級數與負重": {"score": "➖", "reasoning": "級數未知"},
        "場地適性": {"score": "➖", "reasoning": "場地性能未知"},
        "賽績線": {"score": "➖", "reasoning": "無賽績線"},
        "裝備與距離": {"score": "➖", "reasoning": "1000m"}
    },
    "base_rating": "D+",
    "fine_tune": {
        "direction": "-",
        "trigger": "8檔外檔，試閘平庸"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "D",
    "core_logic": "此駒賽前兩次試閘未見有任何驚喜走勢，近一次於 Warwick Farm 818m 試閘亦只能跑第 4。今仗初出即出戰對排檔要求極高嘅 Hawkesbury 1000m，不幸抽中 8 檔大外檔，形勢可謂雪上加霜。即使騎練配搭尚可，但本身進度及排檔均處於絕對劣勢，難以看好。",
    "advantages": ["騎練配搭尚可"],
    "disadvantages": ["8檔外檔非常輸蝕", "試閘未見速度", "進度一般"],
    "stability_index": "低",
    "tactical_plan": {
        "start": "嘗試出閘後向內切入尋找遮擋",
        "middle": "很大機會被迫在三疊或更外疊競跑",
        "straight": "望空後視乎餘力，但預計較為吃力"
    },
    "dual_track": {
        "triggered": False
    },
    "underhorse": {
        "triggered": True,
        "condition": "排檔劣勢及進度未足",
        "reason": "試閘全無走勢兼排外檔，極難突圍。"
    }
})

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Horse 7 logic filled.")
