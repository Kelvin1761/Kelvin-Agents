# EXP-20260825-01 差試閘 × PacePerf／wet 收縮

- **日期**：2026-08-25
- **平台**：AU
- **假設**：一匹已出賽馬近三課有名次試閘全部未入前三時，正面 PacePerf 或 wet
  overlay 應降低可靠度；呢個 interaction 可修正 Gunroom 型高估而改善整體排序。
- **搜索過嘅舊記錄**：EXP-20260823-02（單獨削 PacePerf／wet 全部不成立）、
  EXP-20260824-02（prep evidence × volatility 無足夠樣本）、EXP-20260824-05
  （新 trial placing transport 令呢個 interaction 首次可觀察）。
- **改到嘅組件**：只改 research harness
  `scratch/au_trial_transport_eval_20260824.py`；production model **冇改**。

## 預先鎖定配置

baseline 先恢復 Sportsbet point-in-time trial placings，只改 captured runtime 中原本
`trial_score=fallback`、但 target date 前其實已有試閘名次嘅 runner。候選只對恢復後
等同 fresh-engine `trial_no_recent_top3`（established horse trial score 56）嘅 runner：

1. **PF-half**：只將正面 `pace_figure_score - 60` 收縮一半；
2. **wet-half**：只將正面 wet overlay 收縮一半；
3. **both-half**：兩者同時收縮。

門檻同 0.5 幅度喺開結果前固定，冇搜尋 cap、threshold 或 alpha。三個候選先只睇 dev
頭 5 場內 AUC；只有 dev 正數嘅最佳候選先准開一次 terminal holdout。

## 數據

- runtime dataset：`/private/tmp/au_reopt_20260821/work/au_ml_runtime_dataset.json`
- 語料：1,411 場／14,109 匹。
- dev：899 場，2025-08-02 至 2026-08-07（70 個完整賽日）。
- terminal（鎖住未開）：512 場，2026-08-08 至 2026-08-20。
- Sportsbet point-in-time extraction：174 meetings／1,450 pages；trial date 必須早過
  target date。
- 10,352 匹 trial identity 對齊；2,425 匹原本 fallback 有可恢復證據；37 匹 trial
  score 真正改變、12 場 baseline 排序改變。
- SP／實際結果只作評估 label，冇進 scorer。

## Dev 結果

| 候選 | dev 頭5 AUC 差 | 結果 |
|---|---:|---|
| PF-half | **0.000000** | 分唔開 |
| wet-half | **0.000000** | 分唔開 |
| both-half | **0.000000** | 分唔開 |

三個候選連 dev 頭 5 comparable pairs 都冇改變，所以冇候選合資格開 terminal；
holdout 保持未看。呢個唔係「holdout 跨零」，而係更早一步已經冇足夠 footprint。

## Randwick R1 個案效果

fresh Sportsbet raw replay baseline：Isawyou 70.39／Gunroom 69.77／Clear Proof 69.35。
Gunroom 已有 `trial_no_recent_top3`、trial 56，但 PacePerf 79.4 ＋ wet +2.18 仍令佢第二。

| 配置 | R1 Top 3 | Gunroom 分 |
|---|---|---:|
| baseline | Isawyou／Gunroom／Clear Proof | 69.77 |
| PF-half | Isawyou／Clear Proof／Gunroom | 68.66 |
| wet-half | Isawyou／Clear Proof／Gunroom | 68.68 |
| both-half | Isawyou／Clear Proof／Gunroom | 67.57 |

三個候選都啱啱好修到 R1，但歷史 dev 完全冇辨識力；因此呢個係典型「單場答案靚、
泛化證據為零」，唔可以落 production。

## 檢查

- **leakage-audit**：PASS — trial date `< target date`；SP／名次只係 label。
- **feature ablation**：A、B、A+B 已分開量；三者 dev 都 0。
- **golden_scoring／data_contract**：不適用，production code 冇改。
- **退步**：未開 holdout，不能聲稱冇退步。

## 結論

Clear Proof 排第三確實指出 R1 對 Gunroom 嘅 PacePerf＋wet 組合仍然過信；但新嘅
poor-trial reliability gate 喺現有歷史樣本冇足夠 footprint，dev 精確打和。保留
trial 56同 visible risk 呢個 correctness fix；interaction ranking change 拒絕。

**決定：REJECT**

**commit：未 commit（production model 無改）**

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  scratch/au_trial_transport_eval_20260824.py \
  --dataset /private/tmp/au_reopt_20260821/work/au_ml_runtime_dataset.json \
  --output /private/tmp/au_trial_poor_interaction_20260825.json
```
