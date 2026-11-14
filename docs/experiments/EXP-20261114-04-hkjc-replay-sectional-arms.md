# EXP-20261114-04 HKJC 段速候選喺全量回放（研究計劃第 4 步＋§2c 負磅）

- **日期**：2026-11-14 ｜ **平台**：HKJC ｜ **決定**：邊緣（FT 方向全正但 CI 跨零）→ **Kelvin 2026-11-14 決定上線（決定 2）**＋forward `sectional_ft_post_live` 可退回
- **前置**：EXP-20261113-08（概念 PASS）、EXP-20261113-09（389 場判唔到）、EXP-20261114-01（負磅逐段）、EXP-20261114-03（S 版 baseline）
- **腳本**：`patches/hkjc_hist_sectional_features_v2.py`、`patches/hkjc_replay_sectional_arms.py`（預先登記喺 docstring）

## 方法
baseline = S 版權重（EXP-20261114-03）。`speed' = clip(speed + 0.5 × 9.45 × clip(z, ±2.5))`，標準化用 2024-08 前；離線重排（base picks = raw 排序，0 場例外）。
arm：FT（前段＋全程，主）、F、T、Tw（全程換算今仗負磅 0.0033 秒／400 米／磅）、FTw。

## dev（2020/21–2023/24）
| arm | Gold | Good | capture@5 | 頭二 | 過 dev |
|---|---|---|---|---|---|
| **FT** | **+0.42** [+0.03,+0.84] | +0.03 | +0.18 | +0.24 | ✅ |
| **F** | +0.27 | +0.09 | **+0.42** [+0.06,+0.78]（100% null） | +0.24 | ✅ |
| T | +0.18 | **−0.12** | +0.27 | 0.00 | ❌ |
| Tw | +0.21 | **−0.24** | +0.36 | +0.06 | ❌ |
| FTw | +0.36 | 0.00 | +0.18 | +0.24 | ❌（冇指標過） |

## holdout（2024/25–2025/26，1,710 場；一次）
| arm | Gold | Good | capture@5 | 頭二 | 贏 null |
|---|---|---|---|---|---|
| FT | +0.18 [−0.41,+0.76] | +0.18 [−0.53,+0.94] | +0.23 [−0.14,+0.62] | +0.23 | 93–96% |
| F | +0.12 | +0.06 | +0.12 | **−0.47** | 36–93% |

## 結論
1. **前段係有用嗰部分**；全程單獨加 Good 跌；**負磅換算冇幫**（Tw 比 T 更差）—— 同 EXP-20261114-01「全程負磅效應細」一致。
2. FT holdout 四個點估計全正、Gold／Good 冇跌，capture@5 贏 96% null（啱啱過預先登記 95%），但 Holm（2 個）後唔過、冇 CI > 0。
   → 按規矩係**邊緣**：唔上線。效果大約 +0.2pp，要 forward 大約 1,500–2,000 場先判得清。
3. 段速依然係 Kelvin 認為最重要嘅因素；證據話「加前段唔會傷，但幅度細」。

## 決定清單
- 開 FT forward shadow（新場次對現行，唔入分），定係直接接受「方向正、無害」上線？

## 上線（Kelvin 2026-11-14「2 上線」）
- 計法：`hkjc_racing_engine/pit_sections.py`（`ft_values`／`ft_points`）—— live 同離線同一套定義；表 `HK_Racing/HKJC_Sections/pit_sections.json`
  （本機資料根，唔讀外置碟），由 `hkjc_race_extractor/scripts/hkjc_pit_sections_build.py` 生成。
- 引擎：`past_runs.attach` 寫 `_data.sectional_ft`；`SpeedScorer.compute` 喺所有段速分之後加 `b × 9.45 × mean(z)` 再 clip（同 arm 次序一樣）；開關 `scoring.SECTIONAL_FT`。
- 忠實度：生成器表 vs v2 特徵 7,862 個值 0 差異；live 引擎 vs 離線 arm（回放 2023-09..10）speed_score 1,426／1,431 一致（差異 ≤1.1 分，
  來自舊仗班次來源：live 用 `recent_6_detail` 近 6 仗，離線用分段頁）。修正咗冇跑完（段數唔齊）嘅仗：表加 `nsec`，live 只收段數齊嘅仗。
- live 接線：2026-11-11 九場 101 匹 speed_score 改變、8 場排名改變。
- 每日更新：HKJC 排程覆盤完成後背景跑 `hkjc_pit_sections_build.py update`（backfill tasks → 慢速補抓分段頁 → 解析 → 重建表）；
  檔案鎖防同時兩個抓取器；外置碟冇掛載或者失敗 → Telegram primary，live 用上一版表。
- 一齊入 main：`backfill_history.py` 兩位數年份修正（現役馬頁面之前 0 仗）同 `horse_all`（所有往績）—— 否則每日更新跑 `parse` 會用有 bug 版本覆蓋馬匹頁解析。
- forward `sectional_ft_post_live`（60 場）。
