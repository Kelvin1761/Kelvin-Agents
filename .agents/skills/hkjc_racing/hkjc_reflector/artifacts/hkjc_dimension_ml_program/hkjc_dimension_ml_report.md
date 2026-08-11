# HKJC 個別評分維度 ML Research Report

產生日期：2026-08-11

## 結論先行

今次只研究 `trainer_signal`、`race_shape`、`stability`。Production 七維 Matrix、外層權重、排序及 renderer 均沒有改動。

現行權重重算後，walk-forward Matrix 基準為：0-hit 0.2547、Winner@3 0.5342、Top3 capture@5 0.6294、NDCG@5 0.5312。

Archive 嘅 `current_live_recomputed_ability` 原本沿用上一版外層權重；本輪已保留舊值作 audit，並由七維分數按 2026-08-01 production contract 重算基準。

## Development cap selection

| 維度 | 選定 cap | Development gate | External non-regression | 研究判斷 |
|---|---:|---|---|---|
| `trainer_signal` | 0.20 | FAIL | PASS | reject / diagnostic only |
| `race_shape` | 0.05 | FAIL | PASS | reject / diagnostic only |
| `stability` | 0.05 | PASS | FAIL | reject / diagnostic only |

Operational decision：`stability` 已接入 checksum-pinned opt-in shadow monitoring；呢個決定唔等於 production promotion，亦唔會改主排名或投注建議。

## Selected residual scorecard

| Period | 維度 | 0-hit Δ | 0/1-hit severity Δ | Winner@3 Δ | Capture@5 Δ | NDCG@5 Δ | Log loss Δ |
|---|---|---:|---:|---:|---:|---:|---:|
| walk_forward | `trainer_signal` | +0.0062 | +0.0062 | -0.0062 | -0.0021 | +0.0021 | -0.0004 |
| external_holdout | `trainer_signal` | +0.0000 | +0.0000 | +0.0000 | +0.0000 | -0.0133 | +0.0000 |
| walk_forward | `race_shape` | +0.0000 | +0.0000 | +0.0124 | -0.0021 | +0.0031 | +0.0000 |
| external_holdout | `race_shape` | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.0001 |
| walk_forward | `stability` | +0.0062 | -0.0311 | +0.0000 | -0.0041 | -0.0019 | -0.0005 |
| external_holdout | `stability` | +0.0000 | -0.1111 | +0.0000 | -0.0370 | -0.0413 | +0.0014 |

## 0/1-hit races

- `trainer_signal`：walk-forward 幫到 2 場，傷害 1 場；其餘不變。
- `race_shape`：walk-forward 幫到 0 場，傷害 0 場；其餘不變。
- `stability`：walk-forward 幫到 6 場，傷害 1 場；其餘不變。

### Stability Rank 3 → Top 2

- Development：7 匹實際三甲馬由 Rank 3 升 Rank 2，其中 4 匹係頭馬。
- External：1 匹；包括 2026-07-15 R3「浪漫老撾」由 Rank 3 升 Rank 2，取代最終第7嘅「大千氣象」。
- 呢啲係整個 residual ranking 自然產生嘅移動，唔係逐場 blind swap；完整清單見 `dimension_rank_movements.csv`。

## Residual signal diagnosis

- `trainer_signal`：`num__feat_jockey_score` (+0.0156), `num__rel_matrix_trainer_signal` (+0.0138), `num__matrix_trainer_signal` (+0.0116)。
- `race_shape`：`num__barrier` (-0.0032), `num__rel_matrix_race_shape` (+0.0023), `num__feat_draw_score` (+0.0007)。
- `stability`：`num__last6_mean_finish` (-0.0100), `num__rel_matrix_stability` (+0.0092), `num__feat_form_score` (+0.0091)。
以上係標準化後、控制 Matrix offset 嘅條件 residual coefficient，只供診斷，唔等於 production 權重。

## 方法與限制

- 250 場／3109 runners；development 24 meetings，external 1 meeting。
- Walk-forward 以首 8 meetings 起步，每次只訓練較早日期；imputation、scaling、one-hot、calibration 同 residual fit 全部 fold-local。
- Residual 係 Matrix log-odds offset 上嘅 L2=1 細幅修正；cap 只由 development 選，external 只驗證一次。
- 冇用 odds、市場排名、ROI、賽果 priors、事故資料、步速預測、跑法標籤、micro tie-break 或 blind swap。
- External 只有 9 場，證據只可視為 non-regression check，唔足以批准 production promotion。

詳細數字見 `dimension_walk_forward_results.csv`、`dimension_external_results.csv`、`dimension_weak_race_impact.csv` 同 `dimension_segment_analysis.csv`。
