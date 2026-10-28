# EXP-20261028-11 結果：近績質素分按場數收縮 + 獎金 z 封頂 —— REJECT

- **預先登記**：[protocol](EXP-20261028-11-au-form-quality-sample-size-protocol.md)（`945bbbdb`（rebase 前 `75f54ce8`），量度之前）。
- **語料**：`scratch/au_fq_weight_class_dump_20261028.py` @ `945bbbdb`（rebase 前 `75f54ce8`）（main `52e12fe9` 引擎），3,818 場；
  v3 乾淨窗 2026-08-05 起 2,948 場（完整賽果）；§8 扣 warmup 後 2,012 場／53 個賽日。
- **replica**：leaf 誤差 ≤ 0.00076（dump 存 6dp）；綜合分 37／37,560 匹差 > 0.001，最大 0.0038，全部係維度分 2dp 捨入跨邊界。
- **決定**：A1、A2、A3 全部 **REJECT**。冇改動上線。

## 收縮常數（只用 run_date < 2026-08-05，冇賽果）

| | μ | k | 馬內變異 | 馬間真變異 | 馬 | 仗 |
|---|---:|---:|---:|---:|---:|---:|
| A1（原值） | 0.111 | **0.80** | 0.217 | 0.272 | 9,839 | 46,076 |
| A3（封頂後） | 0.075 | **1.05** | 0.199 | 0.189 | 9,839 | 46,076 |

k = 0.80 即係 2 場馬（W = 1.8）保留 69%、6 場馬（W = 3.3）保留 80% —— 兩者分別細。

## 描述

**少場數馬冇被系統性高估。** 模型名次層內剩餘超額（baseline）：

| 計分場數 | 頭 3 名 | 4–6 名 | 7+ 名 |
|---|---:|---:|---:|
| 2 | +13.9pp | −1.2pp | −8.9pp |
| 3 | +19.5pp | +5.2pp | −7.0pp |
| 4 | +17.3pp | +4.2pp | −10.4pp |
| 5 | +13.7pp | 0.0pp | −10.7pp |
| 6 | +15.7pp | −1.1pp | −12.1pp |

2 場馬喺頭 3 名稍為差少少（+13.9 vs +15.7），但 7+ 名反而跑得好過 6 場馬（−8.9 vs −12.1）—— 即係被排低嘅少場數馬
其實被**低估**，唔係高估。分佈：2 場 SD 21.5、6 場 SD 19.7；≥85 分佔比 13.6% vs 9.6%。

## 判決

| arm | 改到場數 | v3 fixed：Gold | Good | ranking | 分層 CI 全負 | §8 refit B1−B0 Gold／Good |
|---|---:|---|---|---|---|---|
| A1 收縮 | 2,062 | −0.23 [−0.56, +0.07] | −0.03 | 全部跨零 | **≤8 匹 Good、首選 $1–3 Gold** | −0.30／−0.05 |
| A2 封頂 | 1,641 | −0.07 [−0.48, +0.37] | −0.27 [−0.73, +0.13] | 全部跨零（+0.0012–0.0013） | 冇 | −0.35／−0.34 |
| A3 兩樣 | 2,543 | −0.20 [−0.73, +0.32] | −0.20 [−0.81, +0.36] | **三個 CI 全正**（top3 +0.0030 p 0.009） | 冇 | −0.70／−0.44 |

v3：三個都 `primary_regression`（Gold／Good 點估計 < 0）。§8：fixed、refit、live guard 全部 REJECT，Holm p 1.0。
A3 本身亦被預先登記嘅 ablation 規則擋住（A1 Gold、A2 Good 點估計都 < 0）。

## 解讀

- 用戶嘅擔心（少場數馬因為平均數變異大而被推高）喺數據入面**唔成立**：少場數馬冇喺頭 3 名被高估，反而喺低名次被低估。
  收縮將佢哋再拉向平均，方向錯。
- 獎金封頂令排名指標（AUC、NDCG、top3 捕捉）細微向好，但 Gold／Good 跌 —— 即係改善喺「頭 5 名入面次序」，
  唔係「揀中前三」。Quarterback 嗰種「大賽跑包尾算最好一仗」係真嘅，但平均落嚟大賽包尾嘅馬確實有料，
  封頂之後反而睇低咗佢哋。
- 呢個係 EXP-20261016-06 窗嘅第四個 family，冇一個上線。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 X=<外置碟 scratch>
python3 scratch/au_fq_weight_class_dump_20261028.py --out $X/dump_base.json           # @945bbbdb
python3 scratch/au_fq_weight_class_eval_20261028.py --dump $X/dump_base.json --outdir $X/arms
python3 scratch/au_fq_weight_class_judge_20261028.py $X/arms/base.json $X/arms/A1.json $X/v3/A1.json --extra runs
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_walkforward_refit.py predict --data $X/arms/A1.json --out $X/wf/A1.json
python3 scratch/au_paceperf_s8_20261016.py --base $X/wf/base.json --cand $X/wf/A1.json --label A1 --out $X/s8/A1.json
```

證據：`EXP-20261028-11-evidence/`（describe、v3_A*、s8_A*）。
