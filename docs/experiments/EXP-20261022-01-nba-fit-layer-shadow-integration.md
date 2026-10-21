# EXP-20261022-01 NBA 擬合機率層 shadow 接駁（只記錄，唔影響任何選擇）

- **日期**：2026-10-22
- **平台**：NBA
- **目的**：將 EXP-20261021-05 嘅 (A)（Poisson/NB＋per-stat logistic 重校準，`nba_fit_layer_A_v1`）以 **shadow 欄位** 接入 live pipeline，累積前瞻證據。**唔係**採納，冇利潤聲稱，冇對 live 模型改善嘅聲稱。
- **搜索過嘅舊記錄**：EXP-20261021-01（hybrid ML shadow）、EXP-20261021-05。
- **改動**：`nba_extractor.compute_fit_inputs`（同季常規賽、MIN>0、嚴格早過賽事 US 日；唔含上季／季前賽／季後賽）、`generate_nba_reports.compute_shadow_fit`、sidecar legs、`nba_market_ledger.record_snapshot`（欄位入 model_obs，**唔入** `MODEL_VARIANTS`）。
- **旗標**：`NBA_FIT_LAYER_SHADOW_ENABLED`（預設 1＝計算；0＝關）。每 leg try/except、`FIT_STATUS` 計數、報告 header 一行。冇任何代碼讀取該值。
- **規則**：≥10 同季常規賽出場且 prior-10 平均 MIN ≥20，否則 null＋原因（`insufficient_same_season_games`／`low_minutes_out_of_population`／`no_gamelog`／`no_fit_inputs`／`artifact_invalid`／`invalid_inputs`／`error`）。驗證線（最近 prior-10 平均嘅 3 個整數）以外照計，狀態 `ok_outside_validated_lines`（連 mu、l10_mean、line_minus_mean 一齊記）。預計首批非空約 11 月 6–15 日。
- **驗證（離線）**：NBA suite 240 passed；11 場／401 leg 存檔（注入合成 fit_inputs 令計算路徑行）shadow 開 vs 關：報告 md 除 header 一行外逐字相同 11/11；sidecar 除 shadow 欄位外相同 11/11（leg 機率、選腿、組合不變）。
- **未驗證**：冇真實 `fit_inputs`（舊存檔冇）；ok 與 outside 比例（155／246）只反映合成輸入；生產 extractor 新欄位要睇首批真實 run。
