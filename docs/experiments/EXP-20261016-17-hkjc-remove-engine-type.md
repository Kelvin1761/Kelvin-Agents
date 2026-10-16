# EXP-20261016-17 — 剷走 HKJC 段速「引擎型態」：REJECT，未上線

- **日期**：2026-10-16；平台：HKJC；Stage 4 v3 `fixed_rule`（剷走規則，冇 fit）
- **觸發**：Kelvin「引擎型態冇用就剷左佢」—— 前提係 EXP-20261016-14 量到剷走只係 ±0.33pp
- **Code**：main `80c9b842`（完成時間趨勢 ±5 已剷，EXP-20261016-16）；harness production 路徑 + PIT，306 場
- **改動（只喺 branch `claude-hkjc-engine-type-20261016`，冇入 main）**：`features/speed.py` 剷走引擎型態／引擎信心
  計分、`SPEED_MICRO_WEIGHTS` 五個 `engine_*` key、報告重點「段速型態」；測試期望 75.86 → 72.83

## 結果

| 指標 | Δ | 95% CI（賽日 bootstrap） |
|---|---:|---|
| Gold | +0.65pp | [−0.97, +2.22] |
| **Good 位置** | **−1.31pp** | [−3.30, +0.34] |
| top3_capture@5 | +0.33pp | [−0.67, +1.22] |
| NDCG@5 | −0.0034 | [−0.0112, +0.0032] |
| competitive_recall@5 | +0.14pp | [−0.63, +0.80] |
| 實際前三平均名次 | −0.013（越低越好） | [−0.044, +0.017] |

判決：**REJECT / primary_regression**（Good 點估計負，約 −4 場）。221 場排名有郁。

分層：冇 CI 全負，但馬匹數 13–14 Good −2.22 [−4.58, 0.00]、首選 SP 2.6–4 Good −3.23 [−6.82, 0.00]
兩個上界貼 0。

## 同 EXP-20261016-14 唔一致

| 量度時嘅 main | 剷走引擎型態 Gold | Good |
|---|---:|---:|
| `05dd1b20`（完成時間趨勢 −5 仲喺度） | +0.33 | −0.33 |
| `80c9b842`（完成時間趨勢已剷） | +0.65 | **−1.31** |

上一個改動改變咗呢個訊號嘅邊際貢獻（[[retest-orthogonality-changes]] 同一個形狀）：完成時間趨勢 −5
同引擎型態都係「近仗段速形態」嘅訊號，剷走一個之後另一個嘅剩餘資訊變多咗。
「引擎型態冇用」呢個前提喺現行模型**唔再成立**（亦未證明有用 —— CI 跨零）。

## 決定

唔上線。Kelvin 嘅指示係有條件嘅（「冇用就剷」），而現行 main 量到佢可能有用。
code 留喺 branch，由 Kelvin 再決定。**唔好再用 EXP-14 嗰個 ±0.33 做理由剷佢**。

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
git checkout 80c9b842 && python3 $H run --out base.jsonl
git checkout claude-hkjc-engine-type-20261016 && python3 $H run --out cand.jsonl
python3 $H compare base.jsonl cand.jsonl --stage4 fixed_rule --leakage-audit-passed
```
