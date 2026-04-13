import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

data["horses"]["1"].update({
    "scenario_tags": ["初出", "大馬房", "試閘有走勢", "1檔慳位"],
    "status_cycle": "初出即用",
    "trend_summary": "試閘表現有進步，近試 1030m 獲亞軍，具備基礎速度。",
    "analytical_breakdown": {
        "class_weight": "未有賽績，無法評估級數。負磅未知。",
        "engine_distance": "兩次試閘分別為 900m 及 1030m，今場 1000m 距離合適。引擎類型推斷為 Type A/B。",
        "track_surface_gait": "未有遇過黏軟爛地，未知場地性能，但試閘於好地有走勢。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Chris Waller 旗下初出馬，配合近期有表現之 Rory Hutchings，馬房有一定計謀。"
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
        "assessment": "初出馬，體能 100%。抽得 1 檔，預計出閘後能輕鬆貼欄，免卻三疊力氣消耗。"
    },
    "forgiveness_archive": {
        "factors": "無",
        "conclusion": "無需寬恕"
    },
    "matrix": {
        "狀態與穩定性": {"score": "➖", "reasoning": "初出馬穩定性成疑，但試閘獲亞表現合格"},
        "段速與引擎": {"score": "➖", "reasoning": "欠缺正式段速數據支持"},
        "EEM與形勢": {"score": "✅", "reasoning": "1檔完美起步點，全程慳位"},
        "騎練訊號": {"score": "✅", "reasoning": "Chris Waller 精兵出擊，初出不可忽視"},
        "級數與負重": {"score": "➖", "reasoning": "未知級數"},
        "場地適性": {"score": "➖", "reasoning": "未知場地性能"},
        "賽績線": {"score": "➖", "reasoning": "無賽績線可循"},
        "裝備與距離": {"score": "➖", "reasoning": "1000m 合初出試閘距離，缺實戰"}
    },
    "base_rating": "C",
    "fine_tune": {
        "direction": "+",
        "trigger": "1檔形勢極佳及大馬房效應"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "C+",
    "core_logic": "初出馬數據匱乏，但兩課試閘已見進步，近試更獲亞軍。今場排得黃金 1 檔，喺 Hawkesbury 呢條窄場會係極大優勢。加上 Chris Waller 馬房作風，有一定作冷潛力，但難以作為絕對穩陣之選。",
    "advantages": ["排1檔極具優勢，慳位", "Chris Waller 操練，試閘見進步（得亞軍）", "體能滿充"],
    "disadvantages": ["欠缺實戰經驗", "無段速及班次證明"],
    "stability_index": "低",
    "tactical_plan": {
        "start": "順住出閘，利用1檔優勢切入內欄前列",
        "middle": "守住前領或放頭馬身後，慳水慳力",
        "straight": "望空挑戰"
    }
})

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Horse 1 logic filled.")
