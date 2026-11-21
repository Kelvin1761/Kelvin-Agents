# EXP-20261121-30 結果：濕地 overlay 按濕度調幅度 —— REJECT

- **預先登記**：[protocol](EXP-20261121-30-au-wet-overlay-by-wetness-protocol.md)（`75e757b7`，量度之前 push）。
- **baseline**：`FINAL.json`（main `1c33b058` 評分），3,736 場、99 個賽日。碼：`scratch/au_wet_scale_wf_20261121.py`。
  證據：`EXP-20261121-30-evidence/`（判決、逐日倍數）。
- **決定**：**REJECT / primary_regression**。冇改動。

## 擬合出嚟嘅倍數（m = 1 即現行）

| 日期 | 大爛地 | Soft 7+ | 其他軟地 |
|---|---:|---:|---:|
| 08-27 | 1.22 | 1.28 | 1.78 |
| 09-26 | 0.98 | 0.68 | 0.85 |
| 10-26 | 1.08 | 0.27 | 0.50 |
| 11-12（最後） | 1.18 | 0.31 | 0.45 |

數據**唔**支持「大爛地 overlay 要加重」：大爛地倍數一直喺 1 附近（0.98–1.22），即係現行幅度已經差唔多啱。
反而軟地（Soft 7+、Soft ≤ 6）倍數隨數據增加跌到 0.3–0.45 —— 即係 overlay 喺軟地可能太重；但呢個方向未證實（見下面判決）。

## v3 walk_forward_oos（郁咗 1,391 場、11,618 匹）

| 指標 | Δ | 95% CI | 時間塊 ≥0 |
|---|---|---|---|
| Gold | −0.19pp | [−0.39, +0.03] | 2/6 |
| Good | +0.05pp | [−0.18, +0.29] | 3/6 |
| top3@5 | −0.03 | [−0.15, +0.10] | |
| ndcg@5 | +0.03 | [−0.08, +0.14] | |
| top5 AUC | −0.00 | [−0.08, +0.08] | |

分層 CI 全負：≤8 匹 Gold、1201–1600m Gold、首選前置 Gold。按地況：大爛地 Gold −1.0pp [−2.5, 0]、Good 0；
Soft 5–6 Gold −0.42 [−0.85, 0]；Soft 7+ Gold +0.39、Good +0.78（CI 跨零）。

## 解讀（答用戶「大爛地點改善」）

- 大爛地 overlay 冇被低估，所以「加重濕地往績」唔係出路。
- 大爛地嘅弱點喺往績類 leaf 唔轉移（近績質素 −0.039 AUC、近績 −0.037、練馬師 −0.035）。
  而家唯一針對呢點、有正面證據嘅係 **EXP-20261105-06 H2**（大爛地近績質素用返舊公式）：v3 大爛地 Good +2.59pp [+0.52, +5.29]、
  整體 PRIMARY_WIN，但 §8 冇功效；forward 跟緊（11-20 時 15／200 場）。
- 軟地倍數向下嘅走勢值得記低，但今次係單一 arm 嘅副產品，唔准據此再開「軟地減半」（EXP-20260822-03 已經試過整體減半打和）。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 scratch/au_wet_scale_wf_20261121.py "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/FINAL.json" OUTDIR
```
