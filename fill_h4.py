import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing = data.get("horses", {}).get("4", {})
nonce = existing.get("_validation_nonce", "")

data["horses"]["4"].update({
    "_validation_nonce": nonce,
    "scenario_tags": ["超級寬恕馬", "上仗三疊無遮擋", "縮程", "試閘曾勝出"],
    "status_cycle": "敗後回勇",
    "trend_summary": "上仗初出全程 3WNC 大敗，敗不足據，實力仍是一個謎但有試閘根據。",
    "analytical_breakdown": {
        "class_weight": "未能作準，上仗形勢過於惡劣。",
        "engine_distance": "出戰 1100m 展現出 WTMF 居中跑法，今縮程 1000m 將考驗其前速。",
        "track_surface_gait": "上仗跑軟地(Soft)，無不妥。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Michael Freedman 馬房配 Dylan Gibbons，班底不弱。"
    },
    "sectional_forensic": {
        "raw_L400": "N/A",
        "correction_factor": "形勢極端惡劣",
        "corrected_assessment": "上仗 Kensington 沒有詳細段速，但「3W straightening 1.2L」顯示喺全程三疊無遮擋下轉彎仍能咬緊前領馬，段速底子其實極佳。",
        "trend": ""
    },
    "eem_energy": {
        "last_run_position": "8th4→4th4→F8",
        "cumulative_drain": "高",
        "assessment": "上仗初出遭遇地獄級賽程：起步被帶出外層，全條直路 3WNC (三疊無遮擋)，賽後報告更指「Slow to recover. Did plenty of work in run」。今次排 5 檔，預計 EEM 消耗會大幅正常化。"
    },
    "forgiveness_archive": {
        "factors": "Taken out shortly after start + 3WNC 全程三疊無遮擋",
        "conclusion": "100% 絕對寬恕。上仗敗績完全是形勢造成，不能反映其實力。"
    },
    "matrix": {
        "狀態與穩定性": {"score": "➖", "reasoning": "上仗大敗復原能力成疑"},
        "段速與引擎": {"score": "✅", "reasoning": "三疊無遮擋下轉彎仍能咬緊前領馬"},
        "EEM與形勢": {"score": "✅", "reasoning": "今場排5檔，走位理應比上仗地獄級好極多"},
        "騎練訊號": {"score": "✅", "reasoning": "幕後未有放棄，繼續報名硬撼"},
        "級數與負重": {"score": "➖", "reasoning": "未知"},
        "場地適性": {"score": "➖", "reasoning": "未知"},
        "賽績線": {"score": "➖", "reasoning": "無賽績線參考"},
        "裝備與距離": {"score": "➖", "reasoning": "縮程 1000m 考前速"}
    },
    "base_rating": "B",
    "fine_tune": {
        "direction": "+",
        "trigger": "超級寬恕馬！上仗沿途3WNC敗不足據"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "B+",
    "core_logic": "這是一匹典型需要「超級寬恕 (Forgiveness)」嘅賽駒。上仗初出於 Kensington 跑 1100m 運氣極度惡劣，起步被撞兼且全條直路頂在三疊無遮擋 (3WNC) 食風，去到彎頂依然只落後 1.2 馬位，最終因為耗力過度而大敗，賽後報告亦指出佢「Did plenty of work in run」。所以上仗第 8 名絕對可以當粉筆字抹走。今次抽到中檔 5 檔，只要出閘順利搵到遮擋，慳力之下分分鐘可以交出試閘贏馬時嘅水準，係今場一路極具威脅嘅伏兵。",
    "advantages": ["超級寬恕馬，上仗 3WNC 敗不足據", "試閘曾於 Randwick 勝出，有基本質素", "今仗排5檔形勢大幅轉好"],
    "disadvantages": ["上仗嚴重耗力，未知體能是否完全恢復", "居中跑法於 Hawkesbury 1000m 可能較為輸蝕"],
    "stability_index": "低",
    "tactical_plan": {
        "start": "出閘後盡量找遮擋",
        "middle": "守在 5 檔中層二疊位置，保留體力",
        "straight": "望空作最後衝刺"
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

print("Horse 4 logic filled.")
