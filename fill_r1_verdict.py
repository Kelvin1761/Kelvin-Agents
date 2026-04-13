import json

file_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7/Race_1_Logic.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

data["race_analysis"]["verdict"] = {
    "confidence": "🟡中",
    "top4": [
        {
            "horse_num": "2",
            "reason": "上仗大幅犯錯依然上名，質素極高兼有2檔優勢",
            "risk": "走規稚嫩"
        },
        {
            "horse_num": "4",
            "reason": "超級寬恕馬，上仗沿途三疊無遮擋，抽5檔可現真身",
            "risk": "排檔不如內線馬慳力"
        },
        {
            "horse_num": "10",
            "reason": "試閘表現好，3檔起步佔盡先機",
            "risk": "初出馬穩定性未經證明"
        },
        {
            "horse_num": "1",
            "reason": "排1檔黃金位置，大馬房效應",
            "risk": "缺乏實戰經驗"
        }
    ],
    "top2_confidence_1": "🟢高",
    "top2_confidence_2": "🟡中",
    "pace_flip_insurance": {
        "if_faster": {
            "benefit": "4檔 Portico (後追有望)",
            "hurt": "9檔 Oxford Power (前領耗力)"
        },
        "if_slower": {
            "benefit": "2檔 Barracks (從容守位)",
            "hurt": "4檔 Portico (追不到)"
        }
    }
}

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Verdict filled!")
