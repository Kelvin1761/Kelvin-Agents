# Unified AU Race Reflector Report

## Workflow Summary
- Domain: `AU`
- Meeting: `2026-08-22 Randwick Race 1-10`
- Reflected races: `2`
- Results file: `Race_Results_Reflector.md`
- Approval gate: **任何 improvement suggestion 只供審批，不會自動改 code / matrix。**

## Meeting Performance Summary
- Gold: 0
- Good: 0
- Pass: 0
- 1 Hit: 1
- Miss: 0
- Top 5 包齊實際前三: 0/1 (0.0%)
- Top 5 包至少兩匹實際前三: 0/1 (0.0%)
- 冠軍在模型 Top 5: 1/1 (100.0%)
- 平均每場 Top 5 包實際前三匹數: 1.0

## What The Model Did Well
- 今次 meeting 幾乎冇明顯命中優勢，強項主要只剩個別單場細節。

## What The Model Missed
- 只有 1 Hit 的場次有 1 場，通常屬排序未夠準而唔係完全冇訊號。

## Race 2
- Performance label: **1 Hit**
- Model Top 3: #5 Mrs Goldberg, #9 Dee Dee Express, #4 Zubba Storm
- Model Top 5 shortlist: #5 Mrs Goldberg, #9 Dee Dee Express, #4 Zubba Storm, #14 Kakoda, #19 Parthenope
- Actual Top 3: 1. #5 Mrs Goldberg, 2. #15 Empress Tsarina, 3. #18 Lovecats
- Top 5 shortlist coverage: 1/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Actual Top 3 outside model Top 5: #15 Empress Tsarina, #18 Lovecats
- Missed Top 3 horses:
  - #15 Empress Tsarina: 模型失誤。 原模型排第 13， 隱藏訊號 `段速 / 信心`， 短板 `練馬師 / 騎師`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強段速 / 試閘 / 速度訊號
  - #18 Lovecats: 模型失誤。 原模型排第 8， 隱藏訊號 `賽績線 / 信心`， 短板 `pace_figure_score / rating_score`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
- Race verdict: 偏向 clean model failure

## Backtested Improvement Suggestions
- 今次未有可用 backtest candidate。

## Recommended Next Step
- 先審核今份反射報告與 backtest evidence。
- 如你批准某個 suggestion，我哋先會再做 code / matrix 更新。
- 無批准之前，最終排名仍以現行 `綜合戰力分` 排序結果為準，唔會有任何 override。
