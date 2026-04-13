import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing = data.get("horses", {}).get("8", {})
nonce = existing.get("_validation_nonce", "")

data["horses"]["8"].update({
    "_validation_nonce": nonce,
    "scenario_tags": ["初出馬", "試閘勝出", "大外檔地獄"],
    "status_cycle": "初出即用",
    "trend_summary": "賽前唯一一次同場 800m 試閘勝出，展現出前速，但今排大外檔考驗極大。",
    "analytical_breakdown": {
        "class_weight": "未有賽績，無法評估級數。",
        "engine_distance": "試閘展示前速，估計為 Type A 前領型引擎。",
        "track_surface_gait": "未知。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Blake Ryan 加 Jay Ford，普通班底。"
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
        "assessment": "初出馬體力充沛。然而不幸抽得全場最外的 11 檔，若要憑前速切入內欄，將面臨極大阻力並消耗極多 EEM。"
    },
    "forgiveness_archive": {
        "factors": "無",
        "conclusion": "無需寬恕"
    },
    "matrix": {
        "狀態與穩定性": {"score": "➖", "reasoning": "試閘表現好，但初出穩定性成疑"},
        "段速與引擎": {"score": "✅", "reasoning": "憑試閘展現優秀前速"},
        "EEM與形勢": {"score": "❌", "reasoning": "11檔排位絕對是惡夢"},
        "騎練訊號": {"score": "➖", "reasoning": "一般騎練組合"},
        "級數與負重": {"score": "➖", "reasoning": "級數未知"},
        "場地適性": {"score": "➖", "reasoning": "場地性能未知"},
        "賽績線": {"score": "➖", "reasoning": "無賽績線"},
        "裝備與距離": {"score": "➖", "reasoning": "1000m 適合"}
    },
    "base_rating": "C",
    "fine_tune": {
        "direction": "-",
        "trigger": "11檔大外檔地獄"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "C-",
    "core_logic": "此駒質素理應不差，賽前於同場試 800m 閘順利拔頭籌。然而，今仗命運弄人，抽中全場最外位置嘅 11 檔。Hawkesbury 1000m 對排外檔嘅前領馬極度殘酷，第一隻彎離起步點極近，如果要強行切入將幾乎肯定要與內側馬群力拼，未入直路已經會耗盡 EEM；若果選擇留後，於此窄場又缺乏足夠直路追前。喺排檔形勢嚴重制肘下，只能作為冷腳或忍痛放棄。",
    "advantages": ["曾於同場試閘輕鬆勝出", "具備前速"],
    "disadvantages": ["11檔大外檔屬致命傷", "騎練配搭普通", "欠缺實戰經驗"],
    "stability_index": "低",
    "tactical_plan": {
        "start": "別無選擇，出閘後必須奮力搶前",
        "middle": "極大機會被迫在三四疊競跑，消耗甚大",
        "straight": "視乎早段能否神奇切入，否則直路初便會乏力"
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

print("Horse 8 logic filled.")
