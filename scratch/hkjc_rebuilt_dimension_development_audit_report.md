# HKJC Dimension重建 Step 4 — Development單項診斷與Ablation

## 方法鎖定

- 只解封archive development：9個賽日／88場／1093匹；其他三段賽果完全未載入。
- Step 3公式原封不動；無搜尋權重、無逐場規則、無micro tie-break或第二／第三選盲換。
- 七維等權分只係ablation參考，唔係候選或正式排名公式。
- 每個dimension嘅前進閘口在計算前固定：核心閘、可靠樣本條件閘，以及等權ablation明顯有害否決。

## 七維等權診斷參考

- 0／1／2 hit：26/49/13；Top2總hits 75；頭馬Top2 30。
- 實際前三AUC 0.668；頭馬AUC 0.628。

## 單項結果

| Dimension | Top3 AUC | 頭馬AUC | 可靠樣本AUC／pairs | Δ前三分 | 正向賽日 | 單項0/1/2 | 總hits | 頭馬Top2 | 決定 |
|---|---:|---:|---:|---:|---:|---|---:|---:|---|
| speed_engine | 0.565 | 0.565 | 0.599/1541 | +0.47 | 5/9 | 39/44/5 | 54 | 21 | ADVANCE_CORE |
| stability | 0.689 | 0.649 | 0.704/1918 | +2.78 | 9/9 | 31/43/14 | 71 | 25 | ADVANCE_CORE |
| distance_context | 0.494 | 0.452 | 0.500/0 | -0.09 | 2/9 | 40/41/7 | 55 | 13 | HOLD_OR_REJECT |
| class_weight | 0.525 | 0.510 | 0.524/2435 | +0.42 | 5/9 | 44/37/7 | 51 | 14 | HOLD_OR_REJECT |
| trainer_signal | 0.609 | 0.648 | 0.618/1518 | +1.73 | 8/9 | 33/46/9 | 64 | 27 | ADVANCE_CORE |
| readiness_risk | 0.500 | 0.497 | 0.500/2310 | +0.06 | 6/9 | 46/41/1 | 43 | 11 | HOLD_OR_REJECT |
| form_line | 0.528 | 0.457 | 0.498/671 | +0.24 | 4/9 | 42/42/4 | 50 | 15 | HOLD_OR_REJECT |

## 等權Ablation

正數代表移除該dimension後上升；如果移除後總hits上升、0-hit下降兼頭馬不跌，視為該dimension在等權環境明顯有害。

| 移除 | Δ總hits | Δ0-hit | Δ頭馬Top2 | ΔTop3 AUC | Δ頭馬AUC |
|---|---:|---:|---:|---:|---:|
| speed_engine | -1 | +3 | -3 | -0.000 | +0.000 |
| stability | -15 | +13 | -7 | -0.064 | -0.058 |
| distance_context | -1 | +1 | -4 | +0.001 | +0.001 |
| class_weight | +9 | -6 | -2 | +0.017 | +0.003 |
| trainer_signal | -7 | +3 | -14 | -0.024 | -0.054 |
| readiness_risk | +0 | +1 | -1 | -0.005 | -0.006 |
| form_line | -1 | +0 | -3 | +0.006 | +0.032 |

## Step 4結論

- 核心前進：speed_engine, stability, trainer_signal。
- 條件前進：無。
- 暫緩／否決：distance_context, class_weight, readiness_risk, form_line。
- Validation errors：0。
- 呢個決定只用development；下一步只會由前進dimension組成最多三個預先凍結完整矩陣，仍然唔會打開其他賽果。
