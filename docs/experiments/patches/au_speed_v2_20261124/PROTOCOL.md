# EXP-20261124-40 預先登記（2026-11-24，睇結果之前寫）

- 來源：EXP-20260927-02 WinningTime 速度分（`au_speed_venue_audit.runner_speed_best3`：今仗之前每仗
  「頭馬時間 + 輸距換算」對 point-in-time 場地×路程中位標準（≥10 場）同地況修正（≥40 場），每 km 秒；
  最少 3 仗，取最好 3 仗平均）。開發期 Gold +0.43 [+0.05, +0.86]；盲測 2,044 場舊尺（Stage 4 v2）判 REJECT
  （insufficient_ranking_metrics）。**唔追溯改判嗰個 forward** —— 呢度係喺現行 live 上嘅新候選。
- 語料：`au-rejudge-20261124/BASE.json`（現行 live 排名，含 F1），2026-08-05 起。
- 速度值：直接 call `au_speed_venue_audit.collect_reference_races`／`build_asof_standards`／`load_races`（同 forward 一樣嘅 code），
  按 (日期, 場號, 馬名 norm) 接去 BASE；冇速度 = 場內 z 0（同原定一樣）。
- Arm（Holm 家族 2）：
  - **S1 固定**：ability + 0.5 × 場內 z(speed)（原定 GLOBAL_SPEED_K，冇 fit）
  - **S2 walk-forward**：ability + β × 場內 z(speed)，β 每個賽日只用之前賽日 fit（`au_perf_rating/judge.fit`，頭 20 日 β = 0）
- 尺：AU log-loss v2（`au_logloss_ruler.evaluate` 預設）；PASS 仲要 Holm < 0.05。
- 洩漏：速度只用今仗日期之前嘅往績同標準（`run["date"] < target_date`、標準嚴格早過 D）；冇用賠率。
- 唔會因結果改 k、標準門檻或者最少仗數。
