# -*- coding: utf-8 -*-
import json

with open("2026-05-03_ShaTin/Race_4_Logic.json", "r", encoding="utf-8") as f:
    data = json.load(f)

h2 = data["horses"]["2"]

h2["matrix"]["stability"]["reasoning"] = "[Resource Check: 05_forensic_analysis.md / 穩定性+醫療事故作廢規則]\n[近6場數據(含班次): 第1仗(15/04/2026 第四班): 6名 1-3/4 | 第2仗(25/03/2026 第四班): 3名 1-1/2 | 第3仗(04/03/2026 第四班): 2名 1/2]\n[季內=季內 (1-1-1-4) | 同程 (1-1-1-3), 頭馬距離趨勢=1-3/4→1-1/2→1/2→3-1/4→2-1/2→2 → 📈收窄中]\n[生涯標記: ESTABLISHED; 香港正式賽事場次=7; 標準馬]\n[晨操 digest: status=ok, mode=status_continuity, load=快操3/試閘0/踱步17/游水17/空白0, trend=easing, pattern_replay=57, maintenance=60, positives=無, risks=操練放緩]\n[晨操判讀規則: 正式賽績與晨操 50/50；近績差馬若有 pattern_replay_score/TW_WIN_PATTERN_REPLAY，不可單憑近績死扣]\n[🏥 健康掃描(作廢用): ✅ 無醫療事故記錄]\n→ [判讀: 賽績方面，近績整體名次穩定且頭馬距離呈收窄趨勢，但晨操指標稍見放緩（體能維持=60，具備「操練放緩」風險標記），綜合賽績與晨操表現後，穩定性評估仍可維持正面。]"

h2["core_logic"] = "團結戰靈近6仗跑獲6-3-2-9-4-4（1亞1季），頭馬距離呈收窄趨勢，可惜晨操指標稍降（體能維持=60，有「操練放緩」標記），加上今仗排10檔形勢不利，預期快步速下守中段跑法或面臨外疊消耗。儘管L400造出22.83秒及具備極強賽績線（強組比例10/11），但整體實力受制於劣檔，屬邊緣爭位分子。"

with open("2026-05-03_ShaTin/Race_4_Logic.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
