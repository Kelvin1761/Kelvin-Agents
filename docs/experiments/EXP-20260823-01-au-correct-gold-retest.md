# EXP-20260823-01 用 contract 嘅 `gold` 重測；搜索目標改 `place`

- **日期**：2026-08-23
- **平台**：AU
- **假設**：2026-08-22 全日嘅分析用錯咗 `gold` 嘅定義。用 contract 嘅正確定義重測，
  幾個「gold 升但 t3prec/pass 跌」嘅 trade-off 候選會變成純蝕。
- **改到嘅檔案**：`au_matrix_refit.py`（`--obj` 預設 balanced → place）、
  `docs/model-evaluation-contract.md`（記錄目標改動 + `gold` 定義警告）

## 起因：一個貫穿全日嘅指標錯誤

`eval_metrics.py:235` 寫得好清楚：

> `gold` 由「頭三揀全部上名」改成 **「實際前三全部落喺模型頭四揀之內」**。
> Kelvin 要追嘅係捕捉率 —— 三隻上名馬有冇一隻走漏。

但 2026-08-22 全日嘅 harness 計嘅係 `any(pos == 1 for 模型 top-4)` ——
**「頭馬喺我 top-4 之內」**，一個我自己發明、而且撞名嘅指標。我甚至叫佢 `gold@4`。
memory `au-gold-is-capture-at-four` 早就寫過警告，我讀成「頭馬喺 top-4」。

三個唔同嘅嘢，唔可以混住講：

| 名 | 定義 |
|---|---|
| `gold`（contract） | 實際前三**全部**落喺模型 top-4（捕捉率）|
| `gold_strict` | 模型 top-3 **全部**上名 |
| 我發明嘅 `gold@4` | **頭馬**喺模型 top-4（唔喺 contract）|

## 重測（653 場，contract 排除前三不足 3 匹嘅場次）

baseline（現行引擎 + 證據厚度安全欄）：
Gold **21.29%**、Good位 28.02%、Pass 52.53%、t3prec 50.74%、首選上名 60.49%

| 候選 | Gold(捕捉率) | Good位 | Pass | t3prec | 首選上名 |
|---|---|---|---|---|---|
| pace_perf → 0.100 | −0.14 | −1.39 | +0.34 | −0.29 | −0.62 |
| pace_perf → 0.080 | +0.16 | **−2.43 ❌** | −0.10 | −0.19 | **−1.83 ❌** |
| pace_perf → 0.060 | −0.13 | −1.57 | −1.25 | −0.76 | **−1.86 ❌** |
| pace_perf → 0.000 | +0.63 | −1.73 | −0.92 | −0.67 | −1.33 |
| 剷濕地 overlay | −0.17 | −0.46 | +0.12 | −0.16 | −0.77 |
| 剷 overlay + pace_perf 0.08 | −0.32 | −0.94 | −0.90 | −0.29 | −1.82 |
| track_score 偏離 ×0.6 | +0.16 | −0.76 | −0.15 | −0.21 | −0.46 |
| track_score 偏離 ×0.0 | +0.15 | −0.60 | −1.52 | −0.56 | −1.23 |
| PF×PI 矛盾 ×0.50 | −0.46 | **−1.08 ❌** | −0.75 | −0.35 | +0.00 |
| PF×PI 矛盾 ×0.00 | −0.46 | **−1.39 ❌** | −0.76 | −0.52 | +0.15 |

**每一個「gold 升」嘅好處都消失。** 之前報嘅 `gold@4 +1.00 / +1.17 / +1.33 / +1.50`
（減 pace_perf）同 `+0.33`（剷 overlay）全部係我發明嗰個指標。用 contract 嘅 `gold`
睇，佢哋係**純蝕**，而且幾個變成**顯著**蝕。

**結論不變（仍然 REJECT），但理由更強** —— 之前叫「trade-off」，其實係單邊損失。

## 意外收穫：負磅（`weight_score`）加法版

| | Gold | Good位 | Pass | t3prec | 首選上名 |
|---|---|---|---|---|---|
| `rating .70 + weight .35`（加法）| +0.16 | **+0.92 [+0.2,+1.8] ✅** | +0.46 | +0.05 | −0.01 |

walk-forward Good位 **3/3 全正**（+1.23/+0.61/+0.61），四個幅度（w .20/.35/.50、
r.60/w.35）全部從未負。lockstep 檢查：class_weight 場內 SD 由 9.667 **窄** 4.5%
到 9.231（`weight_score` 大部分停喺 60，係攤薄唔係放大）；把權重除返個比例鎖住
影響力之後五個指標**一模一樣** → 收益唔係偷偷 re-weight 換嚟。

⚠️ **但唔 ship。** 三個 contract test 明文守住「`weight_score` 退出排名」，理由記錄
係 **AUC 0.480**（我自己重量係 0.4928 —— 標準單一 leaf 判別力**低過隨機**）。
一個 AUC < 0.5 嘅 leaf 加落去改善 Good位，最可能嘅機制係**同 rating 高度相關，
所以加佢等於對 rating 做方差收縮（ensembling）而唔係加新資訊** —— 呢個同 SD 窄咗
4.5% 一致。但呢個係事後合理化，而且五個指標只有一個顯著。

推翻一個有記錄、有 AUC 依據嘅決定，唔應該靠一個指標。**決定：NEEDS MORE TESTING**，
code 已 revert。要 ship 就應該先獨立驗證「方差收縮」呢個機制（例如直接測
`0.5×rating + 0.5×weight` 嘅收縮版，同埋分層睇 rating 缺失／齊全兩批）。

## 搜索目標改 `place`（用戶決定）

`au_matrix_refit.py` 嘅 `--obj` 預設由 `balanced` 改為 `place`：

| preset | keys |
|---|---|
| `balanced`（舊預設）| gold, good_pos, pass, champ, winT3, t3prec, mrr, ndcg5, blowout |
| **`place`（新預設）** | **gold, good_pos, pass, t3prec** |

理由：本 project KPI 係上名捕捉。`balanced` 會令搜索用 `champ`/`winT3`/`mrr`
買走 `pass`/`t3prec`。已記入 `docs/model-evaluation-contract.md`（判決規則真源）。

⚠️ **歷史可比性**：2026-08-01 / 08-03 / 08-08 三次已 ship 嘅重 fit 都係 `balanced`
出嘅。要同嗰啲紀錄對比就要明確傳 `--obj balanced`。已寫入 contract 同 `--help`。

## 檢查
- **run_tests.sh**：九個 suite 全綠
- **contract**：已更新（新增「搜索目標」一行 + `gold` 定義警告）

## 結論

**決定**：`--obj place` **KEEP**；十個 trade-off 候選 **REJECT**（理由比之前更強）；
負磅加法版 **NEEDS MORE TESTING**（已 revert）
