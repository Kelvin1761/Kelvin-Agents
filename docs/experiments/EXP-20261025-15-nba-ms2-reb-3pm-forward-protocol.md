# EXP-20261025-15 MS2 只用喺 REB＋3PM 對 Layer C 嘅 forward 判決協議（未有數據之前凍結）

- **日期**：2026-10-25（Claude Code，用戶同意趁零數據時預先登記）
- **點解另開一個測試**：EXP-20261025-14 明文唔准事後揀 stat。呢個子集假設喺**任何 forward 數據出現之前**提出，依據係開發證據（EXP-13 有價 dev：MS2 − C_refit 嘅 REB −0.0020、3PM −0.0007；PTS −0.0001、AST +0.0022；S_v2 單獨對市場 REB −0.0041、3PM −0.0012）。開發證據已經睇過，所以唔算確認，只係用嚟揀假設。
- **凍結時狀態**：帶 `season_rate_v2_*` 嘅 ledger 腿 = 0。
- **工具**：`nba_ms_forward.py --model v2-reb3pm`；設定 `nba_ms_forward_v2_reb3pm.json`，SHA256 `be37d53912d9154e1f51b9b6c5b4b0156737dfad1a78b4b2900c1193565e5c5c`。係數同 EXP-14 一模一樣（測試釘住），只係加咗 `stats: [REB, FG3M]`。

## 假設

只喺 REB 同 3PM 嘅腿上，MS2 嘅 Brier 好過現役 C。成立嘅話，候選上線方式係「REB／3PM 用 MS2，PTS／AST 繼續用 C」。

## 規則

除咗以下兩點，其餘同 EXP-20261025-12 §3–§7 一字不改（樣本規則、150／400／800 場檢查點、97.5% 比賽日 cluster CI、五項 KEEP 條件、數據守則、唔准中途改）：

- **範圍**：只計 REB 同 3PM 嘅腿。其他 stat 計做 `stat_out_of_scope`，唔入覆蓋率分母。
- **場次**：只計有至少一隻 REB／3PM 合資格腿嘅場次。

## 功效（睇數據之前計）

用 EXP-11 嘅 OOF 做替代（REB＋3PM、MS1 − C_refit），每場 SD ≈ 0.00449（32 場）。

| 檢查點 | MDE（97.5% 雙尾、80% 功效） |
|---|---:|
| 150 場 | 0.00113（只做傷害檢查） |
| 400 場 | 0.00069 |
| 800 場 | 0.00049 |

開發效應大約 −0.0013，所以如果係真，400 場有合理功效。但開發效應通常偏樂觀，呢點寫低喺度。

## 多重比較

EXP-12（MS1 全部 stat）、EXP-14（MS2 全部 stat）同呢個 EXP-15 並行。任何一個 KEEP 之後要切換 live，`model-regression-gate` 都要對三個測試做 **Holm 調整**。只要其中一個 KEEP，唔可以當其餘兩個都成立。

## 執行

```bash
cd .agents/skills/nba/nba_daily_auto
PYTHONDONTWRITEBYTECODE=1 python3 nba_ms_forward.py --model v2-reb3pm --until YYYY-MM-DD
```
