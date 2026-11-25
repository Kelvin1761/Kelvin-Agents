# EXP-20261125-07 校準模型機率（shadow）同校準板

- 日期：2026-11-25　平台：AU／HKJC（機率）＋ NBA／Tennis（只入板）　類型：新工具（shadow，唔郁評分、唔上 dashboard）
- 起因：dashboard 只有排名同分數，冇「幾大機會入位」；而我哋講嘅機率（NBA、網球）準唔準亦冇一塊統一嘅板。
- 工具：`shared_racing/scripts/model_probability.py`、`shared_racing/scripts/calibration_board.py`；
  測試 `shared_racing/tests/test_model_probability.py`、`test_calibration_board.py`（17 個）。
- golden_scoring 冇郁；`au_racing_engine`／`hkjc_racing_engine` 一行都冇改。

## 定義（同判決尺同一條公式，唔另起一套）

| | 公式 | 來源 |
|---|---|---|
| 入頭三 | p = σ(a + α·(raw − 場均) + γ·logit(3/N)) | AU log-loss 尺 v2（`au_logloss_ruler._xy`／`_fit` 直接調用）；HKJC 回放尺 v5 |
| 獨贏 | p_i = softmax(β·(raw − 場均)) | `market_ruler.py` 淨模型部分同一形狀（條件 logit），β 一維 Newton |

- AU raw = 已發佈 `ability_score`（= `au_eval.default_scorer` 嘅 live ability）。
- HKJC raw = 已發佈 Logic 嘅 `ability_score_raw`（回放尺用嗰個，唔係顯示用嘅 `ability_score`）。
- **logit(3/N) 兩邊唔同，刻意各跟自己把尺**：AU = `log(3/max(N−3, 1e-9))`（同 AU 尺 bit-identical）；
  HKJC = v5 `field_logit`（N ≤ 3 當 N = 4）。N ≥ 4 完全一樣，只係 ≤3 匹嘅場唔同（AU eligible 要 ≥3 匹入三甲，
  3 匹場 AU 尺會畀 logit ≈ 21.8，即係「一定入」—— 啱嘅）。
- 參數寫 `<資料根>/<AU|HKJC>_Prob_Calibration.json`：`{model_id, fit_until, n_races, n_days, a, alpha, gamma, beta_win, status,
  reference_all_models, model_changed_from?}`。

## 防洩漏

1. **只用目標日之前嘅賽日 fit**（嚴格 <，目標日本身都唔用）；頭 20 個賽日只做訓練。測試：加未來日子，過去參數一個 bit 都唔變。
2. 輸入係**賽前已發佈**嗰份（`unified_reflector_core.select_prerace_snapshot`，同覆盤／失手體檢一樣；快照經
   `wongchoi_paths.prediction_snapshot_dir`）。冇快照嘅舊場次照 reflector 慣例用 meeting 目錄（`sources` 有數）。
   外置碟冇掛載 = 嗰個場次跳過（`offline`），唔會靜靜用賽後版本。
3. `live_record_exclusions` 場次唔計（HKJC 2026-10-07 跑馬地）；AU 亦跟 `corpus_paths` 剔 `au_corpus_exclusions`。
4. 預測唔齊（有賽果嘅馬冇預測）成場唔要，唔好靜靜令 N 細咗。
5. **賠率唔入模型**；收市價只喺校準板做對照。HKJC 冇用今仗賠率（AGENTS.md）。
6. **model_id**：AU = `au_golden:<scoring_golden.json sha256 頭 16 位>`；HKJC = `SCORING_CONTRACT_VERSION`。
   只用現行模型數據：HKJC 逐匹睇 Logic 記低嘅 `scoring_contract_id`；AU Logic 冇記模型版本，用 golden 最後一次改動嘅
   commit 時間做分界（快照 `created_at` 要遲過佢）。未夠 20 日 = `insufficient`（參數 null），另附
   `reference_all_models`（混埋舊模型，只供參考）。已知限制：golden 唔包 overlay（騎練剩餘、獎金、速度分），
   overlay 改動唔會觸發換 model_id。

## 第一次跑（2026-11-25，真數據，寫去 scratchpad，未寫入生產位置）

參數（目標日 = 今日）：
- AU：`insufficient` —— 現行 golden（2026-11-05 起）得 19 個賽日、845 場（差一日）。
  參考（全部模型 112 日、4,566 場）：a −0.0079、α 0.0818、γ 1.106、β_win 0.0804。
- HKJC：`insufficient` —— 現行 contract 得 13 個賽日、127 場。參考（21 日、205 場）：a −0.023、α 0.159、γ 1.069、β_win 0.170。
  HKJC 已發佈 Logic 有 `ability_score_raw` 嘅場次只得 21 個賽日，所以未來幾個月都會係 insufficient；
  要早啲有就要用回放語料（現行 code 重評）fit —— 未做，見跟進。

