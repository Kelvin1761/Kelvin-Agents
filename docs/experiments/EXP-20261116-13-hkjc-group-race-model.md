# EXP-20261116-13 — HKJC：分級賽專用模型（方向 c）—— dev PASS（Holm）、holdout CI 啱啱跨零 → REJECT

- 日期：2026-11-16｜Kelvin「a 之後做 b 同 c」。baseline = `v4/incident_I1.jsonl`。腳本 `patches/hkjc_group_model/build.py`。
- 分級賽 223 場（每季 31）。只郁分級賽，其他場次不變；尺用 v4 全窗（唔改尺）。

## 候選（預先登記，Holm 2）
分級賽 raw += Σγ_k·(9 個外層維度 − 場均) + β_r·(評分 − 場均)/10 + β_w·(負磅 − 場均)/10；之前季分級賽逐季 walk-forward 嘅 L2 logistic（raw 欄唔受罰）。
| 候選 | 2026 β（評分／負磅） | dev Δlog-loss | Holm | holdout |
|---|---|---|---|---|
| G2a C=0.01 | +1.96／−2.30；維度 γ 全部 ≤ 0.15 | **−0.00016 [−0.00028,−0.00004]** PASS | p≈0.005，97.5% 上界 −0.00004 ✅ | −0.00018 [−0.00038,**+0.00001**]、AUC +0.0003、Gold／Good 0.00 → REJECT |
| G2b C=0.1 | +3.18／−3.95 | −0.00018 [−0.00040,+0.00005] | p≈0.067 ❌ | 冇開 |

## 解讀
- 分級賽入面模型要做嘅主要係**評分加分、負磅扣分**（同 EXP-20261116-07 拆解一致：分級賽負磅唔跟評分），維度權重基本唔使改（γ 細）。
- dev／holdout 同方向同幅度，但 holdout 上界 +0.00001 → 按 v4 規則 REJECT，冇上線。
- 冇開 forward shadow：分級賽每季 31 場，forward 要幾年先夠；而且 `weight_rating_shadow`（EXP-07 HR）已經包分級賽負磅＋評分。交 Kelvin 決定。
