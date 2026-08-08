# AU scoring-matrix restart and archive-alignment follow-up (2026-08-09)

## Direction

今輪按用戶方向，明確唔做「保住 Top 2、只執第 3/4 slot」rerank。所有實驗都由
horse ability evidence／scoring matrix 本身出發；比較基準係已加入
`performance_quality_score` 嘅 805 場 current-runtime snapshot。

## Matrix diagnosis

現役主要能力訊號喺完整 805 場嘅 feature-alone within-race AUC：

| Signal | All | 1–8 runners | 9–12 | 13+ |
|---|---:|---:|---:|---:|
| stability matrix | 0.6226 | 0.6265 | 0.6232 | 0.6196 |
| jockey/trainer matrix | 0.6273 | 0.6427 | 0.6280 | 0.6184 |
| performance quality | 0.6124 | 0.6288 | 0.6106 | 0.6075 |
| form | 0.6105 | 0.6134 | 0.6149 | 0.6012 |
| official rating | 0.5848 | 0.5972 | 0.5682 | 0.6081 |
| pace-performance matrix | 0.5891 | 0.5951 | 0.5814 | 0.5998 |

大場表現差唔係因為 matrix 冇 spread 或某一條主訊號變成常數；係同一批能力訊號
喺 13+ runners 場更難分開第三匹上名馬。Rating／pace 喺大場反而相對更有用，唔支持
用 field-size rerank 去鎖 slot。

## Structural performance-quality experiments

以零改動必須 rank-exact 嘅 differential harness，固定 production observed cohort
（887 horses／98 covered races）測試：

- historical field-size credit (`log2(starters / 10)`)：development 同 terminal day
  方向反轉；較大 credit 全面變差；reject。
- beaten-margin distance scaling (`margin × (1400 / distance)^gamma`)：大場 AUC 有改善，
  但 terminal Pass／winner@3 下跌；reject。
- target-distance weighted run quality：development 有輕微改善，但 terminal
  Gold／Good／Pass 或 AUC 不穩；reject。

結論：`-margin + 4 × log10(prize/50000)` 保持簡單版本，唔疊 starters／途程參數。

## Research archive alignment bug

七個 research tools 仍然假設 meeting 係 `root / meeting_name`，完成後移入
`Archive/` 嘅場次會靜靜消失。舊 unused-feature scan 因此只讀 684 場。

新增共用 `sb_backfill_archive.scored_meeting_index()`：

- recursive discover `Meeting_Auto_Scoring.csv`；
- 現場見到 122 meetings，其中 34 個喺 `Archive/`；
- 同名 direct／archive snapshot 直接 fail，禁止靜默揀一份；
- unused-feature、candidate-dimension、feature-A/B、leaf-power、people-going、
  dump-leaves、leaf-substitute 全部共用同一 resolver。

修正後 feature scan 由 684 升至 955 場；candidate evaluation 有 942 場可用。

## Leakage guard

完整 scan 一度見到 `Ave $` AUC 0.635、`up_place_rate` 0.582，但兩者來自 Sportsbet
career overview。同一 overview 嘅 J/H、WinRange 已有逐匹證據會包含 target race；
所以 outcome-derived `Ave $` 同 1st/2nd/3rd-up record 一律禁止用作歷史驗證。
Live report 可以顯示，但唔可以用 post-race archive 證明預測力。

保留嘅候選必須由已按日期截斷嘅 run rows 重建：

- `dist_place_rate`：942 場，62% runners 有值；terminal Gold -0.70pp、
  champion -0.70pp，reject。
- `jh_pre_place_rate`：942 場，28% runners 有值；terminal Gold +0.70pp、
  Good +1.41pp、Pass +1.41pp，但 champion／winner@3 無升，覆蓋稀疏，未通過
  現行 promotion gate；保留 research-only，唔入 production。

