# EXP-20261016-15 結果 — HKJC 前置習慣（近仗第一沿途位）

- **登記**：`EXP-20261016-15-hkjc-early-habit-protocol.md`（commit `ff12dac1`，跑之前已 push）
- **Code**：main `05dd1b20`；harness `hkjc_eval_harness.py`（production 路徑 + PIT），`--until 2026-10-10`
- **樣本**：286 場配對（剔 04 月 speed_score 死日），31 個賽日
- **判決**：**REJECT**（三個 arm 都冇 WIN）→ 照登記**唔開 forward**，live 冇改

## 結果（Stage 4 v3 `fixed_rule`）

| K | 變動場 | Gold Δpp [CI] | Good Δpp [CI] | NDCG@5 | cap@5 pp | recall@5 pp | 平均名次 | 判決 |
|---|---:|---|---|---:|---:|---:|---:|---|
| 3 | 115 | **+1.40 [+0.34, +2.75]** | −1.05 [−2.53, +0.36] | +0.0018 | +0.23 | −0.07 | −0.006 | REJECT（primary_regression） |
| 6 | 184 | +0.70 [−1.04, +2.38] | +0.00 [−1.38, +1.43] | −0.0002 | +0.12 | −0.38 | −0.005 | REJECT（ranking_evidence_too_weak） |
| 9 | 216 | +0.70 [−1.04, +2.38] | −0.35 [−2.14, +1.42] | −0.0040 | +0.12 | −0.72 | −0.002 | REJECT（primary_regression） |

時間塊（6 塊，pp）：K=3 Gold `0, +2, +2, +2, 0, +2.4`、Good `−2, −2, +2, −3.9, 0, 0`。

**Holm**（3 arm × 6 指標 = 18）：最細原始 p 係 K=3 Gold 0.038 → 調整後 **0.684**。冇任何一項顯著。

接線：三個 arm 分別改咗 115／184／216 場排名，冇「同 baseline 一模一樣」問題。

## §6 功效

所有 arm 所有指標嘅 |Δ| 都細過登記嘅閘門 MDE（Gold ±1.96、Good ±1.76、NDCG ±0.0101…）。
照登記，效果大細屬**閘門分辨唔到**；但 v3 判決本身係 REJECT，兩者結論一樣：**唔上線、唔開 forward**。

## 分層（Gold／Good Δpp）

| K | 沙田 n191 | 跑馬地 n95 | ≤1200 n144 | 1400–1650 n113 | 1800+ n29 |
|---|---|---|---|---|---|
| 3 | +2.1／−2.1 | 0.0／+1.1 | +0.7／−1.4 | +1.8／−0.9 | +3.4／0.0 |
| 6 | +1.6／−1.0 | −1.1／+2.1 | −0.7／−0.7 | +1.8／+0.9 | +3.4／0.0 |
| 9 | +1.6／−0.5 | −1.1／0.0 | −0.7／−1.4 | +1.8／+0.9 | +3.4／0.0 |

一致嘅只有：Gold 微升、Good 微跌 —— 前置馬多咗入頭 4，但首選／次選上名冇改善。
1800+ 只有 29 場，冇意義。

## 解讀

- EXP-20261016-14 量到嘅 cohort 差距（模型 4–6 名：前置 33.9% vs 後上 20.9%）**冇轉化成排名收益**。
  同 [[au-cohort-gap-is-not-a-gain]]、[[au-settle-position-accurate-covered-orthogonal-still-fails]] 同一個形狀。
- 可能原因（未驗證）：(1) 習慣只係 49% 準（EXP-20261010-12 ρ 0.49），一半「前置馬」今仗唔前置；
  (2) 細幅度（K=3 最多 ±2 段速分 ≈ 0.26 綜合分）主要喺頭 4／頭 5 邊界調位，所以 Gold 郁、Good 唔郁；
  (3) 診斷用 live 分數（非 PIT）量 cohort，可能高估。
- D12 門檻（Kelvin 2026-10-16 決定唔適用）同今次結果冇衝突：門檻唔係擋住佢嘅原因，數據先係。

## 唔好再試同一樣嘢

同一個定義（近 3 仗第一沿途位 ≤3 比例，加落段速）唔好再換 K 重跑 —— 換幅度救候選 = REJECT。
值得試嘅係**唔同資訊**：今仗步速形勢 × 習慣（例如場內冇其他前置馬時先加），或者官方 Speedmap 有存檔之後。
任何新版本要另開編號、重新登記。

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
python3 $H run --until 2026-10-10 --out base.jsonl
for K in 3 6 9; do WC_EARLY_HABIT_K=$K python3 $H run --until 2026-10-10 \
  --arm docs/experiments/patches/hkjc_arm_early_habit.py --out k$K.jsonl; done
for K in 3 6 9; do python3 $H compare base.jsonl k$K.jsonl --stage4 fixed_rule --leakage-audit-passed; done
```
