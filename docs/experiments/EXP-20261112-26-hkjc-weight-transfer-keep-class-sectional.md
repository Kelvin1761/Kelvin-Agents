# EXP-20261112-26 — HKJC 權重遷移：保留評分與經驗／保留段速版

- 日期：2026-11-13
- 平台：HKJC
- 決定：**REJECT（四個版本）**
- 前置：EXP-20261112-25（T100／T50 REJECT：評分與經驗被遷移到 0，Gold／Good 跌）

## 假設

EXP-25 失敗可能因為賽果庫量唔到「評分與經驗」同「段速」本身（只有輸頭馬等級做代理），所以將呢兩個維度釘住現行份量，
只喺其餘維度之間按賽果庫 β/SD 重配。

Kelvin 2026-11-13：「賽果庫冇匹馬自己嘅分段時間……we should not use it to adjust our model」、
「段速表現 should be the most important factor」→ **只有 S 版（保留段速）係合資格候選**；K 版預先登記咗，照報但唔算。

## 方法

- 腳本：`patches/hkjc_weight_transfer_keep_class.py`（生成 `transfer_keep.json`），arm `patches/hkjc_arm_weight_transfer.py`
- K100／K50：保留 class_advantage，其餘四個（stability、trainer_signal、sectional、race_shape）重配（100%／50% 移向賽果庫份量）
- S100／S50：保留 class_advantage 同 sectional，只重配 stability、trainer_signal、race_shape
- 引擎回放 449 場 → fixed_rule 判決 389 場，baseline = labels_final（936f3d9b 現行）

## 結果（候選 − baseline，pp，95% 配對 bootstrap）

| 版本 | 郁咗 | Gold | Good | capture@5 | recall@5 | 頭三平均名次 | 頭二選有中 | 判決 |
|---|---|---|---|---|---|---|---|---|
| K100 | 387 | −2.06 [−5.32,+1.04] | −4.11 [−7.36,−0.77] | +0.69 | +1.40 [+0.30,+2.50] | −0.09 | +2.83 [+0.00,+5.76] | REJECT |
| K50 | 378 | −2.57 [−5.17,+0.00] | −0.51 | +0.69 | +1.05 [+0.06,+2.04] | −0.07 [−0.14,−0.00] | +1.54 | REJECT |
| **S100** | 389 | −3.08 [−5.79,−0.51] | −4.63 [−8.33,−1.26] | +0.26 | +0.89 | −0.06 | +0.77 | REJECT |
| **S50** | 377 | −1.80 [−3.55,+0.00] | −0.77 | +0.34 | +0.58 | −0.09 [−0.15,−0.02] | +0.51 | REJECT |

## 點樣失敗

同 EXP-25 一樣嘅形狀：廣義排序（recall@5、頭三平均名次）有改善，但全中類（Gold／Good）跌。
保留段速令改善幅度細咗（S 版 recall CI 跨零），損失冇細咗多少。結論：**由賽果庫搬權重呢條路完咗**，
問題唔係邊個維度被錯誤遷移，而係賽果庫嘅份量本身唔適用於引擎嘅分數尺度（引擎維度同賽果庫特徵唔係一對一）。
四個版本喺同一 389 場試，就算有一個過都要 forward；冇一個過。
