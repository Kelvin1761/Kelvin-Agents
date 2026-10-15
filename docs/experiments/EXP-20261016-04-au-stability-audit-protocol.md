# EXP-20261016-04 預先登記：AU `stability` 三項量度

> 喺睇任何數字之前寫。三項都係**量度／診斷**，唔改模型、唔上線。
> 結果另寫：`EXP-20261016-04-au-stability-audit-results.md`。

- **日期**：2026-10-16
- **平台**：AU
- **起因**：用戶逐個維度覆核公式；`stability` 揀咗三項先查。
- **baseline**：production F6a（`claude-au-paceperf-20261015` head `3903102b`；
  `stability` 部分同 origin/main 一樣）。
- **舊記錄**：EXP-20260903-01（死班次乘數：K1 中和 REJECT，K2／K3／K4 因 dev 窗 0% 標籤
  **測唔到**）；EXP-20260822-01（未上名仗）；memory `au-adjustment-direction-audit`、
  `cohort-cells-are-not-term-evidence`、`au-class-label-only-exists-in-holdout`。

## 語料

研究 dump（同 production dump 同一評分路徑），另外逐匹記低：近績分實際用嘅最近 4 場正式賽
（名次、出賽數、`source_race_class`、日期、負距、獎金），今場班次標籤，同 −4 規則有冇觸發。
判斷窗：乾淨窗 2026-08-05 起；evaluable 場次規則同 canonical 一樣。

## M1 真班次欄覆蓋率（只量，唔測候選）

- 近績分計分行（每匹最近 4 場）有 `source_race_class` 嘅比例，按**目標賽日**逐月同逐週報。
- 解析得到 tier（`_get_class_tier` 唔係落 fallback 7）嘅比例；標籤分佈。
- 計「完全覆蓋賽日」：該日 ≥ 95% 計分行有可解析標籤。
- **門檻（決定之後開唔開 K2 候選登記）**：連續完全覆蓋賽日 ≥ 30 日 → 可以另開 K2 登記；
  否則記低預計幾時夠。今次**唔跑** K2。

## M2 −4 規則方向審計

規則：`form_score ≥ 72 而且 class_score < 60 → form_score − 4`（`analyze_horse`）。冇 A/B 記錄。

- **term ablation（主）**：離線將觸發馬嘅 form_score 加返 4，用 production 算術重算 ability，
  其餘不變。v3 `fixed_rule` 全紀錄判決（乾淨窗；冇 fit）。**方向**：剷走後 primary 點估計
  ≥ 0 而且 ranking 唔差 → 規則冇幫手或方向錯；剷走後 primary < 0 → 規則有用。
- **描述（副）**：觸發馬 vs 未觸發但 form ≥ 72 嘅馬，場內超額入位率（實際入前三 − 3／馬匹數），
  賽日 bootstrap CI。只作描述，唔用嚟判方向（組合格唔係單項證據）。
- 報觸發率同觸發馬平均名次。

## M3 頭馬贏幾遠有冇資訊

而家 `performance_quality` 每場 `quality = −min(20, 負距) + 4·log10(獎金/50,000)`，
頭馬負距一律 0，贏一個鼻位同贏 5 個馬位計法一樣。

- 頭馬贏距 = 同一場（場地、日期、場號、路程）**第二名**嗰行嘅負距，由全語料 Formguide 搵；
  搵唔到 = 未知。
- **覆蓋**：PQ 計分行之中頭馬行嘅比例，同其中知道贏距嘅比例。
- **候選 leaf（固定，唔調）**：頭馬 `quality = +min(20, 贏距) + 班次項`；未知贏距照舊 0；
  非頭馬唔變。用 `_performance_quality_digest` 同一條式（recency 權重、最少 2 場、場內 z、
  60 + 20z）。
- **指標**：leaf 層面場內配對 AUC（同 EXP-20261016-01 一樣：同一個 replica、按賽日 bootstrap
  2000、seed 7），候選 PQ′ − 現行 PQ。另報只計「最少一場計分頭馬行知道贏距」嘅馬。
- **停止規則**：知道贏距嘅頭馬行 < 50% → 只報覆蓋，**唔報 AUC 結論**（偏差樣本）。
- 唔做排名 A/B；leaf 贏咗都只係入圍，要另開 §8 登記。

## 唔准做

- 改 −4 嘅門檻或幅度、改贏距上限、揀子集救結果。
- 用 M1 嘅結果即刻跑 K2。
- 改評估把尺。
