# Tennis Wong Choi Performance Audit — 2026-08-21

## Executive verdict

現時未有任何 player-prop family 證明到可持續正 ROI。Lifetime paper profile 仍然係正數，但 rebuild 後 holdout、最近 14 日、raw-model Brier 全部顯示 edge 已衰減；所以全部維持 `RESEARCH_ONLY`，唔可以將 paper result 當成實盤盈利。

## Performance windows

| Window | Settled | Wins | P/L | ROI | Interpretation |
|---|---:|---:|---:|---:|---|
| 2026-08-20 | 28 | 10 | -10.649u | -38.0% | 單日，只作營運告警 |
| 最近 14 日（截至 2026-08-20） | 317 | 159 | -29.613u | -9.3% | 固定 rolling window；短期 gate 主要證據 |
| Rebuild holdout（2026-08-07 起正式 profile） | 343 | 177 | -22.683u | -6.61% | chronological OOS／forward-style audit subset |
| Lifetime 正式 paper profile | 1,789 | — | +82.833u | +4.6% | 只供 regime comparison，唔可用嚟解鎖投注 |
| Confirmed live bets | 0 | 0 | 0u | N/A | 無實盤回報可以申報 |

14 日同 rebuild holdout 筆數唔同，因為前者按每日 performance contract 嘅日期／settlement cutoff，後者按 rebuild cutover 同 formal-profile eligibility；兩者唔會混合成一個 ROI。

## Family paper profile

| Family | Lifetime settled | Lifetime P/L | Lifetime ROI | 固定短期觀察 | Current gate |
|---|---:|---:|---:|---:|---|
| player_aces | 72 | +3.596u | +5.0% | 全 sample +5.0% | RESEARCH_ONLY；holdout Brier/ROI 未過 |
| player_double_faults | 0 | 0u | N/A | 無 feed coverage | RESEARCH_ONLY |
| player_total_games | 329 | +2.238u | +0.7% | 最近 100：-5.0% | RESEARCH_ONLY |
| player_win_a_set | 411 | +41.115u | +10.0% | 最近 100：-5.6% | RESEARCH_ONLY |
| first_set_winner | 67 | +5.480u | +8.2% | 全 sample +8.2% | RESEARCH_ONLY；sample 細、Brier 輸市場 |
| player_game_handicap | 891 | +25.537u | +2.9% | 最近 100：-24.9% | RESEARCH_ONLY／短期熔斷 |
| player_set_handicap | 19 | +4.867u | +25.6% | sample 太細 | RESEARCH_ONLY |
| player_exact_set_score | 0 formal bets | 0u | N/A | 只得 scorecard outcomes | RESEARCH_ONLY |

## Probability quality

- Raw model Brier：0.2127。
- De-vig market Brier：0.1962。
- 結論：市場目前比模型校準得好；放寬 edge threshold 只會增加負 EV exposure。
- 2026-08-07 frozen holdout 逐 family 比較亦係全部 raw model 輸市場；market-residual 同 surface-conditioned 實驗無 family 達到預先設定嘅 +0.002 Brier improvement。

## Data and settlement health

- 2026-08-07 至 2026-08-20：813 fixtures、642 priced、599 analysed、705 resulted、3,494 prop rows、468 value rows。
- 已修復 265 個 `prop_tracker`／`clv_tracker` settlement mismatch；目前為 0。
- 已修復 6 個不可能 scoreline；critical validation failure 目前為 0。
- 仍有 43 個超過 3 日嘅 value pending：34 個無 match result，9 個有比分但缺 ace stats。呢啲唔會被當作輸贏或靜默刪除。

## Decision

現階段目標唔係「調參調到歷史 ROI 變正」，而係逐 family 證明 untouched OOS 增量。Promotion 必須同時通過：model Brier 贏 market、calibration 合格、settlement/price timing 完整、bootstrap downside gate、固定短期 ROI 非負；否則繼續 shadow 或 retire。

第一輪專業化轉化已完成：game handicap／player games 改用 fitted joint simulator，set families 共用 BO3 outcome distribution，player aces 改用 service-games exposure + negative-binomial。新 variant 全部改善咗各自舊 raw Brier，但仍然輸 bookmaker baseline，因此決定不變：全部 `RESEARCH_ONLY`。詳細結果見 `professional-model-conversion-2026-08-21.md`。

## Price preference

正式卡現以 `2.00+` 作 EV-aware soft preference，而唔係硬 cutoff：先套用相同 evidence/value/timing gates，再畀合格 2.00+ 候選 3 個 EV 百分點嘅排序 bonus。長價只會喺同最佳短價相近時升前，唔會跳過明顯更高 EV 嘅 1.50–1.99；無合格長價時，正 edge 短價照常可用。報表會精確分拆 `<1.60`、`1.60–1.99`、`2.00–2.24`、`2.25+`，避免將 1.90 同 2.00 混埋後誤判。
