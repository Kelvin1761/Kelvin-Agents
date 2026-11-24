# EXP-20261124-50 預先登記（2026-11-24，睇結果之前寫）—— AU 初出馬「練馬師初出馬上名率」

- 來源：HKJC EXP-20261123-13（DT，dev／holdout／六季初出馬場全 PASS，上線）。AU 未試過；EXP-20261105-07 證實
  AU 初出馬之間排序差市場（AUC 差 0.08）。
- 初出：Logic `career_race_starts == 0`（先 `refresh_career_starts` 由 facts 重抽，避開 EXP-20261105-08 過期值）。
- 事件：語料所有場次（`corpus_paths`，連 Archive）嘅初出馬 →（日期, 練馬師 norm, 入頭三 0/1）；名次來自 `AU_Historical_Raw_Race_Results.csv`
  （同 forward 腳本一樣嘅 `choose_track_rows` 配對）。練馬師名來自 Logic（今仗同事件同一來源）。
- 率（as-of，只計賽日**之前**事件）：r = (入位 + p0·k) / (出賽 + k)，k = 10（同 HKJC）。
- 常數（只用 2026-08-05 **之前**嘅事件計，判決窗之外）：p0 = 嗰段初出馬入頭三率；z = (r − 均) / SD，均／SD 用嗰段每匹初出馬嘅 as-of r。
- 入分：只限初出馬，z 場內置中（非初出 = 0）；β walk-forward（`au_perf_rating/judge.fit`，每賽日只用之前賽日，頭 20 日 β = 0）。
- Arm：**DT**（單一 arm，Holm 家族 1）。
- 尺：AU log-loss v2（`au_logloss_ruler.evaluate` 預設），語料 = 現行 live BASE dump（含 F1、速度分），2026-08-05 起。
  另報（唔係閘）：只計有 ≥1 匹初出馬嘅場次；初出馬之間 AUC 變化。
- 唔會因結果改 k、p0 計法、初出定義或者常數窗。
