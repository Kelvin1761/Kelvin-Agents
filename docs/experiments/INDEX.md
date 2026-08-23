# 實驗索引

最新喺上面。一行一個實驗。

| ID | 日期 | 平台 | 假設 | 決定 |
|---|---|---|---|---|
| [EXP-20260823-01](EXP-20260823-01-au-correct-gold-retest.md) | 2026-08-23 | AU | 08-22 全日用錯 `gold` 定義（用咗「頭馬喺 top-4」而唔係「真前三全部喺 top-4」）；用正確定義重測 | **REJECT ×10**（「gold 升」嘅好處全部消失，幾個變顯著蝕）；`--obj place` **KEEP**；負磅加法版 NEEDS MORE TESTING |
| [EXP-20260822-04](EXP-20260822-04-au-thin-evidence-rail.md) | 2026-08-23 | AU | 單一 leaf 預設影響量唔到，但**多因子計數**量得到：首選唔應該由「冇證據」撐起 | **KEEP**（首選上名 +1.70pp [+0.15,+3.36]✅、首選頭馬 +1.39✅、四個上名指標結構上零成本；10 個變體冇一個贏）|
| [EXP-20260822-03](EXP-20260822-03-au-refit-and-wet-overlay.md) | 2026-08-22 | AU | 名次修好後重 fit 權重可收返綜合打和；濕地 overlay 值得獨立審視 | **NEEDS MORE TESTING**（603 場冇 power；overlay 五個修法全打和）|
| [EXP-20260822-02](EXP-20260822-02-au-late-fade-scoring.md) | 2026-08-22 | AU | 末段跌位（PI）落到排名分可修 Gunroom 型個案 | **REJECT**（ρ +0.26 對全模型；安全欄符號逐 rank 調轉）|
| [EXP-20260822-01](EXP-20260822-01-au-unplaced-run-placings.md) | 2026-08-22 | AU | 未上名嘅仗名次被讀成輸距，一律當中性 60，令「末段跌位」結構上冇得表達 | **KEEP**（5 個 leaf 顯著變好、無倒退）；⚠️ 08-23 補：`finish` token 嘅 cache 回測無效（頁面封頂 10 條，賽後抓取令歷史被截 7.5%），排名效果只能向前量 |
| [EXP-20260821-06](EXP-20260821-06-au-race-shape-contribution.md) | 2026-08-21 | AU | `race_shape` 回測價值大部分係檔位矩陣洩漏造成 | **KEEP**（污染界線改正為 08-09；真乾淨 403 場 6/7 指標升）|
| [EXP-20260821-05](EXP-20260821-05-audit-followup-fixes.md) | 2026-08-21 | AU+HKJC | 審計後續：`racing_data_health` AU 分支每匹馬報 3 個假警報（test 自己鎖死個 bug）、場數指標加馬群分層、退役工具加閘、長期紅 test 修好 | KEEP |
| [EXP-20260821-04](EXP-20260821-04-au-draw-field-size-scaling.md) | 2026-08-21 | AU | 按馬匹數縮放檔位修正（實測訊號 5-8 匹 1.6pp vs 12-14 匹 10.7pp）可改善排名 | **REJECT** |
| [EXP-20260821-03](EXP-20260821-03-au-pace-map-gradient.md) | 2026-08-21 | AU | `race_shape` 場內 SD 低係因為 `pace_map_score` 係 4 級階梯；階梯粒度啱，但修正幅度冇按馬匹數縮放 | 診斷完成（候選見 EXP-04 → REJECT） |
| [EXP-20260821-02](EXP-20260821-02-au-gain-weight-joint-refit.md) | 2026-08-21 | AU | 重擬顯示尺 gain 並同步重 fit 權重，可令權重＝影響力並救活「啞」維度 | **REJECT（兩個候選）** |
| [EXP-20260821-01](EXP-20260821-01-au-archive-corpus-blindspot.md) | 2026-08-21 | AU | `Archive/` 令 49.1% 已評分場次對所有評估工具隱形；stale-baseline 警告本身係假警報 | 待決定 |
