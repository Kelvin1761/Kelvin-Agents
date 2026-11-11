# EXP-20261111-09 HKJC 頂磅 dummy 重做 ＋ 評分差距 A/B 喺今日 main 重跑

- **日期**：2026-11-11
- **平台**：HKJC
- **觸發**：Kelvin：「重做頂磅 dummy 測試，I think we shall at least first use 官方評分 to replace 用負磅推返評分」
- **搜索過嘅舊記錄**：memory `hkjc-top-weight-is-the-missing-signal`（2026-09-04，調轉前）、EXP-20261029-30（評分差距 arm，
  forward `weight_rating_gap` 30/60）、EXP-20261111-08（well-in REJECT）
- **改到嘅檔案／組件**：**冇。純量度**
- **預先登記**：Part 1 係**重做**舊測試，定義原封照用（頂磅 = 場內宣佈負磅最高；判決 cohort = 模型排名 4+），冇另寫新規則；
  Part 2 用 EXP-20261029-30 原 arm（`hkjc_arm_weight_rating_gap.py`）同原判決規則（`fixed_rule`），冇改

## 語料
- baseline：`hkjc_eval_harness run --dump-matrix`，origin/main `7bc10b28`（之後 main 只有記錄改動）；PIT 回放
- 宣佈負磅、評分由排位表讀（賽前）

## Part 1：頂磅 dummy（模型排名分層，上名率 頂磅 − 其餘，場次 bootstrap 2,000）

讓磅賽 344 場（全部 360 場結果相近）：

| 模型排名 | 頂磅 − 其餘 | 95% CI | n |
|---|---|---|---|
| 1 | −4.94pp | [−17.33, +8.07] | 77 vs 265 |
| 2–3 | +5.06pp | [−5.04, +15.78] | 94 vs 594 |
| 4–6 | +0.90pp | [−8.01, +9.95] | 116 vs 910 |
| 7+ | −0.86pp | [−6.16, +5.32] | 149 vs 2,128 |
| **4+【舊判決 cohort】** | **+1.50pp** | **[−3.34, +6.65]** | 265 vs 3,038 |

舊（2026-09-04，負磅方向調轉之前，193 場）：**+8.7pp [+3.1, +14.3]**。
**調轉之後呢個缺口基本消失**（+1.50pp、CI 跨零）—— 「模型漏咗讓磅官意見」已經由調轉後嘅負磅分補返。

讓磅賽入面「頂磅」同「全場最高評分」揀中**完全同一批馬**（每一格數字一樣）：讓磅賽嘅負磅就係評分。
兩者只喺**底磅壓縮**（評分差距大過磅數範圍）同**非讓磅賽**（呢度 16 場）先唔同。

## Part 2：評分差距 arm（EXP-20261029-30）喺今日 main 重跑，`fixed_rule`

380 場配對，161 場排名有變：

| 指標 | Δ | 95% CI | p | 6 塊 |
|---|---|---|---|---|
| Gold | **+1.05pp** | **[+0.26, +2.12]** | 0.032 | 0, +2.82, +1.41, +1.47, 0, 0 |
| Good 位置 | **−0.53pp** | [−2.07, +0.81] | 0.595 | −1.41, −1.41, 0, 0, 0, 0 |
| top3 capture@5 | −0.18pp | [−0.71, +0.36] | | |
| NDCG@5 | +0.13 | [−0.31, +0.54] | | |
| competitive recall@5 | −0.25pp | [−0.67, +0.16] | | |
| 頭三平均模型名次 | −0.0079（好咗） | [−0.0242, +0.0080] | | |

**判決：REJECT / primary_regression**（Good 點估計 < 0）—— 同 10-29 兩次一樣（當時 Gold +1.16、Good −0.58）。

拆時間：
| 窗 | 場 | 變動 | Gold | Good | NDCG Δ |
|---|---|---|---|---|---|
| 10-30 之前（設計時見過） | 330 | 142 | 45 → 49 | 77 → 76 | +0.0022 |
| **forward 10-30 起**（未見過） | 30 | 10 | 2 → 2 | 4 → 4 | **−0.0083** |

forward 30 場暫時打和，NDCG 微負（forward 過關條件係 Gold／Good／NDCG 全 ≥ 0）；30 場冇功效判。

## 檢查
- **leakage-audit**：PASS —— 負磅、評分、班次全部係排位表賽前資料；冇用賠率
- **golden_scoring**：冇郁；**退步**：冇（冇改 code）

## 結論
1. 頂磅缺口（+8.7pp）喺負磅分調轉之後已經冇咗（+1.50pp 跨零）。
2. 讓磅賽入面負磅同評分係同一樣嘢；改用評分只會影響底磅馬同非讓磅賽。
3. 「評分差距代替負磅」第三次量都係同一個樣：Gold 顯著升、Good 微跌（跨零），按規則 REJECT；
   forward 期間暫時打和。上唔上線係 Kelvin 決定。

**決定**：MEASUREMENT（Part 1）／REJECT 按 `fixed_rule`（Part 2，交 Kelvin 決定）
**commit**：未 commit 任何 model code

## 重跑
```bash
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --out base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_top_weight_dummy.py base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 $H run --arm docs/experiments/patches/hkjc_arm_weight_rating_gap.py --out gap.jsonl
python3 $H compare base.jsonl gap.jsonl --stage4 fixed_rule --leakage-audit-passed
```
