# EXP-20261023-01 NBA back-to-back 旗標：由「永遠係 B2B」修正為真實連續作賽（正確性修正，唔係模型改善）

- **日期**：2026-10-23
- **平台**：NBA
- **假設**：report 層嘅 team B2B 旗標同 extractor 算出嘅 `is_b2b` 唔一致。**可證偽**：用真實 extractor 輸出數旗標觸發率；若合理（開季首周多數隊伍距上場賽事極遠）應該接近 0。
- **搜索過嘅舊記錄**：`grep -il "b2b\|back-to-back" docs/experiments/` —— 冇相關記錄。
- **改到嘅檔案**：`nba_extractor.py`（`nba_local_game_date`、`compute_rest_info`、`compute_fatigue_adjustment`）、`generate_nba_reports.py`（`detect_team_b2b`、MC 旗標來源、meeting 表 B2B 格）、新測試 `test_nba_back_to_back.py`。
- **唔係**：冇重訓、冇改權重、冇改調整幅度（B2B 仍然 −2／−4）。**冇聲稱改善。**

## 發現（用 2026-10-22 十一場真實 extractor JSON 量度）
1. **旗標永遠係真**：舊規則 `fatigue_pct > 0 or warning` 即「任何球員有過 B2B 掉 PPG」。**22／22 隊觸發**（而同一批 JSON 嘅 `is_b2b` 全部 false —— 最後一場都係 3 至 11 個月前）。結果：每隊每條 leg 都喺 10-Factor 食 −2（主）／−4（客）。
2. **Monte Carlo 由來冇收到 B2B**：`is_b2b_map` 由 `meta[...]["fatigue"]` 讀，meta 冇呢個 key，永遠 false。
3. **Report 表格硬寫 `B2B：否`**。
4. **UTC 日期錯**：ESPN tip 係 UTC（如 `2026-10-22T02:00Z` = 美西 10 月 21 日 7pm），game log 係美國當地日；用 UTC 日期令晚場 B2B 被當隔咗兩日。
5. **新季／新秀無 rest_splits 就 `fatigue = None`**：B2B 完全未知，ML `b2b_flag` 一律 0。

## 修正
- 美西當地日（`America/Los_Angeles`）同 game log 比；`is_b2b` 同 splits 脫鈎（冇 splits 都計到）。
- 隊旗標＝有已知休息日嘅球員中 **≥ 一半** `is_b2b`；未知唔計。
- MC 同 meeting 表改用同一個 `team_b2b`。
- `rest_days` 語義不變（ML 特徵）；唯一差別係用美西日期，晚場會少數 1 日差。

## A/B（同一 11 場、2,710 條 leg；舊＝origin/main，新＝本分支，`NBA_FIT_LAYER_SHADOW_ENABLED=0`）
| | 結果 |
|---|---|
| `p_10f`（10-Factor） | 1,061 條改變，平均 +1.08pp，最大 +4.0pp（B2B 懲罰消失） |
| `p_final`（引擎最終機率） | **0 條改變** |
| `p_monte_carlo` | 0 條改變（今日冇隊係 B2B） |
| 入選 leg／組合 | 完全相同（8 個 picked；11 場組合 0 場有分別） |

`p_final` 冇動，因為 live 最終機率已改由校準層（EXP-20261022-03）出，唔再直接食 10-Factor 嘅加減。所以呢個修正喺而家 **唔改任何落注輸出**，只係：(a) 10-Factor 顯示值同診斷唔再係每隊 −2／−4；(b) 真係 B2B 嗰晚 MC／ML 會收到正確旗標。

## 限制
- 量度日（開季第二日）冇任何真 B2B，所以「真 B2B 日嘅行為」只靠單元測試覆蓋，冇真實日數據。要等到 11 月會有真 B2B 先睇到。
- 冇量度 B2B −2／−4 幅度本身啱唔啱（獨立問題，未做）。
