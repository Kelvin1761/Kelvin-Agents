import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing = data.get("horses", {}).get("3", {})
nonce = existing.get("_validation_nonce", "")

data["horses"]["3"].update({
    "_validation_nonce": nonce,
    "scenario_tags": ["前領型", "初出曾領放", "縮程", "外檔大蝕位"],
    "status_cycle": "熱身後漸進",
    "trend_summary": "上仗初出 1200m 展現飛快前速，放入直路後乏力。今縮程 1000m 較合發揮。",
    "analytical_breakdown": {
        "class_weight": "上仗 Wyong 處女馬賽得第5名，有前速但貫注力不足。",
        "engine_distance": "上仗 1200m 展現極快段速但末段崩潰，縮程至 1000m 絕對是利好因素。為典型 Type A 領放引擎。",
        "track_surface_gait": "上仗跑軟地(Soft)，無不妥。",
        "gear_intent": "無特別紀錄。",
        "jockey_trainer_combination": "Kim Waugh 配 Ashley Morgan，具備一定戰鬥力。"
    },
    "sectional_forensic": {
        "raw_L400": "N/A",
        "correction_factor": "無",
        "corrected_assessment": "上仗 Wyong 沒有詳細段速，但文字描述「Led sett 1.3L. S/L straightening. Beaten 200m」，證明其早段 800m 速度極高。",
        "trend": ""
    },
    "eem_energy": {
        "last_run_position": "8th1→4th1→F5",
        "cumulative_drain": "中等",
        "assessment": "上仗初出強行放頭，末段耗盡體力退敗。今次縮程本應有利，但不幸抽得 9 檔（外檔），出閘若強行切入將再次消耗大量 EEM。"
    },
    "forgiveness_archive": {
        "factors": "初出即跑 1200m 氣量未足",
        "conclusion": "上仗初出放頭敗陣有氣量藉口，今次縮程可予寬恕。"
    },
    "matrix": {
        "狀態與穩定性": {"score": "➖", "reasoning": "熱身一仗後理應提升，但未有證明"},
        "段速與引擎": {"score": "✅", "reasoning": "擁有一流早段前速"},
        "EEM與形勢": {"score": "❌", "reasoning": "9檔極差，Hawkesbury 1000m 利內排，外檔強行切入代價大"},
        "騎練訊號": {"score": "➖", "reasoning": "正常班底"},
        "級數與負重": {"score": "➖", "reasoning": "處女馬賽中游"},
        "場地適性": {"score": "➖", "reasoning": "軟地可應付"},
        "賽績線": {"score": "➖", "reasoning": "上仗無賽績線參考"},
        "裝備與距離": {"score": "✅", "reasoning": "縮程 1000m 極端有利其跑法"}
    },
    "base_rating": "C",
    "fine_tune": {
        "direction": "-",
        "trigger": "9檔外檔極劣勢，抵銷了縮程利好"
    },
    "override": {
        "rule": ""
    },
    "final_rating": "C-",
    "core_logic": "本身屬典型前速甚高嘅賽駒，上仗初出 1200m 自己帶放，去到直路最後 200m 先至斷氣，證明本身引擎極具威力。今次縮程 1000m 本來係極完美嘅部署，可惜天意弄人竟然抽到 9 檔大外檔。Hawkesbury 1000m 起步轉彎非常急，如果硬要從外檔搶出切入，頭段所消耗嘅 EEM 體能必定超乎想像，直接會重演上仗直路斷氣嘅畫面；如果唔搶，本身又唔識留。形勢險惡，只能作冷腳看待。",
    "advantages": ["前速極快", "縮程 1000m 百分百合腳法"],
    "disadvantages": ["9檔大外檔，極具毀滅性", "末段貫注力成疑"],
    "stability_index": "低",
    "tactical_plan": {
        "start": "別無選擇，必須出閘狂推搶佔前列",
        "middle": "嘗試切入內疊，與內檔馬纏鬥",
        "straight": "希望縮程 1000m 能頂到終點"
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

print("Horse 3 logic filled.")
