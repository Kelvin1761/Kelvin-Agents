# EXP-20261127-40 結果：NBA S2 forward（EXP-20261111-05）判決 —— PASS（主指標），但改善嚟自「重新擬合」，唔係新上場時間預測

- **日期**：2026-11-27 · **平台**：NBA · 協議：`EXP-20261111-05-nba-s2-shadow-forward-protocol.md`（11-11 commit 4c50042e，喺任何 forward 數據之前）
- **判決點**：`nba_forward_tracker` 喺 2026-11-26 18:44 悉尼（07:44 UTC）自動判一次並凍結：
  `~/WongChoiData/NBA_Market_Eval/reports/EXP-20261111-05-S2-result.json`。今日（11-27）用同一個腳本 `--force` 寫去 scratch 重跑，數字**逐位一樣**；判決腳本自 4c50042e 冇改過。
- **冇改任何上線 code**：`config.json`、`p_final`、精選規則全部不變。上唔上線係 Kelvin 決定。

## 主判決（預先登記，凍結）
母體：target_date 2026-11-12…11-26（14 個比賽日；11-19 冇 production 發佈，見 EXP-20261124-70），**15,787 腿**（門檻 14 日／10,000 腿）。

| | 平均 log-loss |
|---|---|
| 發佈 `p_final`（MS） | 0.45337 |
| **MS2（市場＋S2，S 份額 0.35）** | **0.45154** |
| MSR（同批數據重擬合，舊 S） | 0.45137 |
| S 單獨 | 0.46237 |
| S2 單獨 | 0.46167 |

**Δ = MS2 − 發佈 = −0.00183，95% CI [−0.00313, −0.00065]**（按日 cluster bootstrap 2,000，seed 20261111）→ CI 上限 < 0 = **PASS**。

### 次要（協議預先列明，只報告）
| 比較 | Δ log-loss [95% CI] | 解讀 |
|---|---|---|
| MSR − 發佈 | −0.00200 [−0.00316, −0.00102] | 單係「重新擬合＋S 份額升到 0.29」已經攞晒改善 |
| **MS2 − MSR** | **+0.00017 [−0.00033, +0.00063]** | **新上場時間預測（v2 minutes）冇加到嘢**，點估計仲差少少 |
| S2 − S | −0.00070 [−0.00211, +0.00061] | S2 單獨比 S 好少少，CI 跨零 |

逐 stat（MS2 − 發佈）：PTS −0.0015（4,902）、REB +0.0001（4,028）、**AST −0.0058**（2,934）、3PM −0.0012（3,923）。

## 額外（今次加，非預先登記，只報告）
腳本：`patches/nba_s2_forward/secondary.py`（同一母體 15,787 腿）。

- **Brier**：發佈 0.14692 → MS2 0.14628，Δ −0.00064 [−0.00111, −0.00022]；14 日入面 11 日 MS2 較好。
- **命中（p ≥ 0.5 判 over）**：發佈 78.72% → MS2 78.96%（+0.24pp；大部分腿係極端線，呢個指標好鈍）。
- **平均機率**：實際 0.379；發佈 0.363、MS2 0.369 —— 發佈機率整體偏低，MS2 修正咗一部分。
- **校準**（按發佈機率分段）：

| 段 | 腿 | 實際 | 發佈 | MS2 |
|---|---|---|---|---|
| 0–0.2 | 7,011 | 0.097 | 0.088 | 0.097 |
| 0.2–0.4 | 2,686 | 0.351 | **0.292** | 0.310 |
| 0.4–0.6 | 1,948 | 0.551 | **0.496** | 0.505 |
| 0.6–0.8 | 1,833 | 0.686 | 0.702 | 0.697 |
| 0.8–0.9 | 1,057 | 0.839 | 0.850 | 0.838 |
| 0.9–1.0 | 1,252 | 0.914 | **0.946** | 0.935 |

  MS2 修正咗大約三分一嘅中段低估（−5.9pp → −4.1pp）同頂段高估（+3.2 → +2.1pp），但**中段仍然低估 4pp** —— 同 EXP-20261124-70 見到嘅形狀一樣，MS2 冇解決佢。

