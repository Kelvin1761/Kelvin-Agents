# EXP-20261016-32 結果 — HKJC 最快第一段（e1_best）入 段速表現

- **登記**：`EXP-20261016-32-hkjc-first-section-protocol.md`（commit `e12a4977`，跑之前已 push）
- **Code**：main `80c9b842`；harness production 路徑 + PIT，`--until 2026-10-10`；286 場配對，31 賽日
- **判決**：**冇 WIN（Holm 後）＋ 全部 |Δ| < MDE → UNRESOLVABLE**。照登記**唔開 forward**，live 冇改。

## 結果（Stage 4 v3 `fixed_rule`）

| K | 變動場 | Gold Δpp [CI] | Good Δpp [CI] | NDCG@5 | cap@5 pp | recall@5 pp | 平均名次 | v3 原始判決 |
|---|---:|---|---|---:|---:|---:|---:|---|
| 2 | 137 | +0.35 [0.00, +1.06] | +0.70 [−0.69, +2.12] | −0.0029 | −0.58 | −0.33 | −0.002 | REJECT（ranking_metric_harm） |
| 4 | 210 | −0.35 [−1.43, +0.71] | +1.40 [−0.33, +3.12] | −0.0009 | −0.47 | −0.44 | −0.017 | REJECT（primary_regression） |
| 6 | 238 | +0.35 [−0.71, +1.45] | +1.05 [−0.35, +2.50] | +0.0041 | +0.23 | −0.12 | −0.041 | RANKING_WIN（未調整） |

**Holm**（3 arm × 6 指標 = 18）：最細原始 p = K=2 top3_capture 0.021 → 0.378；K=6 平均名次 0.041 → **0.697**。
冇一項調整後顯著 → K=6 嘅 RANKING_WIN **唔成立**（合約：Holm 後先可以報 WIN）。

**§6**：所有 arm 所有指標 |Δ| 都細過登記 MDE（K=6 平均名次 0.041 < 0.049；NDCG 0.0041 < 0.0101）→ `UNRESOLVABLE`。

## 分層（Gold／Good Δpp）

| K | 沙田 n191 | 跑馬地 n95 | ≤1200 n144 | 1400–1650 n113 | 1800+ n29 |
|---|---|---|---|---|---|
| 2 | +0.5／0.0 | 0.0／+2.1 | −0.7／+0.7 | +0.9／+1.8 | +3.4／−3.4 |
| 4 | −0.5／+0.5 | 0.0／+3.2 | −2.1／+1.4 | +0.9／+2.7 | +3.4／−3.4 |
| 6 | +0.5／+0.5 | 0.0／+2.1 | −0.7／+1.4 | +0.9／+1.8 | +3.4／−3.4 |

馬匹數／首選 SP 五段：冇 CI 全負。K=4 首選 SP ≤2.5 Gold −2.63 [−8.11, 0.00] 上界貼 0。

## 解讀

- **方向一致偏正**：三個 K 嘅 Good 都係正（+0.70／+1.40／+1.05pp，約 2–4 場），跑馬地 Good 三個都 +2–3pp。
  Gold 同 ranking 指標混合。呢個係今日幾個候選入面最正面嘅，但**閘門分辨唔到**。
- 同前置習慣（EXP-15：Gold 升 Good 跌）形狀相反：前速主要改善首選／次選上名，前置習慣主要郁頭 4 邊界。
- 唔可以因為 K=6 原始判決係 RANKING_WIN 就上線 —— 揀 K=6 = argmax，而且 Holm 後 0.697。

## 點樣先判得到（建議，要另開編號重新登記）

全紀錄 286 場對 +1pp 級別效果冇功效。可行做法：**固定一個 K（取家族中位數 K=4，唔係 argmax），
以 shadow 方式喺 live 每場記錄有／冇呢個訊號嘅排名**，攢到大約一季（~800 場）先判。
要另開實驗編號預先登記，唔可以當今次嘅 forward。

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
python3 $H run --until 2026-10-10 --out base.jsonl
for K in 2 4 6; do WC_FIRST_SECTION_K=$K python3 $H run --until 2026-10-10 \
  --arm docs/experiments/patches/hkjc_arm_first_section.py --out k$K.jsonl; done
for K in 2 4 6; do python3 $H compare base.jsonl k$K.jsonl --stage4 fixed_rule --leakage-audit-passed; done
```
