# EXP-20261116-02 結果：AU 外層權重 walk-forward refit —— R、RF 都 REJECT（排序變差）

- **預先登記**：[protocol](EXP-20261116-02-au-outer-refit-protocol.md)（`9bc8703d`，跑之前 commit）。
- BASE = `FINAL.json`，2026-08-05 起 3,736 場，v3 `walk_forward_oos`，賽日 bootstrap 2000。A/A replica 最大差 0.000098 ✅。
- 每 7 個賽日 refit 一次，共 12 次；最後一次用 35,026 匹。冇 model code 改動。

| arm | Gold | Good 位置 | top3 capture@5 | NDCG@5 | top5 AUC | 判決 |
|---|---|---|---|---|---|---|
| **R**（pace_perf 固定，其餘五維 fit） | −0.51 [−1.22, +0.23] | −0.78 [−1.66, +0.09] | +0.03 | −0.14 | **−0.30 [−0.57, −0.03]** | **REJECT** |
| RF（六維全 fit） | −0.64 [−1.40, +0.14] | −0.72 [−1.64, +0.22] | −0.04 | −0.14 | **−0.37 [−0.69, −0.07]** | REJECT |

場數（R）：Gold 21.49% → 20.99%、Good 27.03% → 26.26%、Pass 50.29% → 49.87%。
R 分層 CI 全負：軟地 5–6／7+（Good）、≤1200m（Good）、首選前置（Gold）、首選距上仗 <90 日（Gold）。

## 權重點樣郁（R）

| 維度 | 現行 | 第一次 fit（08-26） | 最後一次 fit（11-11） |
|---|---|---|---|
| stability | 0.336 | 0.080 | 0.226 |
| pace_perf | 0.088 | 固定 | 固定 |
| jockey_trainer | 0.842 | 0.773 | 0.806 |
| class_weight | 0.376 | 0.493 | 0.282 |
| track | 0.096 | 0.173 | 0.133 |
| preparation | 0.187 | 0.317 | 0.389 |

早期 fit（得 20 日數據）郁得好大（stability 跌到 0.08），之後慢慢收返；最後一次 fit 主要係「準備（試閘）」×2、「狀態穩定性」同「級數」減。
RF 嘅 pace_perf 由 0.088 升到 0.110（自由 fit 都唔會調低段速）。

## 點解 HKJC 贏、AU 輸

- **樣本**：HKJC 用 6,047 場忠實回放 fit，AU 乾淨語料只有 3,736 場，而且 walk-forward 頭幾次 fit 只得幾百場，權重晃動大，嗰段時間嘅排名變差。
- **把尺對象唔同**：logistic 優化逐匹入位機率；v3 主指標係頭四覆蓋。HKJC 嘅現行權重係喺評估窗調出嚟（EXP-20261113-05），
  所以 refit 有空間；AU 現行權重已經係多次 refit／共識（ae71927、EXP-20260928-02、EXP-20261105-05）嘅結果，冇同樣嘅「舊權重錯配」。
- 同 EXP-20260928-02（2,853 場）同 EXP-20261101-39（3,246 場診斷）一致：AU 現行權重喺入位 logistic 意義上已經接近最優，再 fit 只係加噪音。

## 決定

唔用。兩個 arm 都 top5 AUC CI 全負，有分層 CI 全負，唔係「冇代價」。RP arm 冇跑（EXP-20261116-01 P 冇過）。
要喺 AU 做 HKJC 式大回放，先要有 2026-08 之前嘅 point-in-time 輸入（而家冇），呢個係數據工程問題，唔係權重問題。

## 可重現

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_outer_refit_20261116.py \
  "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/FINAL.json" \
  "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-outer-refit-20261116"
```
判決 JSON、逐次權重：`EXP-20261116-02-evidence/`。
