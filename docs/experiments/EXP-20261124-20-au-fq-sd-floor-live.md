# EXP-20261124-20 AU 近績質素分場內 SD 下限（F1）上線＋退回監察 forward

- 日期：2026-11-24　平台：AU　類型：上線（Kelvin 2026-11-24「go ahead and do all」）＋ forward 退回監察
- 證據來源：EXP-20261123-06（喺 live `fcedd248` 重建，log-loss 尺 v2 PASS）；原候選 EXP-20261111-31 F1。

## 改咗乜

`au_racing_engine/stability.field_z`：場內 z 嘅除數 = max(場內 SD, **0.3065**)。0.3065 喺 EXP-20261111-31 量度前凍結、
只用賽前 raw，冇由賽果 fit，唔准調。`WC_AU_FQ_SD_FLOOR_LIVE=0` 回退。引擎喺 `stability_detail.form_quality.sd_floor`
記低用咗嘅下限；分析頁「近績質素分」拆解喺細 SD 場註明「成場差距細，用下限計」。

## 上線前證據（EXP-20261123-06，v2）

| Δlog-loss [95%] | 場內 AUC Δ [下界] | Gold Δpp | Good Δpp | 頭二選有中 | Holm |
|---|---|---|---|---|---|
| −0.00171 [−0.00225, −0.00120] | +0.0013 [+0.0001] | +0.17 | +0.26 | +0.28 | <0.001 |

## 上線核實（2026-11-24）

- 11-2x 歸檔：2,242 匹有場內 z 嘅馬，1,307 匹（58%，138／236 場）場內 SD 低過下限 → 影響面大。
- Ballina 11-23 scratch 重評分（下限關 vs 開）：64 匹 47 匹近績質素分變、8 個名次變、頭二選組合 8 場都冇變。
- `golden_scoring --platform au`：120 匹一致 —— golden 係凍結 feature vector，唔經 leaf 計算，所以預期唔變（唔係冇接通，上面重評分證實接通）。
- forward 腳本喺舊 code 評分嘅場次重砌「冇下限」分 = 已存分，0 匹差 ≥0.005（重砌公式正確）。
- `data_contract --calibrate` 重做（引擎指紋 1989f272ac80）。

## Forward（退回監察，預先登記）

`au_wong_choi_auto/scripts/au_fq_floor_forward.py`，scheduler `step_fq_floor_forward`，`au_forward_tracker` `fq_floor`。
- baseline = 上線 feature 但 `form_quality_score` 用 `stability.score_without_floor` 重砌；candidate = 上線版；兩邊 `exact_score`。
- 2026-11-25 起、只計新 code 評分（有 `sd_floor`）嘅場次；夠 1,000 場用 log-loss 尺 **v2** 判一次並凍結。
- 之前場次只做 walk-forward 校準、**唔計分**（佢哋 Δ = 0，計入會稀釋 Δ、令護欄更易過 = 更難建議回退；Sol 發佈前覆核搵到，已改）。
  機制驗證：假設 START = 11-15，4,260 場入面只計 381 場 forward。
- 引擎喺建 `form_quality` detail 時就記 `sd_floor`（海外代理／fallback 都有），海外代理同大爛地 forward 嘅
  `score_without_proxy` 跟返評分時嘅下限（冇呢欄 = 舊 code = 冇下限），所以舊 forward 嘅 baseline 唔會靜靜郁。
- 上線版 Δlog-loss CI 下界 > 0 或者 AUC 護欄唔過 → `rollback_recommended`（建議 `WC_AU_FQ_SD_FLOOR_LIVE=0`，Kelvin 決定）。

## 已知限制

- EXP-20261123-06 嘅 dump 用 live `fcedd248`；之後如有改動令同一份語料嘅 baseline 唔同，forward 先係準。
- 落注策略（位賠 ≥2）嘅選注會跟住頭兩選郁；呢個改動唔係為咗落注 ROI，亦冇證據會改善 ROI。
