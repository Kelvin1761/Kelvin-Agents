# HKJC Dimension重建 Step 5d — 不確定性槽固定候選

## 方法鎖定

- 三案只做readiness health-slot及trainer證據可靠度收縮嘅固定ablation；無搜尋權重、threshold或收縮倍率。
- Trainer收縮公式固定為：60 + reliability ×（現行trainer分 − 60）；可靠度0回中性60，可靠度1保留原分。
- 沿用現行官方outer weights及初出馬weights；全245場先完整重排，再載入88場development結果。
- 無micro tie-break、無第二／第三選盲換；正式Auto保持不變。

## 固定候選

| 候選 | Readiness槽 | Trainer收縮 | 假設 |
|---|---:|---:|---|
| readiness_slot_only | 是 | 否 | 以重建readiness-risk取代現行health槽，其餘dimension及官方outer weights不變。 |
| trainer_reliability_shrink_only | 否 | 是 | 保留現行trainer分，但按既有pre-race證據可靠度向中性60收縮。 |
| readiness_plus_trainer_shrink | 是 | 是 | 合併readiness health-slot重建與trainer可靠度收縮，無額外互動項。 |

## Development雙基準

- 原模型Top2：0／1／2 hit 21/40/27；總hits 94；頭馬Top2 39。
- 原matrix純加權骨架：0／1／2 hit 17/45/26；總hits 97；頭馬Top2 41。

## 候選結果

| 候選 | 0/1/2 hit | 對原模型Δhits/Δ頭馬/Δ0 | Top2變動 | helped/harmed | 第三選有效/有害/淨值 | 邊界同分 | Step 6 |
|---|---|---|---:|---:|---:|---:|---|
| readiness_slot_only | 18/43/27 | +3/+2/-3 | 14 | 6/3 | 7/3/+4 | 0 | 是 |
| trainer_reliability_shrink_only | 21/43/24 | -3/-2/+0 | 29 | 7/10 | 6/7/-1 | 0 | 否 |
| readiness_plus_trainer_shrink | 21/42/25 | -2/-2/+0 | 31 | 8/10 | 6/7/-1 | 0 | 否 |

## Development分散度與初出馬影響

| 候選 | hits賽日 +/=/- | 頭馬賽日 +/=/- | 0-hit賽日 改善/不變/轉差 | 變動場次含初出 | 初出相關 helped/harmed |
|---|---:|---:|---:|---:|---:|
| readiness_slot_only | 4/4/1 | 2/6/1 | 3/6/0 | 1/14 | 0/0 |
| trainer_reliability_shrink_only | 3/4/2 | 2/4/3 | 3/4/2 | 0/29 | 0/0 |
| readiness_plus_trainer_shrink | 3/4/2 | 2/4/3 | 3/4/2 | 2/31 | 1/0 |

## Step 5d結論

- 可解封Step 6嘅候選：readiness_slot_only。
- Matrix load errors：0；validation errors：0。
- 未通過候選唔會用holdout結果再調公式；正式Auto保持不變。
