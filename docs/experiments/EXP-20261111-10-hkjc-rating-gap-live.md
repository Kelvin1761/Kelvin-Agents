# EXP-20261111-10 HKJC 負磅分改讀官方評分差距（上線，Kelvin 決定）

- **日期**：2026-11-11
- **平台**：HKJC
- **決定**：Kelvin：「我覺得應該要上線先」—— 明知按 `fixed_rule` 係 REJECT（Good 點估計 < 0）、forward 只得 30/60
- **證據**：EXP-20261029-30（兩次回放）、EXP-20261111-09（今日 main 重跑 ＋ forward 拆分）
- **改到嘅檔案**：
  - `hkjc_auto_orchestrator._align_runner_headers`：退出之後計全場最高評分，寫 `race_context.field_top_rating` 同每匹 `_data.rating_gap`
  - `hkjc_racing_engine/_leaves._weight_score`：有 `rating_gap` 就用（≤1 重 70、≥13 輕 54、其餘 64）；冇評分先退返宣佈負磅 ≤120／≥132
  - `scoring.py`：`WEIGHT_RATING_GAP_LIGHT/HEAVY`、`WEIGHT_DECLARED_LIGHT/HEAVY`
  - `hkjc_forward_tracker.py`：`weight_rating_gap` 標記 decided
  - 測試：`test_weight_direction.py` 加 `RatingGapIsTheInput`（5 條）
  - `hkjc_data_contract.json` 重新 calibrate；HKJC 模型說明重新生成

## 證據摘要
| | 場 | Gold Δ | Good Δ | 判決 |
|---|---|---|---|---|
| 10-29 舊 main | 345 | +1.16 [+0.29, +2.30] | −0.58 [−2.09, +0.89] | REJECT |
| 11-11 今日 main | 380 | **+1.05 [+0.26, +2.12]** | −0.53 [−2.07, +0.81] | REJECT（primary_regression） |
| forward 10-30 起 | 30 | 2 → 2 | 4 → 4 | 打和；NDCG −0.0083 |

## 點解負磅同評分會差咁遠（Kelvin 問）
435 場 / 5,432 匹，兩種分界只有 **82.1%** 匹馬分類一樣：

| 而家（負磅）＼ 新（評分差距） | 中 | 輕 | 重 |
|---|---:|---:|---:|
| 中 | 2,607 | 485 | 46 |
| 輕 | 35 | 1,118 | 0 |
| 重 | 409 | 0 | 732 |

1. **香港頂磅通常係 135 唔係 133**（368/435 場）。舊分界「負磅 ≥132」= 距頂 ≤3 分；「≤120」= 距頂 ≥15 分。
   新分界係距頂 ≤1／≥13，所以 409 匹由「重」變「中」、485 匹由「中」變「輕」。
2. 3.9% 場次冇馬負到 132（頂磅 126–131），舊版全場冇「重」；新版全場最高評分照攞「重」。
3. 讓磅賽入面「頂磅」同「全場最高評分」揀中同一批馬（EXP-20261111-09），所以差異**唔係評分同負磅資訊唔同，係分界擺位唔同**。
   即係 Gold 升幅好可能嚟自分界收窄／擴闊，唔係「評分 vs 負磅」本身。

## 上線前核實
- **忠實度**：production 改動喺 440 場 PIT 回放同 arm `hkjc_arm_weight_rating_gap.py` 嘅排名**逐場一樣（0 場唔同）**
- 單元測試：`test_weight_direction.py` 19/19
- **golden_scoring**：120 匹全部一致 —— golden fixture 冇排位表評分，行後備負磅路徑；新路徑由回放同單元測試覆蓋
- **data_contract**：重新 calibrate（引擎指紋 09e4ffca31f4），check 全部符合
- leakage-audit：PASS —— 評分係排位表賽前資料

## 風險同退路
- Good 三次量都係微負（約 2 場 / 380），CI 跨零；可能係真嘅輕微代價
- **退路**：將 `_weight_score` 開頭 `rating_gap` 分支剷走（或者 orchestrator 唔寫 `rating_gap`）即退返宣佈負磅版本；
  `golden_scoring` 冇郁，舊 baseline 照用
- **跟進**：上線後 60 場 live 同上線前比較 Gold／Good（記喺下一份記錄）

**決定**：KEEP（Kelvin 決定上線，唔係閘門判 KEEP）
