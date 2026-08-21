# 實驗索引

最新喺上面。一行一個實驗。

| ID | 日期 | 平台 | 假設 | 決定 |
|---|---|---|---|---|
| [EXP-20260821-06](EXP-20260821-06-au-race-shape-contribution.md) | 2026-08-21 | AU | `race_shape` 回測價值大部分係檔位矩陣洩漏造成 | **KEEP**（污染界線改正為 08-09；真乾淨 403 場 6/7 指標升）|
| [EXP-20260821-05](EXP-20260821-05-audit-followup-fixes.md) | 2026-08-21 | AU+HKJC | 審計後續：`racing_data_health` AU 分支每匹馬報 3 個假警報（test 自己鎖死個 bug）、場數指標加馬群分層、退役工具加閘、長期紅 test 修好 | KEEP |
| [EXP-20260821-04](EXP-20260821-04-au-draw-field-size-scaling.md) | 2026-08-21 | AU | 按馬匹數縮放檔位修正（實測訊號 5-8 匹 1.6pp vs 12-14 匹 10.7pp）可改善排名 | **REJECT** |
| [EXP-20260821-03](EXP-20260821-03-au-pace-map-gradient.md) | 2026-08-21 | AU | `race_shape` 場內 SD 低係因為 `pace_map_score` 係 4 級階梯；階梯粒度啱，但修正幅度冇按馬匹數縮放 | 診斷完成（候選見 EXP-04 → REJECT） |
| [EXP-20260821-02](EXP-20260821-02-au-gain-weight-joint-refit.md) | 2026-08-21 | AU | 重擬顯示尺 gain 並同步重 fit 權重，可令權重＝影響力並救活「啞」維度 | **REJECT（兩個候選）** |
| [EXP-20260821-01](EXP-20260821-01-au-archive-corpus-blindspot.md) | 2026-08-21 | AU | `Archive/` 令 49.1% 已評分場次對所有評估工具隱形；stale-baseline 警告本身係假警報 | 待決定 |
