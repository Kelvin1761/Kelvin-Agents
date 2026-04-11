import json

with open('2026-04-12_ShaTin/Race_1_Logic.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

data['race_analysis']['verdict'] = {
    "track_scenario": "沙田直路1000米（C賽道無關痛癢，向看台外檔有利）。",
    "confidence": "低",
    "key_variables": "全場新馬初出，起步快慢及能否靠攏外欄成關鍵。",
    "top4": [
        {"horse_num": 5, "reason": "排最佳6檔，形勢大好。", "risk": "初出欠缺經驗。"},
        {"horse_num": 4, "reason": "排5檔優越，田泰安硬功有利直路衝刺。", "risk": "走規可能未熟成。"},
        {"horse_num": 2, "reason": "潘頓執韁，試閘見前速。", "risk": "4檔屬中檔，需及早找尋遮擋或外移。"},
        {"horse_num": 1, "reason": "梁家俊策騎，內檔不利但對手不多。", "risk": "2檔形勢吃虧。"}
    ],
    "pace_flip_insurance": {
        "if_faster": {"benefit": "後上馬", "hurt": "前領馬"},
        "if_slower": {"benefit": "前領跑法", "hurt": "後追馬"}
    },
    "emergency_brake": "新馬賽變數極大，賠率若有異動需特別提防落飛馬。",
    "blind_spots": {
        "sectionals": "無實戰段速參考。",
        "risk_management": "初出馬表現飄忽，注碼宜輕。",
        "trials_illusion": "試閘表現未必等同實戰。",
        "age_risk": "年輕馬狀態及情緒不穩。",
        "pace_collapse_darkhorse": "無明顯黑馬，全為未知數。"
    }
}

with open('2026-04-12_ShaTin/Race_1_Logic.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
