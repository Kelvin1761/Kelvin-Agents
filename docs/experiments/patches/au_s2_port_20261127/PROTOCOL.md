# EXP-20261127-02 預先登記（2026-11-27，睇結果之前寫）—— S2 移植去現行 live

- 來源：S2 forward（EXP-20261016-03 → EXP-20261127-01）ship_eligible：1,812 場未睇過，B1 vs B0 Gold +1.27 [+0.34, +2.16]。
  但係同 10-16 凍結引擎比；現行 live 加咗 C2 refit、F1、R2、老馬、練馬師剩餘表現、WinningTime 速度分（同一來源：頭馬時間＋輸距）。
  Kelvin 2026-11-27「要」移植並量。
- S2 leaf（原樣，EXP-20261016-02）：`pace_figure_score' = 0.5 × pace_figure_score + 0.5 × (60 + 10 × z(A_sb))`；
  A_sb = `scratch/au_sb_total_speed_20261016.compute_asb`（Sportsbet 往績頭馬時間 + 輸距 × 0.17 秒，`full_time_speed` 情境標準，
  場內 z；冇值 z = 0）。冇改公式。
- 語料：現行 live BASE dump（`au-debut-trainer-20261124/BASE.json`，main 10095812 code，含 F1、速度分），2026-08-05 → 11-23。
- Arm（Holm 家族 4），全部對 baseline = 現行 live：
  - **A**：S2 leaf、速度分保留、現行權重
  - **B**：S2 leaf、速度分剷走（S2 取代速度分）、現行權重
  - **C**：S2 leaf、速度分保留、`pace_perf` 權重 × 1.6389（凍結 B1／B0 = 0.177／0.108）
  - **D**：S2 leaf、速度分剷走、`pace_perf` 權重 × 1.6389
  綜合分一律 `au_walkforward_refit.exact_score`（先核對 baseline 重算 = dump ability）。
- 尺：AU log-loss v2；PASS 仲要過 Holm。另報 Gold／Good（v3 forward 用嘅主指標）同頭五 AUC。
- 揀法（預先講好）：PASS 嘅 arm 入面揀 Δlog-loss 最好；如果 B／D（取代速度分）同 A／C 打和（CI 重疊），揀取代版
  （一樣嘢一個標準 + 簡單）。冇 PASS = 唔上，記錄「同現行 live 重疊」。
- 唔會因結果改公式、權重倍數或者 arm。