### 對大細盤精選（`nba_featured`，ROI 口徑）嘅影響
腳本：`patches/nba_s2_forward/featured_replay.py`。用每個賽日 21:00 嗰份 `_prediction_snapshots`（odds＋sidecar），將 milestone 腿嘅 `p_final` 換做 MS2（冇 `p_s2` 嘅腿照用 `p_final`），用凍結規則 `nba-featured-ou-v1`（edge ≥5pp、價 ≤3.0、每日頭 10）重揀，按 ledger 結算。
- 核對：用 `p_final` 重揀，同 live sidecar 嘅 `featured` **98/98 場一樣**。
- 11-12…11-26（14 個有 21:00 快照嘅日；11-19 冇）：

| | 注 | 中 | ROI |
|---|---|---|---|
| 現行（p_final） | 69 | 42 | +7.5% |
| MS2 | 67 | 40 | +9.3% |

- **兩邊只有 19 注一樣**；現行獨有 50 注（27 中、−2.36u）、MS2 獨有 48 注（25 中、−1.31u）。即係換 MS2 會**換走大約七成精選**。
- 69 注嘅 ROI 標準誤大約 ±12pp，差 1.8pp 係噪音，**唔可以話 MS2 對精選好或者差**；只可以講佢會大幅改變揀咩。精選 forward（F250／F1000、v2）而家用 `p_final`，換機率會令佢哋嘅樣本斷開。

## 結論
1. **按預先登記規則：PASS。** MS2 嘅 log-loss 比現行發佈機率低 0.0018，CI 唔跨零；Brier 同校準方向一致。
2. **但機制唔係「S2／新上場時間」**：MSR（舊 S、同樣重擬合）一樣好甚至好少少，MS2 − MSR 跨零。真正有用嘅係**重新擬合**（S 份額由 0.11 升到 0.29–0.35、截距更新、用咗較新嘅 11-03…11-10 數據）。即係話 Kelvin 嘅方向（自己模型佔更大份額）有支持，但 `minutes_v2` 呢部分未證實有貢獻。
3. 同 EXP-20261124-70（`p_final` 事後校準，NEEDS MORE TESTING）係同一件事嘅兩面：現行 MS 係數（10-22…10-28 擬合）已經過時，任何重擬合／再校準都贏佢。兩個唔好疊埋用。

## 判決之後（協議）
- PASS → 可以**申請**將發佈機率換做 MS2，要過 `model-regression-gate`，由 Kelvin 決定。冇改任何 code。
- 建議交 Kelvin 揀（Claude 意見，唔係判決）：
  - (a) 換 MS2（已有 forward 證據，最直接）；
  - (b) 換 MSR（同樣好、少一個依賴 —— 但 MSR 冇自己嘅預先登記 forward 判決，只係次要比較，要另開或者接受佢作為次要證據）；
  - (c) 定期重擬合 MS（根本原因係係數過時），同 EXP-20261124-70 R2／線性 arm 合併成一個 forward。
  - 無論揀邊個，都要決定精選 forward 點處理（換機率 = 精選揀注大換血）。
- 唔准喺同一批數據改係數、改窗再判（協議）。

## 重跑
```bash
python3 docs/experiments/patches/nba_s2_forward/evaluate.py evaluate --force --out <scratch>   # 主判決
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/nba_s2_forward/secondary.py        # Brier／校準
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/nba_s2_forward/featured_replay.py  # 精選重揀
```
數據：`~/WongChoiData/NBA_Market_Eval/ledger/2026-11-12…26.jsonl`；`~/WongChoiData/Wong Choi NBA Analysis/<日> NBA Analysis/_prediction_snapshots/<21:00 run>/`。
