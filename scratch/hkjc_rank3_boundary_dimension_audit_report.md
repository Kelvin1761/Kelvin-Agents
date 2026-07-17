# HKJC Dimension重建 Step 5c — 第2／第3選邊界失誤分型

## 方法鎖定

- 固定比較原模型第2選與第3選；無搜尋權重、threshold或交換規則。
- 第3選實際入前三而第2選甩位，定義為可救邊界；相反情況定義為必須保護。
- 現行dimension及重建dimension用完全相同配對；正分差代表方向正確。
- 本步只做development診斷，未建立候選，正式Auto保持不變。

## 0／1-hit上限

- 原模型88場：0／1／2 hit = 21/40/27；0／1-hit合共61場。
- 0-hit場有10場可由第三選正確升格變成1-hit。
- 1-hit場有7場可由第三選正確升格變成2-hit。
- 完美邊界判斷嘅理論上限：0／1／2 hit = 11/43/34；總hits 111。

## Dimension方向診斷

| 類別 | Dimension | 邊界AUC | 平衡方向準確 | 可救方向（含同分） | 保護方向（含同分） | 平均正向分差 | 正向賽日 |
|---|---|---:|---:|---:|---:|---:|---:|
| official_total | pure_matrix_total | 0.590 | 58.6% | 23.5% | 93.8% | +0.411 | 7/9 |
| official_dimension | sectional | 0.493 | 49.5% | 41.2% | 57.8% | +0.388 | 2/9 |
| official_dimension | trainer_signal | 0.336 | 30.5% | 23.5% | 37.5% | -2.162 | 3/9 |
| official_dimension | stability | 0.439 | 45.0% | 35.3% | 54.7% | +0.021 | 5/9 |
| official_dimension | race_shape | 0.641 | 56.1% | 55.9% | 56.2% | +2.048 | 7/9 |
| official_dimension | class_advantage | 0.630 | 57.1% | 47.1% | 67.2% | +1.622 | 6/9 |
| official_dimension | horse_health | 0.590 | 50.5% | 35.3% | 65.6% | +0.631 | 6/9 |
| official_dimension | form_line | 0.620 | 61.9% | 70.6% | 53.1% | +0.494 | 6/9 |
| rebuilt_dimension | speed_engine | 0.477 | 51.0% | 44.1% | 57.8% | -0.070 | 4/9 |
| rebuilt_dimension | stability | 0.454 | 43.4% | 35.3% | 51.6% | +0.296 | 4/9 |
| rebuilt_dimension | distance_context | 0.399 | 44.4% | 52.9% | 35.9% | -0.478 | 1/9 |
| rebuilt_dimension | class_weight | 0.571 | 54.0% | 70.6% | 37.5% | +0.103 | 5/9 |
| rebuilt_dimension | trainer_signal | 0.338 | 35.0% | 29.4% | 40.6% | -1.729 | 2/9 |
| rebuilt_dimension | readiness_risk | 0.615 | 58.2% | 61.8% | 54.7% | +0.204 | 5/9 |
| rebuilt_dimension | form_line | 0.528 | 55.1% | 61.8% | 48.4% | -0.164 | 4/9 |

## 重建Dimension可靠度檢查

- 固定使用Step 4既有門檻：第2及第3選兩匹馬該dimension可靠度均須≥0.50；無重新選threshold。

| Dimension | 可靠配對（可救/保護） | 可靠配對AUC | 可靠配對平衡方向 |
|---|---:|---:|---:|
| speed_engine | 29 (8/21) | 0.393 | 48.5% |
| stability | 37 (12/25) | 0.443 | 40.5% |
| distance_context | 0 (0/0) | N/A | N/A |
| class_weight | 47 (16/31) | 0.594 | 56.0% |
| trainer_signal | 33 (10/23) | 0.426 | 38.9% |
| readiness_risk | 46 (16/30) | 0.619 | 58.8% |
| form_line | 17 (6/11) | 0.447 | 51.9% |

## 固定讀法

- 重建dimension平衡方向最好：readiness_risk（58.2%）；其次form_line（55.1%）。
- 現行加權dominant blocker：{"trainer_signal": 6, "stability": 5, "race_shape": 5, "form_line": 1}。
- 重建raw dominant blocker：{"trainer_signal": 7, "stability": 6, "form_line": 2, "speed_engine": 1, "class_weight": 1}。
- Validation errors：0。

## Step 5c結論

- 現行純矩陣偏向保住第2選：可救方向只有23.5%，保護方向93.8%。
- 現行form-line應保留：平衡方向61.9%、AUC 0.620，優於重建form-line。
- readiness-risk係唯一同時有合理可救及保護方向、而可靠樣本亦無倒退嘅重建項：全配對平衡方向58.2%／AUC 0.615；可靠配對58.8%／AUC 0.619。
- class-weight雖然可救方向達70.6%，但保護方向只有37.5%，不適合單獨推高。
- speed-engine、distance-context及兩個trainer版本均未顯示可兼顧可救與保護嘅邊界能力；唔據此建立候選。
- 下一步只值得凍結細幅結構候選：以readiness-risk重建現行horse-health細權重槽；trainer只可測試證據可靠度收縮，不能直接換入重建trainer。
