# EXP-20261016-32 — HKJC 最快第一段（e1_best）入 段速表現：預先登記

- **登記日期**：2026-10-16，喺跑任何 arm **之前** commit
- **平台**：HKJC；**Stage 4 v3 `fixed_rule`**（固定分段同固定 K，冇 fit）
- **觸發**：Kelvin「有前速就有機會搵到好位，第一段有速度可以加少少分」；篩選 EXP-20261016-31：
  e1_best 獨立 AUC 0.565、對模型 ρ +0.07、對今仗第一沿途位 ρ −0.42，增量 ΔΔLL +0.0084 [−0.0023, +0.0193]。

## 候選（固定，唔准改）

- **輸入**：Facts「全段速剖面」近 6 仗 Δ1（對 HKJC 標準時間；負 = 快），按表頭搵 Δ1 欄。
- **m** = 近 6 仗最細 Δ1（最快嗰仗）。有效仗數 < 2 → 唔加減。
- **分段**（加落 `speed_score`，clip 0–100）：

| m（秒） | 加減 | 篩選語料上名率 |
|---|---:|---:|
| < −0.3 | +K | |
| −0.3 ～ 0 | +K/2 | 28.2%（< 0 合計） |
| 0 ～ 0.3 | 0 | 23.7% |
| 0.3 ～ 0.6 | −K/4 | 21.3% |
| ≥ 0.6 | −K/2 | 13.7%（0.6–1.0） |

- **家族**：K ∈ {2, 4, 6}，三個 arm；Holm 調整（3 arm × 6 指標）。
- **實作**：`docs/experiments/patches/hkjc_arm_first_section.py`，`WC_FIRST_SECTION_K=2|4|6`。
  包住 `_load_formline_opponent_summaries` 注入 `first_section_min_delta`，patch `engine_core.SpeedScorer`。
  接線證明：`races_with_ranking_change > 0`。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
python3 $H run --until 2026-10-10 --out base.jsonl
for K in 2 4 6; do WC_FIRST_SECTION_K=$K python3 $H run --until 2026-10-10 \
  --arm docs/experiments/patches/hkjc_arm_first_section.py --out k$K.jsonl; done
for K in 2 4 6; do python3 $H compare base.jsonl k$K.jsonl --stage4 fixed_rule --leakage-audit-passed; done
```

- **全紀錄窗口**：語料開始 → **2026-10-10**；main `80c9b842`。
- 判決：`evaluate_full_record`，v3 次序；Holm 後先報 WIN。
- **分層（只報，唔用嚟救）**：沙田／跑馬地、馬匹數、路程段、首選 SP 五段。任何場地 Gold 或 Good 點估計 < 0 → ⚠️。

## §6 功效前置（量度前寫低）

閘門 MDE（EXP-20261016-14 同語料 CI 半寬）：Gold ±1.96pp、Good ±1.76pp、top3_capture@5 ±1.51pp、
NDCG@5 ±0.0101、competitive_recall@5 ±0.0101、平均名次 ±0.049。三個 arm 全部 |Δ| < MDE → `UNRESOLVABLE`。

## Leakage audit（已做，PASS）

- Facts 全段速剖面 21,980 行，**0** 行日期 ≥ 賽日。只用過往賽事分段。
- 標準時間：HKJC 官方「標準時間」頁（`hkjc_standard_times.json`，2026-08-25 版）。可能由包括語料期間嘅賽季計出，
  但每個（場地、路程、班次）係一個常數，唔含任何單場結果；風險低，照實披露。
- 冇用賠率、今仗沿途位或賽果。

## 已知偏差

EXP-20261016-31 篩選**已經睇過**同一語料（方向、分段上名率）。分段門檻係由嗰張表揀嘅。
所以全紀錄結果只算篩選，WIN 一定要過 forward 先可以上線。

## Forward 確認（只開一次）

- **窗口**：2026-10-17 起嘅 HKJC 賽日，累積 ≥ 60 場先開。
- **K**：全紀錄有 WIN 嘅 arm 入面取 K 中位數（唔准 argmax）；冇 WIN → 唔開 forward，記 REJECT。
- **判決（寫死）**：Gold Δ ≥ 0、Good Δ ≥ 0、NDCG@5 Δ ≥ 0 → 可以提交上線；任何一項 < 0 → REJECT。
  唔准換指標、換窗口或重開。
- 上線前要將 Δ1 由 Facts 正式接入 Logic `_data`（唔係靠 arm 注入）。

## 結果

見 `EXP-20261016-32-hkjc-first-section-results.md`：**UNRESOLVABLE**（Holm 後冇 WIN，全部 |Δ| < MDE），冇開 forward。
