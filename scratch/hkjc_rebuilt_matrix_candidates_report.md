# HKJC Dimension重建 Step 5 — 三個凍結完整矩陣候選

## 候選鎖定

- 三候選在量development表現前固定；無grid search、無逐場改權重。
- 非初出馬只用Step 4通過嘅speed-engine、stability、trainer；其餘四維權重為0。
- 初出馬缺正式賽證據，三候選統一用50%中性60＋50%trainer；不使用draw或被暫緩dimension。
- 每場完整重排；無micro tie-break或第二／第三選盲換。完全同分只以馬號固定排序，並另計發生率。
- 只載入development結果；其他三段候選分及排名已outcome-free凍結。

| 候選 | Speed | Stability | Trainer | 假設 |
|---|---:|---:|---:|---|
| balanced_core | 0.33 | 0.33 | 0.33 | 三個通過dimension等權，避免單一訊號主導。 |
| stability_led | 0.20 | 0.50 | 0.30 | 按development最強且9/9正向嘅stability主導，trainer次之，speed作支持。 |
| winner_guard | 0.15 | 0.40 | 0.45 | 提高development頭馬AUC強嘅trainer比重，stability保留主體，speed只作確認。 |

## Development基準

- 原模型Top2：0／1／2 hit = 21/40/27；總hits 94；頭馬Top2 39。

## 候選結果與前進閘

| 候選 | 0/1/2 hit | Δhits | Δ頭馬 | 變動場 | helped/harmed | 救0-hit | 1→2/1→0 | 第三選升格有效/有害/淨值 | 邊界同分 | Step 6 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| balanced_core | 23/50/15 | -14 | -11 | 76 | 21/29 | 13 | 8/9 | 7/9/-2 | 0 | 否 |
| stability_led | 27/51/10 | -23 | -12 | 79 | 12/29 | 8 | 4/8 | 5/10/-5 | 0 | 否 |
| winner_guard | 20/55/13 | -13 | -10 | 77 | 18/27 | 13 | 5/8 | 6/10/-4 | 0 | 否 |

## Step 5結論

- 可解封Step 6驗證嘅凍結候選：無。
- Validation errors：0。
- 候選排名CSV不含賽果或原模型rank；正式Auto engine保持不變。