校準板（walk-forward，每日重 fit，混模型版本）：

| domain | 樣本 | 模型 log-loss | 同一批去水市場 | 備註 |
|---|---|---|---|---|
| AU 入頭三 | 3,787 場／36,203 匹（08-25 → 11-24） | 0.5569 | 0.5085（Harville） | 0.4–0.8 段高估 2–5pp（0.7–0.8：預 74.2%、中 68.9% [65.7, 71.9]）；低段準 |
| AU 獨贏 | 36,128 匹 | 0.3036 | 0.2721（power） | 市場明顯好過模型（同 EXP-20261124-90 一致） |
| HKJC | 11 場（得 1 個計分日） | 0.479／0.240 | 0.431／0.212 | 樣本太少，全部桶 n<50 |
| Tennis all | 30,083 注 | 0.6149 | 0.5720（`market_prob_fair`） | 0.8–1.0 段高估 7pp |
| Tennis 精選 | 174 注 | 0.7959 | 0.6545 | 平均預測 64.3%、實際 39.1% —— 精選係揀咗「模型最高估」嗰批 |
| NBA | 19,888 腿（讀 `reliability_latest.json`，唔重計） | —（來源冇 log-loss） | 收市原價 gap +4.1pp | 整體 gap −0.5pp；0.9–1.0 段預 94.6%、中 92.2% |

## 排程（shadow，失敗唔影響 run）

- AU evening：賽果摺入 → `step_trainer_residual_table` → shadow 步驟最後 `step_calibration_shadow`
  （`calibration_board.py --refit au`，timeout 1,200 秒，實測 ~2 分鐘）。失敗只記 step + log，**唔 `runlog.warn`**
  —— warning 會令 evening 變 partial（exit 75），同 a00ed9c6 一樣嘅教訓。
- HKJC postrace：賽果入庫後背景跑 `calibration_board.py --refit hkjc`（同段速表一樣 `Popen`；log 去 `calibration_shadow.log`）；
  測試中／`WC_DISABLE_CALIBRATION_SHADOW=1` 唔開。
- 冇加入 `job_freshness.py`：唔係 launchd job，係 evening／postrace 入面嘅 shadow step。

## 跟進（未做）

1. **第二個機率定義**：dashboard `Horse_Racing_Dashboard/backend/services/parser_au.py` 讀舊 Monte Carlo 嘅
   `predicted_place_odds`（`mc_simulator.py`）。今次冇剷；上 dashboard 之前要決定邊個係標準，另一個剷走
   （「一樣嘢只准有一個標準」）。
2. **Dashboard**：校準機率夠數（`status: ok`）之後先顯示，標「shadow／未入分」；校準板做一頁（每 domain 一張 reliability 圖 + CI）。
   要另外 Telegram 通知 Kelvin。
3. HKJC 用回放語料（現行 code）fit，避免等幾個月。
4. AU 入頭三中高段系統性高估 → 可以考慮非線性校準（例如 α 分段）—— 要過判決尺先講得改善。
5. AU model_id 考慮包埋 overlay 版本。

## 2026-11-26 上 dashboard（Kelvin「做 1-3」第 2 項）

- **一個標準**：機率只由 `model_probability.py` 計。dashboard `backend/services/model_prob_display.py` 只係調用
  `top3_probs`／`win_probs`（測試核對同一條公式）；舊 Monte Carlo（`mc_simulator.py`）2026-05 之後冇輸出，
  只喺舊場次顯示並標「舊版（2026-05 前）」。跟進 1 完成。
- **AU 馬匹卡**：總分旁邊「入位 X% · 獨贏 Y% shadow」chip，tooltip 寫明 shadow／未入分、fit 到幾時、用幾多賽日、
  以發佈時馬數計。條件：參數 `status == ok` 而且 `model_id` == 現行 golden（模型改咗未重 fit = 唔顯示）。
  純顯示：唔改分數／排名／grade（`test_attach_is_display_only`）。
- **HKJC**：參數仲係 `insufficient`（現行 contract 14 日），而且 raw 係 Logic `ability_score_raw`，未接 —— 唔顯示，唔扮有。
- **校準板**：Portfolio 頁「🎯 校準板」6 張 reliability 圖（AU 入頭三／獨贏、HKJC 入頭三、NBA 腿、網球全部／精選），
  每桶 Wilson 95% 區間、樣本 <50 淡色、同一批去水市場 log-loss 對照。`calibration_board_export.py` 只抄
  `<WongChoiControl>/calibration_board.json`，唔重計。跟進 2 完成（Telegram 另發）。
- 本機用真數據（11-26 Mornington 等 4 個 AU 場次）砌過：Mornington R1 8 匹，獨贏加埋 100%、入位加埋 ≈2.94，
  次序同分數一樣；手機 375px 冇橫向捲動。
