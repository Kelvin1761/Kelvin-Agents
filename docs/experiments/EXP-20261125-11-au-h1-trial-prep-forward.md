# EXP-20261125-11 H1 試閘＋備戰分加重：預先登記 forward（shadow）測試（AU）

- 日期：2026-11-25（登記＋凍結）　平台：AU　類型：**預先登記 forward／shadow**（唔郁 live 排名，golden 不變）
- 來源：EXP-20261125-06 H1 —— 試閘分 z≥1 模型殘差 +5.05pp [+3.69, +6.70]（覆蓋 9.4%）、備戰分 z≥1 +4.56pp [+3.49, +5.59]（覆蓋 17.0%），市場殘差 ≈ 0；
  power_precheck 3/3 PASS。**呢啲數字係 110 日 in-sample**，所以只可以喺凍結之後嘅新賽日確認，唔准喺同一批數據「證實」。
- Script：`.agents/skills/au_racing/au_wong_choi_auto/scripts/au_h1_forward.py`（`status`／`evaluate`）；
  一次性 fit：`docs/experiments/patches/au_h1_forward/fit_frozen.py`；凍結參數：`docs/experiments/patches/au_h1_forward/frozen.json`
- 測試：`.agents/skills/au_racing/au_wong_choi_auto/tests/test_au_h1_forward.py`（17 個）

## 假設

模型 ability 入面試閘分（`trial_score`）同備戰分（`preparation_score`）份量太細。市場已經定咗價（市場殘差 ≈ 0），
所以就算成立，都只係令模型**追近市場**（m3 追市場軌），唔係贏市場。

## 候選（2026-11-25 凍結，之後唔再 fit）

```
候選 ability = live ability + w_trial·z(trial_score) + w_prep·z(preparation_score)
z = 場內標準化：(x − 場均) / 場內母體 SD；SD < 1e-9 → 0（同 EXP-20261125-06 disagree.enrich 一樣）
```

fit（只做一次）：入頭三 logistic，同 `au_logloss_ruler` v2 校準同一個形狀，加兩欄一齊 fit：

`logit P(top3) = a + α·(ability − 場均) + γ·log(3/max(N−3, 1e-9)) + β_t·z_t + β_p·z_p`

