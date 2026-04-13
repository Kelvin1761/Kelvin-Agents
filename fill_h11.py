import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing = data.get("horses", {}).get("11", {})
nonce = existing.get("_validation_nonce", "")

data["horses"]["11"].update({
    "_validation_nonce": nonce,
    "scenario_tags": ["鄉鎮賽績", "外疊居中", "末段力弱", "冷門分子"],
    "status_cycle": "未達水準",
    "trend_summary": "上仗初出於 Dubbo 1100m 上陣，路程最後 200 米呈現乏力，反映能力不足以爭勝。",
    "analytical_breakdown": {
        "class_weight": "上仗鄉鎮賽事 (Dubbo) 亦未能交出水準，證明級數稍次。",
        "engine_distance": "前速唔夠快，只能守 4th 2W，末段亦未能衝刺。縮程 1000m 或有助氣量，但前速將成疑。估計為 Type C 均速偏慢型。",
        "track_surface_gait": "上仗跑好地(Good)無特別表現。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Damien Lane 訓練，騎師未有公佈 (Unknown)，陣容極為薄弱。"
    },
    "sectional_forensic": {
        "raw_L400": "N/A",
        "correction_factor": "無",
        "corrected_assessment": "欠缺正式段速紀錄，但賽後報告指「Did not finish race off well enough last 200m」，證明末段乏力。",
        "trend": ""
    },
    "eem_energy": {
        "last_run_position": "8th3→4th3→F5",
        "cumulative_drain": "中低",
        "assessment": "上仗居中二疊，消耗不算大，但依然斷氣。今仗排 6 檔，預期形勢亦只能守在二疊，無太大優勢。"
    },
    "forgiveness_archive": {
        "factors": "無",
        "conclusion": "形勢正常下依然力弱，不值得寬恕。"
    },
    "matrix": {
        "狀態與穩定性": {"score": "❌", "reasoning": "上仗末段乏力，未見狀態"},
        "段速與引擎": {"score": "❌", "reasoning": "缺乏有效前速及後勁"},
        "EEM與形勢": {"score": "➖", "reasoning": "6檔不過不失"},
        "騎練訊號": {"score": "❌", "reasoning": "騎師未定，幕後缺乏信心"},
        "級數與負重": {"score": "❌", "reasoning": "鄉村賽大敗，級數未夠"},
        "場地適性": {"score": "➖", "reasoning": "好地未能交出表現"},
        "賽績線": {"score": "➖", "reasoning": "無資料"},
        "裝備與距離": {"score": "➖", "reasoning": "縮程 1000m 或可紓緩斷氣問題，但難反先"}
    },
    "base_rating": "D",
    "fine_tune": {
        "direction": "-",
        "trigger": "騎師從缺，鄉村賽大敗"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "D",
    "core_logic": "此駒上仗初出自視頗低，於較次級嘅鄉鎮馬場 Dubbo 出戰 1100m 賽事，沿途雖然進佔第 4 位嘅有利位置（二疊包廂），但直路最後 200 米卻未能交出衝刺，最終面對弱旅亦只跑第 5（6匹馬出賽）。今仗由鄉鎮場越級挑戰 provincial 省級別嘅 Hawkesbury，對手級數強得多，加上至今連騎師都未卜，明顯只係志在參與嘅陪跑份子，可以不理。",
    "advantages": ["縮程 1000m 或有助解決末段乏力問題"],
    "disadvantages": ["上仗鄉村賽大敗，級數太低", "末段乏力", "騎師未定，部署消極"],
    "stability_index": "低",
    "tactical_plan": {
        "start": "順其自然出閘",
        "middle": "嘗試留守馬群中後疊數",
        "straight": "跟隨大隊過終點"
    },
    "dual_track": {
        "triggered": False
    },
    "underhorse": {
        "triggered": True,
        "condition": "任何情況",
        "reason": "上仗鄉鎮賽形勢好亦大敗，級數未夠兼無人策騎，完全屬陪跑馬。"
    }
})

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Horse 11 logic filled.")
