import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing = data.get("horses", {}).get("9", {})
nonce = existing.get("_validation_nonce", "")

data["horses"]["9"].update({
    "_validation_nonce": nonce,
    "scenario_tags": ["初出馬", "試閘表現好", "大馬房", "外檔大蝕位"],
    "status_cycle": "初出即用",
    "trend_summary": "賽前三次試閘中勝出兩次，包括最近一次於 Scone 900m，走勢譽滿欄邊，具備上佳質素。",
    "analytical_breakdown": {
        "class_weight": "未有賽績，無法評估級數。",
        "engine_distance": "兩次試閘贏馬均展現速度，估計為 Type A 前領型引擎。",
        "track_surface_gait": "未知。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Kris Lees 配 Jason Collett，屬於一線殺手組合，備戰完整。"
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
        "assessment": "初出馬體力充沛。抽得極差的 10 檔，若要憑前速切入將面對同屬快馬的內檔馬阻擊，幾乎無可避免要消耗大量 EEM。"
    },
    "forgiveness_archive": {
        "factors": "無",
        "conclusion": "無需寬恕"
    },
    "matrix": {
        "狀態與穩定性": {"score": "✅", "reasoning": "試閘兩勝，狀態進度比同場大部分馬好"},
        "段速與引擎": {"score": "✅", "reasoning": "試閘前速飛快"},
        "EEM與形勢": {"score": "❌", "reasoning": "10檔屬致命打擊"},
        "騎練訊號": {"score": "✅", "reasoning": "Kris Lees 配 Jason Collett 強陣出擊"},
        "級數與負重": {"score": "➖", "reasoning": "未知"},
        "場地適性": {"score": "➖", "reasoning": "未知"},
        "賽績線": {"score": "➖", "reasoning": "未知"},
        "裝備與距離": {"score": "✅", "reasoning": "1000m 合極高前速馬"}
    },
    "base_rating": "C+",
    "fine_tune": {
        "direction": "-",
        "trigger": "10檔地獄位，雖有質素但難以抵銷形勢劣勢"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "C",
    "core_logic": "單論質素及準備功夫，呢匹由 Kris Lees 訓練嘅初出馬絕對係全場數一數二，三次試閘贏兩次，最近試 Scone 900m 展現出極佳速度，加上配上一線好手 Jason Collett，明顯係有備而來。可惜命運往往喜歡開玩笑，今仗抽中極度惡劣嘅 10 檔。Hawkesbury 1000m 要從 10 檔憑速度切入而唔消耗過多 EEM 幾近不可能，特別係內檔已經有幾匹具前速嘅質新馬。形勢上佢處於絕對下風，因為騎練夠級數兼質素高先勉強可以作冷腳兼顧，極難作穩膽。",
    "advantages": ["試閘兩次勝出，質素高", "Kris Lees 及 Jason Collett 強大班底", "前速快"],
    "disadvantages": ["10檔屬地獄檔位", "切入將消耗極大 EEM"],
    "stability_index": "低",
    "tactical_plan": {
        "start": "憑極快前速出閘，嘗試搶奪前列",
        "middle": "若無法順利切入，面臨三四疊競跑危機",
        "straight": "視乎早段能否神奇地找位，否則直路乏力"
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

print("Horse 9 logic filled.")
