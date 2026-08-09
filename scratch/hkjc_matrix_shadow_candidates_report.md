# HKJC Wong Choi Step 6 — Rating Matrix固定候選Shadow

## 方法鎖定

- 四個候選在睇結果前固定，無grid search、無逐場調權重。
- 候選全部用speed-only取代含going嘅stored sectional；初出馬沿用現有debut公式。
- race-shape權重凍結，不按其含draw訊號作調權；本步只重配健康／賽績線至穩定性、級數或路程context。
- 無rank_score、micro tie-break、第二／第三選盲換、賠率、市場或pace。
- Archive按賽日先後70／30切development與時間留後；近期獨立集及2026-07-15另列。

## 候選定義

| 候選 | 說明 | 權重總和 |
|---|---|---:|
| baseline_pure_matrix | 只作比較；stored sectional含going。 | 0.9999 |
| speed_only_substitution | 只將sectional輸入改為speed-only，其餘權重不變。 | 0.9999 |
| speed_stability_shift | 由弱健康及弱賽績線合共轉5.28%去穩定性；race-shape權重凍結。 | 0.9999 |
| speed_balanced_context | 由健康／賽績線轉5.27%，分配去穩定性及級數；race-shape權重凍結。 | 0.9999 |
| speed_distance_5pct | 由健康／賽績線轉5%去路程context；race-shape權重凍結。 | 0.9999 |

## archive_development

| 候選 | 場數 | 0／1／2 hit | Top2總hits | Δhits | 頭馬Top2 | Δ頭馬 | AUC | 名單變動 | 救0-hit | 1→2 | 1→0 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_pure_matrix | 88 | 17/45/26 | 97 | +0 | 41 | +0 | 0.717 | 0 | 0 | 0 | 0 |
| speed_only_substitution | 88 | 17/46/25 | 96 | -1 | 41 | +0 | 0.720 | 2 | 0 | 0 | 0 |
| speed_stability_shift | 88 | 16/46/26 | 98 | +1 | 40 | -1 | 0.724 | 17 | 3 | 1 | 2 |
| speed_balanced_context | 88 | 17/45/26 | 97 | +0 | 40 | -1 | 0.722 | 9 | 1 | 1 | 1 |
| speed_distance_5pct | 88 | 20/42/26 | 94 | -3 | 42 | +1 | 0.719 | 8 | 0 | 1 | 3 |

## archive_temporal_holdout

| 候選 | 場數 | 0／1／2 hit | Top2總hits | Δhits | 頭馬Top2 | Δ頭馬 | AUC | 名單變動 | 救0-hit | 1→2 | 1→0 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_pure_matrix | 39 | 12/20/7 | 34 | +0 | 15 | +0 | 0.685 | 0 | 0 | 0 | 0 |
| speed_only_substitution | 39 | 13/18/8 | 34 | +0 | 14 | -1 | 0.684 | 7 | 0 | 1 | 1 |
| speed_stability_shift | 39 | 13/17/9 | 35 | +1 | 15 | +0 | 0.697 | 9 | 1 | 2 | 2 |
| speed_balanced_context | 39 | 13/18/8 | 34 | +0 | 15 | +0 | 0.696 | 7 | 1 | 1 | 2 |
| speed_distance_5pct | 39 | 13/19/7 | 33 | -1 | 15 | +0 | 0.679 | 6 | 1 | 0 | 2 |

## independent_recent

| 候選 | 場數 | 0／1／2 hit | Top2總hits | Δhits | 頭馬Top2 | Δ頭馬 | AUC | 名單變動 | 救0-hit | 1→2 | 1→0 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_pure_matrix | 109 | 39/54/16 | 86 | +0 | 37 | +0 | 0.674 | 0 | 0 | 0 | 0 |
| speed_only_substitution | 109 | 35/54/20 | 94 | +8 | 42 | +5 | 0.678 | 23 | 5 | 6 | 1 |
| speed_stability_shift | 109 | 32/57/20 | 97 | +11 | 40 | +3 | 0.685 | 22 | 7 | 5 | 0 |
| speed_balanced_context | 109 | 33/57/19 | 95 | +9 | 40 | +3 | 0.684 | 20 | 6 | 4 | 0 |
| speed_distance_5pct | 109 | 33/56/20 | 96 | +10 | 41 | +4 | 0.682 | 26 | 7 | 6 | 1 |

## external_2026_07_15

| 候選 | 場數 | 0／1／2 hit | Top2總hits | Δhits | 頭馬Top2 | Δ頭馬 | AUC | 名單變動 | 救0-hit | 1→2 | 1→0 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_pure_matrix | 9 | 4/2/3 | 8 | +0 | 2 | +0 | 0.608 | 0 | 0 | 0 | 0 |
| speed_only_substitution | 9 | 5/1/3 | 7 | -1 | 1 | -1 | 0.608 | 2 | 0 | 0 | 1 |
| speed_stability_shift | 9 | 5/1/3 | 7 | -1 | 1 | -1 | 0.608 | 4 | 0 | 1 | 1 |
| speed_balanced_context | 9 | 5/1/3 | 7 | -1 | 1 | -1 | 0.600 | 2 | 0 | 0 | 1 |
| speed_distance_5pct | 9 | 4/2/3 | 8 | +0 | 2 | +0 | 0.621 | 3 | 0 | 0 | 0 |

## all

| 候選 | 場數 | 0／1／2 hit | Top2總hits | Δhits | 頭馬Top2 | Δ頭馬 | AUC | 名單變動 | 救0-hit | 1→2 | 1→0 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_pure_matrix | 245 | 72/121/52 | 225 | +0 | 95 | +0 | 0.689 | 0 | 0 | 0 | 0 |
| speed_only_substitution | 245 | 70/119/56 | 231 | +6 | 98 | +3 | 0.691 | 34 | 5 | 7 | 3 |
| speed_stability_shift | 245 | 66/121/58 | 237 | +12 | 96 | +1 | 0.698 | 52 | 11 | 9 | 5 |
| speed_balanced_context | 245 | 68/121/56 | 233 | +8 | 96 | +1 | 0.696 | 38 | 8 | 6 | 4 |
| speed_distance_5pct | 245 | 70/119/56 | 231 | +6 | 100 | +5 | 0.693 | 43 | 8 | 7 | 6 |

## Step 7入閘條件

候選要在development、archive時間留後及近期獨立集同時滿足：Top2總hits不跌、頭馬Top2不跌、0-hit不增；三段之中至少一項有改善。07-15只有9場，只作外部方向檢查，不作硬閘。

| 候選 | Development Δhits/Δ頭馬/Δ0-hit | Holdout | 近期獨立 | 入Step 7 |
|---|---|---|---|---|
| speed_only_substitution | -1/+0/+0 | +0/-1/+1 | +8/+5/-4 | 否 |
| speed_stability_shift | +1/-1/-1 | +1/+0/+1 | +11/+3/-7 | 否 |
| speed_balanced_context | +0/-1/+0 | +0/+0/+1 | +9/+3/-6 | 否 |
| speed_distance_5pct | -3/+1/+3 | -1/+0/+1 | +10/+4/-6 | 否 |

## Step 6結論

- 可進入Step 7候選：無
- 全體Top2名單變動明細：167行（不同候選可重複同一場）。
- 資料錯誤：0。
- 本步只係shadow診斷，無修改正式HKJC scoring engine。
