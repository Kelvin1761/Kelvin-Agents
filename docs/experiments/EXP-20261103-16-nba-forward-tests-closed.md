# EXP-20261103-16 NBA forward／shadow 測試全部收咗（隨 nba_engine 重寫）

- **日期**：2026-11-03
- **平台**：NBA
- **決定人**：Kelvin（2026-11-03：「全部收咗，記錄結果」）
- **原因**：重寫成 `nba_engine`（EXP-20261103-15）之後，live 唔再計 ML、MC、fit layer A、S_v1／v2／v3 shadow 欄位，亦冇 B0／B1 shadow；冇一個測試接近判決點，繼續養住佢哋要將舊引擎大半複雜度搬返過嚟。
- **冇任何一個測試有判決**：以下全部係「中止、冇結論」，**唔准當作 REJECT 或 KEEP 引用**。

## 中止時進度（`nba_experiment_readiness` 2026-11-03 輸出，最後一次）
| 測試 | 協議 | 狀態 | 進度 | 原定檢查點 |
|---|---|---|---|---|
| MS1（市場＋S_v1 vs C） | EXP-20261025-12 | ACCUMULATING | 51 場／6 日 | 150 場 |
| MS2（市場＋S_v2 vs C） | EXP-20261025-14 | INVALID_DATA | 40 場／4 日 | 150 場 |
| MS2 REB+3PM | EXP-20261025-15 | INVALID_DATA | 40 場／4 日 | 150 場 |
| MS3（市場＋S_v3 vs C） | EXP-20261026-01 | INVALID_DATA | 40 場／4 日 | 150 場 |
| S_v4 vs S_v2 | EXP-20261026-08 | ACCUMULATING | 31 場有上季比賽嘅腿 | 季初完結或 12-01 |
| 季初穩膽保護 | EXP-20261026-06 | ACCUMULATING | 29 場（要 ≥15 且 ≥11-15） | 11-15 |
| Questionable／Probable 上場率 | EXP-20261026-02 | ACCUMULATING | 0／0（各要 ≥30） | — |
| 最佳落注時間 | EXP-20261027-20 | ACCUMULATING | 5 日（要 ≥10） | — |
| B0／B1／B2 穩膽 EV shadow | EXP-20261024-02 | 停寫 | — | — |
| fit layer A shadow | EXP-20261023-05 | 停寫 | — | — |

MS2／MS3 嘅 INVALID_DATA 係 11-01／11-02 ESPN 轉換期對手表 `source_unavailable` 造成（EXP-20261103-15 修訂 1 有記）。

## 後續
- 「市場＋S」呢條路線嘅問題，EXP-20261103-15 用今季已有數據直接答咗：MS（S_v4 版）holdout 贏 C，已經上線做 `p_final`。即係 MS1–MS3 想答嘅嘢，有一個較早、較細樣本嘅答案；要更大樣本，ledger 每晚照記 `p_ms`／`p_c`／`p_s`，隨時可以重跑 EXP-20261103-15 嘅 `evaluate.py`。
- 季初穩膽保護嘅旗標（`l10_mostly_previous_season`、`new_team`）照樣喺 B2 擋腿（行為不變），只係唔再有監測。
- 歷史 ledger 行（`banker_shadow_obs`、`shadow_fit_*`、`season_rate_v*`）原封不動保留喺 `~/WongChoiData/NBA_Market_Eval/ledger/`。

## 刪走嘅 code
`nba_ms_forward.py`（+ 4 個 json）、`nba_season_rate_v4_forward.py`、`nba_early_season_guard_monitor.py`、`nba_experiment_readiness.py`、`nba_availability_outcomes.py`、排程 `_experiment_readiness` 步驟，同埋相應測試。要睇舊版用 git history（本 commit 嘅 parent）。

## 更正（2026-11-10）
上面「ledger 每晚照記 `p_ms`／`p_c`／`p_s`」**唔啱**：`nba_market_ledger.record_snapshot` 只抄舊引擎嘅
`season_rate_v*_prob_S` 欄位名，而 `nba_engine` sidecar 用 `p_market`／`p_c`／`p_s`／`p_ms`，所以 11-03 起 ledger 嘅
S 全部係 null。2026-11-10 起 `model_obs` 照 sidecar 原名記低呢四個（`ENGINE_COMPONENTS`，唔入 `MODEL_VARIANTS`，
`evaluate()` 不變）。11-03…11-10 嘅歷史值冇補寫入 ledger（ledger 只加唔改）；要用就直接讀
`_prediction_snapshots/<snapshot_id>/Game_<tag>_Full_Analysis.md.market_legs.json`，每個 21:00 snapshot 都有。
