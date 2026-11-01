# EXP-20261101-39 診斷：L600 標準嘅資訊上限 —— 權重 fit 好之後 G 同現行速度分一樣

- **日期**：2026-11-01；**平台**：AU；**類型**：只量度，冇改模型。
- **用戶**：「actually 3,246 is a lot, let's figure out how we can get this speed sorted out properly」；
  「Unless sportsbet have 更好嘅逐駒數據, or else i dont think there is any」。
- **腳本**：`scratch/au_speed_logit_ceiling_20261101.py`（場內 z）、`scratch/au_speed_logit_ceiling_raw_20261101.py`（場內置中、原尺）；
  數據 = EXP-33 arm（base = production、G = 冇場地項嘅 point-in-time 標準）。

## 1. Sportsbet 有冇更好嘅逐駒數據：冇

逐仗原始頁（cache `.sportsbet_cache`，10,823 頁）只有：名次／馬數、終點輸距、800m／400m 位置（得名次，冇輸距）、
**賽事** `Sectionals 600m`（全場同一個數，EXP-20260831-09 已證）、頭馬時間、頭三名同輸距。冇逐駒分段。
唯一逐駒分段來源係 Racing Queensland XML（只有昆士蘭，而家用嚟計逐駒全程速度）。

## 2. 3,246 場夠唔夠

- 逐匹層面夠：今次每個測試用 ~31,000 匹嘅上名／唔上名結果，CI 半闊 ~0.001（log-likelihood）／~0.003（AUC）。
- 整場指標唔夠分辨細改動：Gold／Good 嘅配對 CI 半闊大約 ±0.7–0.9pp；G、SH 嘅效應得 0.1–0.5pp。
- 所以今次改用逐匹、walk-forward 嘅 logistic（每段只用之前日期 fit，5 段 OOS，73 個賽日）答問題。

## 3. 結果

| 比較 | Δ | 95% CI（賽日 bootstrap） |
|---|---:|---|
| G vs 現行速度分（權重各自 fit，log-likelihood／匹，場內 z） | −0.00000 | [−0.00109, +0.00109] |
| 同上，within-race AUC | −0.00011 | [−0.00359, +0.00317] |
| 同上（原尺） log-likelihood | −0.00009 | [−0.00113, +0.00096] |
| 同上（原尺） AUC | −0.00018 | [−0.00333, +0.00280] |

**G 單獨準咗（leaf AUC +0.013），但同其他維度一齊 fit 權重之後，預測力同現行速度分一模一樣。**
即係新標準帶嚟嘅「準」，係模型其他部分已經知道嘅資訊（主要係馬匹質素）。呢個就係 EXP-30 至 37 換標準點都唔郁排名嘅原因。

## 4. 速度權重：唔支持郁

logistic fit 出嚟速度相對其他嘅比例高過 production（原尺 0.16 vs 0.114），但用 walk-forward fit 權重排名，
within-race AUC 反而**差過** production（原尺 −0.0017 [−0.0034, −0.0000]；場內 z −0.0028 [−0.0048, −0.0008]）。
logistic 優化嘅係機率校準，唔係排名。同 memory `au-pace-perf-weight-is-optimal` 一致：唔改權重。
（我第一次用場內 z 版本報「速度權重輕咗 1.6 倍」，係錯嘅 —— 場內標準化會逐場改變相對權重，唔可以同 production 比。）

## 5. §8 refit 嘅功效問題（另外記低）

EXP-31／33 嘅 §8 refit：baseline 9 個窗有 6 個 fallback 返現行權重（`consensus_failed_gate` 3、`no_consensus` 3），
即係 B0 大部分時間 = A0。refit 用 256 個隨機權重 + 離散指標閘門，功效低。呢個係把尺嘅限制，要改就要當獨立改動論證。

## 結論

- 用 Sportsbet 數據，L600 標準已經去到資訊上限，唔好再試標準變體。
- 唯一未用嘅速度資訊係 Racing Queensland 逐駒 200m 分段（真正逐駒末段 600m，只限有昆士蘭往績嘅馬）。
  2026-07 嘅 QLD shadow 測試只有 6 場（`AU_QLD_Runner_Sectional_Shadow_Backtest.md`），等於未測過；
  而家 bundle 有 5,420 場（2025-01 起）。