用 `au_logloss_ruler._xy(version="v2")` 同 `_fit`。數據：BASE dump
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-debut-trainer-20261124/BASE.json`（sha256 `86c01ecb…5b7179`），
`eligible`（2026-08-05 起）、日期 ≤ 2026-11-25：4,260 場／40,938 匹／110 賽日。

| 參數 | 值 |
|---|---|
| a | −0.008907 |
| α | 0.081932 |
| γ | 1.126457 |
| β_trial | 0.065026 |
| β_prep | 0.110234 |
| **w_trial = β_t/α** | **0.79366 ability 分／場內 SD** |
| **w_prep = β_p/α** | **1.34543 ability 分／場內 SD** |
| （參考）冇 z 嘅 α | 0.085021 |
| in-sample 入頭三 ll（冇 z → 有 z） | 0.55189 → 0.55040（**in-sample，唔係證據**） |

換返 ability 分係因為判決尺自己會重 fit α；候選一定要喺 ability 尺度先公平。

**frozen.json sha256 = `b497ca53ef7ec786d12386d214d97e3fcf98acac619823ffc535684084380b1c`**
（`au_h1_forward.FROZEN_SHA256`；sha 唔對 `load_frozen` 即刻拋 `FrozenParamsChanged`；forward script 冇任何 fit 呼叫，測試用 AST 攔住）。

## 數據來源（防洩漏）

- 每個場次用 `unified_reflector_core.select_prerace_snapshot(meeting, "au")` —— 同覆盤、失手體檢、校準機率（`model_probability.py`，
  EXP-20261125-07）**同一個揀法**：悉尼時間賽日 **11:30 之前**最後一份已發佈快照；快照目錄經 `wongchoi_paths.prediction_snapshot_dir`
  （搬咗去外置碟都跟標記讀）。
- 讀快照入面 `Race_*_Auto_Scoring.csv`（`load_prediction_rows`）嘅 `ability_score`、`trial_score`、`preparation_score`。
  呢三個值係嗰日賽前 pipeline 寫低、manifest 有 sha256 嘅 append-only 快照，所以係**落注之前真係有**嘅資訊。
- **冇賽前快照嘅場次唔用**（唔會退返去 meeting 目錄 —— 嗰份可能係賽後重評）；快照 `created_at ≥ cutoff` 亦剔走；
  `evaluate` 見到任何唔係 `prerace_snapshot` 嘅場次就拋錯。
- 賽果：`find_existing_results_file` ＋ `load_structured_results`（名次、SP）。退出馬剔走；有結果但冇預測／冇 trial、prep 嘅場成場唔要。
  `live_record_exclusions` 嘅場次唔計。
- 試閘分本身嘅 as-of：試閘喺賽前發生，EXP-20261125-06 已註明；呢度冇加新欄位，只係用 live 已經用緊嘅 leaf。
- 賠率（SP）只係市場尺嘅評估基準，唔入候選。
- live 模型喺 forward 期間可能有其他改動上線：比較永遠係「當日 live ability」對「當日 live ability ＋凍結 shift」，所以公平。

## 開始日、樣本量（預先登記）

- **START_DATE = 2026-11-26**（凍結之後第一個賽日）。
- **目標：第一次同時夠 30 個賽日同 1,000 場**（`au_logloss_ruler.eligible` 之後）嗰日做 cutoff；只計 START_DATE ≤ 日期 ≤ cutoff。
  2026-08-05 → 2026-11-25 嘅快照場次（82 日／3,455 場）只做 walk-forward 校準 warm-up，**唔計分**。
  （候選喺呢段係 in-sample fit 過，令候選嘅校準 α 可能偏大 —— 如果 β 過擬合，forward 會更蝕，即係**對候選不利**，保守。）
- 快照語料大約每賽日 37–42 場，所以 30 日 ≈ 1,100–1,250 場，兩個門檻差唔多同時到。
- 功效（`power_precheck.py --platform au`，同模型無關嘅理想訊號 = 上限；BASE 截成 20 日 warm-up ＋ K 日計分，10 seeds）：

| 訊號 | K=30 日（1,032 場） | K=60 日（2,211 場） |
|---|---|---|
| 試閘 5pp × 9.4% | 7/10 PASS | 3/10 |
| 備戰 4.56pp × 17% | 6/10 | 6/10 |
| （EXP-06，全期 3,400 場、3 seeds） | 3/3 | |

  讀法：單一訊號喺 1,000 場左右係「邊緣」（60–70%）；K=60 唔高過 K=30 係因為每個 seed 嘅合成訊號實際大細唔同（CI 闊度由 ±0.0005 收窄到 ±0.00035，
  即係功效其實有升，只係點估計噪音大）。H1 係兩個訊號一齊（in-sample Δll −0.0015／匹，約理想單訊號嘅 2–3 倍），
  就算 out-of-sample 縮一半都仲喺把尺量得到嘅範圍。揀 30 日／1,000 場 = 一個月內有答案；
  **唔准因為結果邊緣而延長窗口**（換窗 = REJECT）。

## 判決規則（合約 m3 追市場軌，預先登記，判一次就凍結）

1. 排名尺：`au_logloss_ruler.evaluate(base, cand, version="v2")`，只計 forward 賽日（Δlog-loss CI 上界 < 0、AUC 護欄、贏 95% null）。
2. 市場尺：`market_ruler.evaluate(base, cand, price_key="sp", since="2026-08-05", score_window=(START_DATE, cutoff))`。
3. **PASS = 排名尺 PASS 而且 `paired.gap_change` 點估計 ≤ 0**（唔准令同市場嘅差距變大）。
4. 另報（唔係閘）：市場尺 A（`candidate_has_info_beyond_market`，預期 false —— 市場已定價）、市場尺 B 配對判決（贏市場軌）、Gold／Good／AUC。

- **PASS**：只係「值得考慮上線」。上唔上線係 Kelvin 決定；上線要另一個改動、過 `model-regression-gate`、更新 golden／data_contract／模型說明。
- **FAIL**：照記錄（點樣失敗：邊個 check 唔過、數字），**唔准喺同一批數據換 β／換窗／換尺重試**。要再試就要新假設、新登記、新賽日。

## 接駁

- 排程：`au_daily_schedule.step_h1_forward`（evening，`step_speed_forward` 之後）每晚跑 `status`；`ready` 就即刻 `evaluate` 一次。
  失敗只 `log` ＋ `runlog.step`，**唔 `runlog.warn`**（同 `step_calibration_shadow`，warning 會令 evening 變 partial）。
- 狀態檔：`<WORK_DIR>/au-h1-forward-status.json`。盲：未判之前只有場數、賽日、快照來源、平均 |shift|（唔睇賽果），`outcomes_visible=false`。
  外置碟冇插（校準場次 offline）就 `blocked_offline`，聽晚再試，唔會用唔齊數據判。
- 追蹤表：`au_forward_tracker.FORWARD_TESTS` 加咗 `h1_trial_prep`（`status_file`）。追蹤表而家會跟狀態檔自己嘅 `ready`
  （要同時夠賽日同場數），第一次夠數推 Telegram，同時上 forward 總板。

## 狀態

- 2026-11-25：凍結、登記。forward 0 場（未開始）。golden 不變（live 排名冇郁）。
