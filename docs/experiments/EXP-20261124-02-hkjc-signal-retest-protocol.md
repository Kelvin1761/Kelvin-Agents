# EXP-20261124-02 預先登記 — HKJC：新 base（表現數字＋初出馬）下逐個後置組件重測

- 日期：2026-11-24｜Kelvin：「全面重測先」「新標準下所有訊號要唔要再測、有冇調整」
- 寫喺任何結果之前。工具：`patches/hkjc_signal_retest/`（run_offs.sh、analyse.py；Terra 寫、Claude 核對）。
- base = 現行 main 回放（`hkjc_history_replay_eval.py run`，全部組件開，表現數字＋初出馬練馬師已上線）。

## 組件（9 個）
上仗賠率 market_history、檔位×跑法 draw_style、事件報告 incident_history、大幅增程 distance_move、轉場 surface_move、
連續藉口 excuse_streak、薄證據收窄 thin_evidence、同程上名場地 venue_distance、馬齡 horse_age。
（表現數字、初出馬練馬師 2026-11-23 先喺同一 base 判過，唔重做。）

## 每個組件
1. 移除：關掉嗰個組件（`ENABLED = False`）重跑回放；v5.2 判 dev、holdout（off − base）。
2. 幅度重 fit：c = base raw − off raw（場內置中）；β 逐季 walk-forward（季 s 只用 2019 ≤ 季 < s，logistic L2 C=0.1，同 J3）；
   cand = base raw + β·c（β > 0 = 加大、β < 0 = 縮細、β = −1 ≈ 剷走）；v5.2 判 dev、holdout。
   walk-forward 會用之前季（包括早過嗰季嘅 holdout 季）fit 後面季，冇未來資料；所有回放實驗一路都係咁。

## 判（寫死）
- **剷走候選**：移除喺 dev 同 holdout 都 v5.2 PASS（即移除反而好）而且兩窗頭二入頭三 Δ ≥ 0。
- **調幅度候選**：重 fit 喺 dev 同 holdout 都 v5.2 PASS 而且兩窗頭二入頭三 Δ ≥ 0。
- 其餘：維持現行。候選唔會自動上線 —— Sol 覆核 leakage／結論之後，Kelvin 決定。
- 每個組件 2 個比較 × 9 = 18 個檢定；報告會寫明呢個多重比較。
