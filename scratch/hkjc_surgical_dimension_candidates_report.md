# HKJC Dimension重建 Step 5b — 外科式Dimension替換

## 方法鎖定

- 沿用現行官方outer weights；候選只逐步替換dimension，無搜尋權重。
- 三候選全部將sectional換成純L400 speed，race-shape固定中性60；第二案再換trainer，第三案再換stability。
- 其餘class、health、form-line沿用現行matrix分；初出馬沿用現行debut weights，但race-shape同樣固定60。
- 每場完整重排；無micro tie-break或第二／第三選盲換。
- 全245場分數及排名先凍結；只載入development reference，未讀其他結果檔。

## 固定候選

| 候選 | 替換 | 假設 |
|---|---|---|
| surgical_speed_shape_neutral | sectional→dim_speed_engine, race_shape→60.0 | 只移除going／draw污染：sectional換純L400 speed，race-shape回中性60。 |
| surgical_plus_trainer | sectional→dim_speed_engine, race_shape→60.0, trainer_signal→dim_trainer_signal | 在污染清理上，再換入Step 4通過嘅sample-shrunk trainer。 |
| surgical_plus_trainer_stability | sectional→dim_speed_engine, race_shape→60.0, trainer_signal→dim_trainer_signal, stability→dim_stability | 再換入9/9 development賽日正向嘅拆重stability。 |

## Development雙基準

- 原模型Top2：0／1／2 hit 21/40/27；總hits 94；頭馬Top2 39。
- 原matrix純加權骨架：0／1／2 hit 17/45/26；總hits 97；頭馬Top2 41。

## 候選結果

| 候選 | 0/1/2 hit | 對原模型Δhits/Δ頭馬/Δ0 | 對純骨架Δhits/Δ頭馬/Δ0 | helped/harmed | 第三選有效/有害/淨值 | 邊界同分 | Step 6 |
|---|---|---|---|---:|---:|---:|---|
| surgical_speed_shape_neutral | 15/62/11 | -10/-7/-6 | -13/-9/-2 | 16/23 | 5/11/-6 | 0 | 否 |
| surgical_plus_trainer | 22/52/14 | -14/-9/+1 | -17/-11/+5 | 15/26 | 5/7/-2 | 0 | 否 |
| surgical_plus_trainer_stability | 26/50/12 | -20/-11/+5 | -23/-13/+9 | 15/33 | 2/7/-5 | 0 | 否 |

## Step 5b結論

- 可解封Step 6嘅候選：無。
- Matrix load errors：0；validation errors：0。
- 正式Auto engine保持不變。
