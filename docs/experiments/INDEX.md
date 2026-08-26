# 實驗索引

最新喺上面。一行一個實驗。

| ID | 日期 | 平台 | 假設 | 決定 |
|---|---|---|---|---|
| [EXP-20260825-04](EXP-20260825-04-au-proven-class-overlay.md) | 2026-08-25 | AU | 高班次只有在當仗實際表現好時才應當成排名實績 | **USER-ACCEPTED EXPERIMENTAL KEEP**：dev +0.00305、4/5 folds 非負、holdout +0.00301，但 CI [-0.00066,+0.00680] 跨零；Gold +0.78pp、Good +0.23pp，用戶明確接受不確定性後啟用及向前監測 |
| [EXP-20260825-03](EXP-20260825-03-au-exact-class-performance-proof.md) | 2026-08-25 | AU | Sportsbet 精確歷史班次應否按該仗實際表現轉成「高班證明」signal | **PROMISING／暫不 ship**：鎖定 proven-class 候選 dev/holdout AUC 均 +0.0030、Gold +0.78pp、Good +0.23pp，但 holdout CI [-0.0007,+0.0068] 跨零；R2 Lovecats仍第8、DDE/Zubba仍第2/3 |
| [EXP-20260825-02](EXP-20260825-02-au-exact-class-pace-reliability.md) | 2026-08-25 | AU | Sportsbet 原始班次 transport 及低班次 race-level PacePerf 收縮可否修正 R2 | **Correctness KEEP／scoring REJECT**：保存 53,142 個原始班次 label 作 evidence；class_form dev/holdout 點估計正，但 holdout CI [-0.0043,+0.0082] 跨零，Lovecats仍第8、DDE/Zubba仍第2/3 |
| [EXP-20260825-01](EXP-20260825-01-au-poor-trial-pace-wet-interaction.md) | 2026-08-25 | AU | 已觀察差試閘時，正面 PacePerf／wet 應否收縮，令 Clear Proof 入 R1 Top 2 | **REJECT**：PF-half、wet-half、兩者合用喺 dev 頭5 AUC 全部精確 0；三者雖都令 R1 排成 Isawyou／Clear Proof／Gunroom，但 holdout 不開、唔准用單場答案上線 |
| [EXP-20260824-05](EXP-20260824-05-au-data-semantics-full-scan.md) | 2026-08-24 | AU | 全鏈掃描 Sportsbet→Facts→Logic→score→deploy 有冇語義錯、runner misalignment、leakage；Aeliana 試閘缺名次必修 | **Correctness KEEP／權重不變**：修 8 類問題；63,515 個完整 finish 100% 合法，active runner 5,239/5,239 對齊；trial 修正只改 12/1,411 場，Gold 不變、Gold Strict +0.071pp，holdout AUC 打和 |
| [EXP-20260824-04](EXP-20260824-04-au-winner-margin-semantics.md) | 2026-08-24 | AU | Sportsbet 頭馬勝距被當輸距；修正後需否重 fit | **Correctness KEEP / refit REJECT**：R9 恢復 Autumn Glow／Sheza Alibi Top 2；整體 Good -0.28pp、Pass +0.14pp；refit holdout AUC -0.0025、CI [-0.0062,+0.0012] |
| [EXP-20260824-03](EXP-20260824-03-au-sportsbet-pace-attribution.md) | 2026-08-24 | AU | Sportsbet race-level L600 只計正式賽輸距 ≤3L，會否變成較可信嘅逐駒 PacePerf | **REJECT**：holdout 頭5 AUC +0.0035、CI [-0.0040,+0.0110]；Pass / winner@3 -1.37pp；Randwick R1 Gunroom 仍第1、Clear Proof 反跌第3 |
| [EXP-20260824-02](EXP-20260824-02-au-prep-evidence-volatile-rail.md) | 2026-08-24 | AU | 休後狀態 × 證據厚度 × wet/pace 高波動支持可否只降 Gunroom 型首選 | **REJECT** — R1 可修成 Clear Proof／Isawyou／Gunroom，但三條件 dev 只觸發 1 場；較闊「休後＋高波動」holdout 頭五 AUC +0.0006，95% CI [−0.0003,+0.0016] 跨零 |
| [EXP-20260824-01](EXP-20260824-01-au-post-spell-poor-return.md) | 2026-08-24 | AU | 長休後復出未上名、短期內再跑應扣分（Gunroom 個案） | **REJECT**（holdout 頭五 AUC +0.0011，95% CI [-0.0012,+0.0036] 跨零）；撤回不完整 archived Logic 得出嘅「第1→第4」說法；另修正 reflector 將部分賽果誤當完整名單嘅排名污染 |
| [EXP-20260823-04](EXP-20260823-04-au-partnership-trainer-lookup.md) | 2026-08-23 | AU | 合夥練馬師名解析失敗（用戶提問觸發） | **KEEP** — 根因係 `&amp;` 冇 unescape 令 `amp` 留喺 key；合夥名成功率 **0% → 100%**，佔 runner 5.8% |
| [EXP-20260823-03](EXP-20260823-03-au-l600-standard-table.md) | 2026-08-23 | AU | L600 標準表向上取整（33.1% pf_runs 中招）＋ 41 處非單調條目 | **KEEP**（Gold +1.06 ✅、walk-forward 3/3 從未負）；試閘按生涯仗數條件剔走 **REJECT**（越剔越蝕）|
| [EXP-20260823-02](EXP-20260823-02-au-going-specific-overlay-and-pace-perf.md) | 2026-08-23 | AU | 濕地 overlay 按今日地況分離；pace_figure 多個明顯缺陷應該修得到 | 濕地分離 **KEEP**（Gold +0.62 ✅）；pace_figure 七個修法 + 三個分層 **全 REJECT**（佢係模型唯一正交輸入，ρ≤0.13）|
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
- [EXP-20260826-01](EXP-20260826-01-au-pace-perf-distance-crossover.md) — AU pace_perf：PF 同段速嘅判別力隨距離對調（>1600m 段速贏 +0.0589 ✅），但落到排名量唔到，NOT SHIPPED
- [EXP-20260826-02](EXP-20260826-02-au-pace-perf-weight-reverification.md) — AU pace_perf 權重重新驗證：五種量法都唔支持調低，兩次重 fit 反而想調高，保持 0.12205（REJECT）
- [EXP-20260826-03](EXP-20260826-03-au-randwick-0822-review-fixes.md) — 0822 Randwick 十場覆核：pace_perf display gain 喺污染語料上 fit（已修，排名不變）、weight_score 降班 nudge 方向調轉（已修）；兩個我自己量錯嘅發現已撤回
- [EXP-20260826-04](EXP-20260826-04-au-new-data-and-retired-dimensions.md) — WinningTime 速度評分（過 fold 閘、主裁判九個配置全部跨 0，覆蓋只 25%，已登記重測）；form_line / race_shape / sectional 三個退役維度復活全部失敗
