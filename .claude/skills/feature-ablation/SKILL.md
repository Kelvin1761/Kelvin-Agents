---
name: feature-ablation
description: 'Isolate the marginal contribution of each change when more than one feature, leaf, signal, weight, gain, rule, transformation or model component moves at once in the Wong Choi engines. Use this skill whenever a candidate bundles multiple edits, when a combined experiment improves and you need to know which part caused it, or when deciding whether to remove existing complexity.'
---

# feature-ablation

## 點解要有

「一次改五樣，總數升咗」講唔出邊樣有用。呢個 repo 已經被咬過兩次：

- **`au_matrix_refit`：收益係五個維度一齊郁出嚟嘅。** 所以逐對權重試（coordinate
  descent）會讀到「已經最優」，其實佢係讀到「平」。單獨郁一對過唔到閘 ≠ 冇用。
- **micro-family 八族剷兩族贏，「全部一齊剷」實測輸。** 所以「簡化」都要逐族量。

同時：**閘門會拒絕 40/40 個中性改動**。所以細幅度候選唔可以用場數指標判死，
要用 ability AUC + 配對 bootstrap（見 `model-regression-gate`）。

## 流程

1. **列清楚今次動咗幾件獨立嘢。** 一個「候選」如果同時改咗 leaf 公式、加咗
   一個 feature、又動咗權重 —— 呢個係三件。分開命名 A / B / C。

2. **量每個 leaf 自己嘅場內判別力，先。**
   ```bash
   python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_leaf_power.py
   ```
   權重只係放大器。一個場內 AUC ≈ 0.50 嘅 leaf，加幾多權重都係加噪音。
   次序係 **量 → 再決定改唔改**，唔係倒轉。（已經中過兩次：PF 寫落死 key、
   段速分嘅 PI 排序倒轉。）
   ⚠️ 一定**場內**比。全池 AUC 會把「呢場係高班賽」當成「呢匹馬好」。
   ⚠️ 中性 60 嗰批預設剔走 —— 佢哋唔係「分數低」，係「冇證據」。

3. **跑階梯。** 計算上做得到就行齊：
   ```
   baseline
   baseline + A
   baseline + B
   baseline + C
   baseline + A + C      ← 只跑有理由懷疑有互動嘅組合
   ```
   工具：
   - 加特徵入排名分 → `au_feature_ab.py`（每個 A/B/C 各跑一次）
   - 剷 / 停用現有 micro family → `au_runtime_micro_ablation.py`
   - 換一個 leaf → `au_eval.py --swap-leaf <leaf>=60`（換成中性 = 等效剷走）
   - 權重 → `au_matrix_refit.py compare --weights w.json`

4. **報邊際貢獻。** 每一步報**相對前一步**嘅差，唔係相對 baseline 嘅累計。

5. **揀最簡單嗰個。** 一個 feature 唔可以因為「合併實驗升咗」就留。如果
   `baseline + A` 同 `baseline + A + B` 喺 holdout 上分唔開，**B 唔留**。

## 唔准做

- **唔准跑無上限嘅組合搜索。** 2^n 個組合喺 ~600 場 holdout 上一定搵到「贏」嘅
  組合 —— 嗰個係 overfit，唔係發現。上限：預先寫定要試邊幾個組合，理由要寫落，
  之後唔准加。
- **唔准 argmax。** 取閘後候選嘅逐維度中位數（共識）。
- **唔准用 holdout 揀組合。** dev + 5 個時間 fold 揀，holdout 只做最後一次確認。
- **唔准跳 walk-forward。**（`au-jockey-trainer-fully-checked`：六個方向全 REJECT，
  省咗 walk-forward 嗰幾次全部誤判。）

## 互動要主動睇

- **scale 同 weight 係鎖住一齊郁嘅**：排名食 weight × gain，所以 gain、
  `MATRIX_WEIGHTS`、濕地 overlay 要一齊改。曾經有 3 個維度（共 6 個）
  永遠顯示唔到 ✅ 就係因為只改咗一邊。
- **重疊訊號**：一個同 `form_score` 高度重疊嘅特徵，AUC 靚但加落去只係放大同一個
  訊號。所以量最終**排名指標**，唔係量 AUC。
- **orthogonality 值得留**：`pace_map` 權重逐對搜索話佢應該細，但佢同其他維度
  唔相關，所以照賺到自己嗰份。剷之前睇相關矩陣。

## 輸出

```
語料：<範圍> ｜ dev/holdout：<日期> ｜ 樣本：N 場

配置                        頭5位AUC(holdout)   邊際     Gold     Good位   判決
baseline                    0.6530              —        14.7%    xx.x%    —
baseline + A                0.6571              +0.0041  15.2%    xx.x%    留 A
baseline + A + B            0.6573              +0.0002  15.2%    xx.x%    剷 B（分唔開）
baseline + A + C            0.6598              +0.0027  15.9%    xx.x%    留 C
baseline + A + B + C        0.6599              +0.0001  15.9%    xx.x%    B 照剷

最簡單而穩健嘅配置：baseline + A + C
剷走：B（邊際 +0.0002，bootstrap 過 0）
互動：A×C 冇互動（相加 0.0068 ≈ 實測 0.0068）
```