再用 current-runtime snapshot 保存嘅 point-in-time 正式策騎／上名 counts，測試將
`jockey_horse_fit_score` 改成 empirical place-rate（prior 0.457；shrink K 2/4/8；
blend 25/50/75/100%）。12 個候選喺 development 594 場嘅 Top-5 AUC 全部負數
（-0.0008 至 -0.0038），Pass／Top-3 precision／winner@3 普遍同跌，毋須打開
terminal holdout。Standalone AUC 較高並不代表有 incremental value；現役 fit 保留。

## Career identity misalignment

新 Sportsbet Racecard 寫 `Career: 45 : 5-7-7`。舊 parser 只截到 `45`，下一層又要求
數字後面即刻有 `:`，結果 805 場入面：

- 947 runners 被錯標 `DEBUT`；
- 其中 945 runners 明明已有正式賽績；
- 問題集中 2026-08-05 至 2026-08-07。

修正：

- Racecard parser 保留完整 career record；
- Facts／builder／runtime parsers 同時接受完整 record 同 integer-only legacy value；
- 1–5 starts 正確標 `EARLY_CAREER`；
- 已有正式賽績但 Racecard 冇 Last 欄，唔再寫「初出馬」；
- explicit stale `DEBUT` 唔可以蓋過非零 career starts。

完整 805 場真引擎 A/B：Gold、Good、Pass、champion、winner@3、winner@5、Top-3
precision 全部 **0.00pp**；45 runners 分數改動、6 races rank 改動，Top-5 AUC
`-0.000071`。呢個係 identity／narrative correctness fix，唔列作 performance gain。

另測試移除 mature-career class heuristic：Good +0.25pp、champion +0.12pp，但
all/dev/holdout AUC 都向下，已撤回，唔 ship。

## Current conclusion

Production ranking 保留 performance-quality upgrade；本輪冇新增 rerank 或 matrix
參數。最有價值嘅改動係修正 archive research population、封鎖 mutable overview
leakage，同修正 947 匹 career identity。下一個真正有機會再提高 Gold／Good 嘅方向，
仍然係新增 point-in-time、可重播而且同現有 form/rating/PF 正交嘅能力 evidence，
例如完整 trip-adjusted sectionals 或 opponent-strength normalization。

## Legacy coverage and ability-peak follow-up

再獨立測試「舊 Formguide 冇 `starters` 欄就完全唔用」係咪過度保守。只保留嚴格
`run_date < meeting_date`、header margin、正數 prize，候選覆蓋由 98 場擴到 408 場。
完整 805 場雖然 Top-5 AUC `+0.00519`、Pass `+0.99pp`、winner@3 `+2.24pp`，但
Gold `-0.37pp`、champion `-0.37pp`，早／中／後三個時間窗亦唔一致；0.25／0.50／
0.75 blend 全部仍然令 Gold 下跌。按 Gold／Good 優先閘，**reject**，完整 schema gate
保持不變。

為免平均近績只量到「穩定」而唔係「能力上限」，亦測咗最近四仗最好一仗（max）同
最好兩仗平均（top-2 mean）：

- max 喺現役完整證據 cohort：Top-5 AUC `-0.00326`，Gold／Good／Pass 全跌；
- top-2 mean 喺現役 cohort：Top-5 AUC `-0.00118`，Gold／Good／Pass 全跌；
- 擴闊 legacy coverage 後 top-2 mean 全樣本只有 Gold `+0.12pp`、Good `+0.50pp`，
  但 Pass `-0.12pp`，三段時間窗方向不穩，bootstrap CI 跨 0。

所以冇以「peak ability」名義偷偷換走穩定、可重播嘅 recency-weighted mean。最新完整
舊版對比（career identity correctness fix 一併計入）係 Gold `+0.87pp`、Good
`+0.87pp`、Pass `+1.37pp`；Top-5 AUC `0.68640 → 0.69276`，paired bootstrap
CI `[+0.00296, +0.00982]`。全套 regression：**438 passed**。
