# EXP-20261102-03 預先登記：AU 官方評分趨勢（上仗 → 今場）有冇用（診斷）

> 量度之前寫。結果另寫 `EXP-20261102-03-au-rating-trend-results.md`。

- **日期**：2026-11-02；**平台**：AU；**類型**：診斷（唔改排名，冇判決 arm）。
- **用戶**：「測埋『評分趨勢』」—— 讓磅官對呢匹馬嘅睇法係變好定變差。
- **舊記錄**：AU 從未測過評分變化。相關：EXP-20260831-06（評分＋負磅殘差係擲毫，raw rating 有料）；
  HKJC EXP-20261010-07（評分下跌篩選，HKJC 專用，唔搬過嚟）。

## 數據（量度之前已查）

- 今場評分 = 場次資料夾 `* Race N Racecard.md` 嘅 `Rating:`（RA Acceptances，接受報名嗰刻定，**賽前**）。
- 上仗評分 = 同一匹馬**較早日期**一個 Racecard 嘅 `Rating:`（同樣係嗰日賽前）。只用 `日期 < 今場日期`，
  365 日內最近一次；同日唔計。馬名正規化（細寫、只留字母數字）。
- Racecard 嚟自 `Archive/` 同頂層場次資料夾（全部，唔用 `rglob` 以外嘅排除名單 —— 純讀評分，唔讀評分輸出）。
- 結果 = `AU_Historical_Raw_Race_Results.csv`（`Pos ≤ 3` = 上名）。模型分 = 嗰場 `Race_N_Auto_Scoring.csv` 嘅
  `final_rank_score`（當日出嗰版），另讀 `form_score`、`rating_score`。

## 設計

- 目標賽事：2026-08-05 起（乾淨 point-in-time 窗）、有 Auto_Scoring 同賽果、場內 ≥ 4 匹有趨勢值。
- `trend = 今場評分 − 上仗評分`。冇方向假設（升分 = 狀態好，但亦代表負磅加咗），**雙邊**判。
- 量度：
  1. 覆蓋率：有今場評分嘅馬之中，有趨勢值嘅比例。
  2. 趨勢單獨嘅場內配對 AUC（上名 vs 唔上名，只計有趨勢值嘅馬），按賽日 bootstrap 2000（seed 7）。
  3. 同模型重疊：場內 Spearman ρ(trend, final_rank_score／form_score／rating_score) 中位數。
  4. **增量**：條件 logit（場內 softmax 對「上名」），訓練 < 2026-10-01、測試 ≥ 2026-10-01（時間切分，唔調參）。
     A = z(final_rank_score)；B = A + z(trend)（場內 z，冇趨勢值 = 0）。
     報測試每匹 log-likelihood 差同場內 AUC 差（B − A），按賽日 bootstrap 2000 CI。

## 判決（預先寫死）

- **有用** = 增量 log-likelihood CI 全正 **而且** 趨勢單獨 AUC CI 唔包 0.5。有用先開排名候選，
  照 `docs/model-evaluation-contract.md` v3 另行預先登記；**呢個診斷本身唔改模型**。
- 其餘一律記錄結案（「冇用」要寫清楚係冇訊號、定係有訊號但同模型重複）。
- 唔准換窗、換切分日、換結果定義去救。

**Leakage**：兩個評分都係賽前公開數；上仗評分只取今場之前嘅 Racecard；測試期唔參與 fit。
