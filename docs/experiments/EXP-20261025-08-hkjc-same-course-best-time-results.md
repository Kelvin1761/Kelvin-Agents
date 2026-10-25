# EXP-20261025-08 結果：HKJC 同程最佳時間＋最快 L400

- **登記**：`EXP-20261025-08-hkjc-same-course-best-time-protocol.md`，commit `0e3d06f6`，跑 arm 之前已經 push
- **Code**：main `a84e44d7`，加埋賽果庫修正（`build_comprehensive_stats.result_row`）；harness production 路徑＋PIT，`--until 2026-10-21`
- **樣本**：364 場配對，37 個賽日；剔走 20 場死欄位或者唔成對；sample_hash `a56b47ec…`
- **判決**：**4 個 arm 全部 REJECT（primary_regression）**。Holm 調整之後冇 WIN，照登記**唔開 forward**，live 冇改。

## 結果（Stage 4 v3 `fixed_rule`）

| Arm | 變動場 | Gold Δpp [CI] | Good Δpp [CI] | cap@5 pp [CI] | recall@5 pp | NDCG@5 | 平均名次 |
|---|---:|---|---|---|---:|---:|---:|
| A K=3 | 226 | −0.27 [−1.57, +0.84] | −1.65 [−3.79, +0.27] | +0.46 [−0.00, +1.00] | +0.15 | −0.001 | −0.004 |
| A K=6 | 290 | −0.82 [−3.05, +1.65] | **−2.20 [−4.18, −0.54]** | +0.64 [−0.09, +1.44] | +0.43 | −0.001 | −0.020 |
| A K=9 | 317 | −1.10 [−3.56, +1.43] | −1.92 [−4.41, +0.55] | **+1.10 [+0.28, +1.92]** | **+0.84** [+0.10, +1.58] | −0.002 | −0.038 |
| B 最快 L400 | 280 | −0.55 [−2.44, +1.15] | +0.27 [−1.61, +2.20] | **+1.19 [+0.18, +2.19]** | +0.66 | +0.004 | −0.019 |

**Holm**（4 arm × 6 指標 = 24 次）：最細嘅原始 p 係 A9 top3_capture@5 0.007 → 調整後 0.168；A6 Good −2.20pp 0.019 → 0.437；B top3_capture 0.027 → 0.567。冇一項調整後仲顯著。

接線：4 個 arm 嘅 `races_with_ranking_change` 都 > 0（226–317 場），兩邊都有接通。

## 分層（Gold／Good Δpp）

| Arm | 沙田草地 n224 | 跑馬地 n130 | 沙田泥地 n10 | 直路 1000 n20 | 今季 26/27 n124 |
|---|---|---|---|---|---|
| A3 | 0.00／−1.79 | −0.77／−1.54 | 0／0 | −5.0／−5.0 | −0.81／0.00 |
| A6 | −1.34／−1.79 | 0.00／−3.08 | 0／0 | −5.0／−5.0 | −3.23／−0.81 |
| A9 | −1.79／−0.45 | 0.00／−4.62 | 0／0 | −5.0／−5.0 | −2.42／0.00 |
| B | 0.00／0.00 | −1.54／+0.77 | 0／0 | −5.0／0.00 | −1.61／+1.61 |

⚠️ A 嘅三個 K，Good 喺沙田草地同跑馬地都係負，跑馬地跌得最多。

## 解讀

- **同程最佳時間個訊號係真，但加錯咗位。** 佢穩定噉將上名馬拉入頭 5：A9 top3_capture@5 喺 6 個時間塊全部正數，competitive_recall 亦一樣向上。但係佢同時將原本啱嘅首選／次選推走，所以 Good 喺三個 K 都跌 1.6–2.2pp。篩選嗰陣量嘅係「上唔上名」嘅整體排序（AUC／ΔΔLL），所以見到正數。閘門嘅主指標睇嘅係頭 2 位，就係呢度輸。
- **K 愈大，ranking 指標愈好，但 Gold 愈差**（−0.27 → −0.82 → −1.10pp）。即係話，加分加得愈多，對頭 1–2 位嘅干擾就愈大。
- **B（最快 L400）**：Good 打和（+0.27），top3_capture 偏正，Gold 偏負。同篩選一樣：上仗 L400 換做最快 L400，冇帶嚟可以證明嘅改善。Kelvin 個建議「換做最快末段」答案係：**唔會差好遠，但冇證據話好啲，所以維持上仗 L400。**
- 呢個形狀同 EXP-20261016-15（前置習慣：Gold 升、Good 跌）同 EXP-20261016-52（e1_best：Good 升、Gold 混合）都唔同。同程時間郁嘅係**頭 5 嘅邊界**，唔係首選。

## 冇做、要另外登記嘅嘢（建議，未登記）

- 用同程時間只決定**頭 4／5 邊界**（例如只喺 rank 3–6 之間重排），唔郁首選、次選。呢個係由今次結果推出嚟嘅新假設，**一定要另開編號、喺新窗口驗證**，唔可以用今次嘅語料去揀規則。
- 報告層：喺賽事分析顯示「同程時間全場最快／差距」，唔入分。呢個唔需要過閘，但要先問 Kelvin 想唔想要。

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
P=docs/experiments/patches
python3 $H run --until 2026-10-21 --out base.jsonl
for K in 3 6 9; do WC_SAME_COURSE_K=$K python3 $H run --until 2026-10-21 \
  --arm $P/hkjc_arm_same_course_best_time.py --out a$K.jsonl; done
python3 $H run --until 2026-10-21 --arm $P/hkjc_arm_best_l400.py --out b.jsonl
for f in a3 a6 a9 b; do python3 $H compare base.jsonl $f.jsonl --stage4 fixed_rule --leakage-audit-passed; done
```

Arm A 需要賽果庫修正已經喺 code 入面。冇呢個修正，2026-05-13 之後嘅同程時間係空，結果會唔同。
