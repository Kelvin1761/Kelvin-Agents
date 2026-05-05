# -*- coding: utf-8 -*-
import json

with open("2026-05-03_ShaTin/Race_4_Logic.json", "r", encoding="utf-8") as f:
    data = json.load(f)

h3 = data["horses"]["3"]

h3["matrix"]["stability"]["score"] = "❌"
h3["matrix"]["stability"]["reasoning"] = "[Resource Check: 05_forensic_analysis.md / 穩定性+醫療事故作廢規則]\n[近6場數據(含班次): 第1仗(15/04/2026 第四班): 5名 2 | 第2仗(18/03/2026 第四班): 4名 2-1/4 | 第3仗(22/02/2026 第四班): 5名 4-1/2]\n[季內=季內 (0-0-0-7), 頭馬距離趨勢=2→2-1/4→4-1/2→4-1/4→3→3 → 📊波動]\n[生涯標記: ESTABLISHED; 香港正式賽事場次=7; 標準馬]\n[晨操 digest: status=ok, mode=status_continuity, load=快操2/試閘0/踱步17/游水15/空白1, trend=easing, pattern_replay=49, maintenance=60, positives=無, risks=操練放緩]\n[晨操判讀規則: 正式賽績與晨操 50/50；近績差馬若有 pattern_replay_score/TW_WIN_PATTERN_REPLAY，不可單憑近績死扣]\n[🏥 健康掃描(作廢用): ✅ 無醫療事故記錄]\n→ [判讀: 近6仗全未能上名，名次及頭馬距離持續波動，加上晨操表現放緩（體能維持=60，具備「操練放緩」風險標記），綜合賽績及晨操數據反映狀態並不穩定。]"

h3["matrix"]["sectional"]["score"] = "➖"
h3["matrix"]["sectional"]["reasoning"] = "[Resource Check: 03_engine_pace_context.md + 04_engine_corrections.md + 05_forensic_analysis.md / 引擎+段速修正+法醫作廢]\n[引擎(速度分佈): 漸進加速型 | 信心: 高 | 最佳1200m]\n[上仗L400=22.99, L400趨勢=22.99→22.89→21.85→22.67→22.44→22.65 → 趨勢: 波動, 能量趨勢=92→96→89→90→93→94 → 趨勢: 穩定]\n[完成時間偏差: +0.20s→-0.30s→+0.36s→+0.49s→+0.08s→+0.46s → 趨勢: 📊穩定 | 水平: ➖ 接近標準水平 (近 3 仗平均偏差: +0.09s)]\n[🔧 步速修正偏差: +0.34s→+0.38s→+0.77s→+0.72s→+0.51s→+0.51s | 修正水平: ➖ 步速修正後接近平均 (近 3 仗修正平均: +0.50s)]\n[🏥 健康掃描(作廢用): ✅ 無醫療事故記錄]\n→ [判讀: 雖然能量趨勢及完成時間偏差尚算穩定，但步速修正後只屬接近平均水平，全段速剖面顯示起步偏慢，整體段速質量不過不失。]"

h3["matrix"]["race_shape"]["score"] = "❌"
h3["matrix"]["race_shape"]["reasoning"] = "[Resource Check: 05_forensic_analysis.md / 形勢走位 + 步速圖使用規則]\n[上仗走位=5-6-5, XW=(1W1W2W), 消耗=低消耗]\n[檔位=13 (❌不利 (勝率4.0%)), 跑法=中段 | 信心: 高, 走位PI=[+1, +2, +3, +3, +5] → 趨勢: 微跌]\n→ [判讀: 檔位13屬極端不利（勝率僅4%），此駒慣常採取中段跑法，在預期快步速及外檔雙重打擊下，極大機會被迫在外疊消耗，形勢相當惡劣。]"

h3["matrix"]["trainer_signal"]["score"] = "❌"
h3["matrix"]["trainer_signal"]["reasoning"] = "[Resource Check: 07b_trainer_signals.md + 07c_jockey_profiles.md / 騎練部署+人馬配搭]\n[騎師=布浩榮, 練馬師=方嘉柏]\n[配備變動: 上仗 TT | 無今仗配備數據]\n[晨操部署: readiness=60, risks=['操練放緩']]\n[🏇 人馬組合統計: 今仗首次換上布浩榮策騎，過往6仗曾用莫雷拉、布文、何澤堯等好手均未能交代]\n→ [判讀: 換上布浩榮出擊但晨操並未見積極（有「操練放緩」信號），加上之前配多位頂級騎師均無功而還，騎練出擊訊號疲弱。]"

h3["matrix"]["horse_health"]["score"] = "✅"
h3["matrix"]["horse_health"]["reasoning"] = "[Resource Check: 05_forensic_analysis.md + 10a/10b/10c_track_*.md / 健康+場地新鮮感]\n[休賽: 28日, 體重趨勢: 1097→1093→1089→1087→1092→1087 → 📈微增 (波幅10lb)]\n[晨操健康: active_days=19, swimming=15, risk_flags=['操練放緩']]\n[🏥 健康掃描: ✅ 無醫療事故記錄]\n→ [判讀: 休賽28日加上大量游水操練（15次），體重保持在波幅10磅內，健康狀況平穩且無事故紀錄。]"

h3["matrix"]["form_line"]["score"] = "✅✅"
h3["matrix"]["form_line"]["reasoning"] = "[Resource Check: Facts.md 賽績線表格 + 05_forensic_analysis.md / 對手後續強度]\n[賽績線強度=✅✅ 極強 (強組比例: 9/12)]\n[上仗名次=5, 距離差=2]\n→ [判讀: 賽績線強度極高（強組比例9/12），過往多場賽事對手於其後比賽能交出頭馬或上名成績，反映其面對過不少強手。]"

h3["matrix"]["class_advantage"]["score"] = "✅"
h3["matrix"]["class_advantage"]["reasoning"] = "[Resource Check: 06_rating_engine.md / 級數優勢+負重互斥規則]\n[班次=第四班, 負磅=131]\n[評分趨勢=64→62→60→58→56→55 → 穩定]\n→ [判讀: 評分由初出時64分逐步下調至目前55分，雖然未見反彈，但評分已有一定減幅，於第四班作賽有輕微評分優勢。]"

h3["interaction_matrix"] = {
  "SYN": "無",
  "CON": "無",
  "CONTRA": "無"
}

h3["fine_tune"] = {
  "direction": "無",
  "trigger": "",
  "channel_a": "",
  "channel_b": ""
}

h3["override"] = {
  "rule": ""
}

h3["core_logic"] = "川河石駒近6仗全未能上名（5-4-5-10-6-8），且晨操指標偏弱（體能維持=60，有「操練放緩」標記），反映狀態未及水準。今仗排13檔極端不利（勝率4%），配上布浩榮兼無積極出擊訊號。儘管L400約22.99秒造出平穩段速，並擁有極強賽績線（強組比例9/12）及評分下調優勢（64落到55分），但在劣檔及狀態平平下，不宜高估。"
h3["advantages"] = "1. 賽績線極強（強組比例9/12），過往對手其後出賽表現出色，證明曾與強手交鋒。\n2. 評分由64分累積下調至55分，於第四班作賽已儲蓄一定評分減幅優勢。"
h3["disadvantages"] = "1. 今仗排13檔極端不利，過往勝率僅得4.0%，加上預期快步速，形勢惡劣。\n2. 晨操出現「操練放緩」風險，且近6仗（5-4-5-10-6-8）全未能上名，狀態欠佳。"
h3["evidence_step_0_14"] = "done"

with open("2026-05-03_ShaTin/Race_4_Logic.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
