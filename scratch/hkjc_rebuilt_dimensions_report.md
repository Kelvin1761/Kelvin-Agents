# HKJC Dimension重建 Step 3 — Outcome-blind公式契約

## 硬約束

- 只讀Step 2 primitive白名單；程式入口即時丟棄賽果label、原模型rank及原分數。
- 無going、draw、barrier、track bias、pace、run style、odds、市場、ROI、edge。
- 缺資料一律60；可靠度只控制向60收縮，唔會本身加能力分。
- 本步無ability權重、無Top 2排名、無AUC或命中率，避免睇結果定公式。

## 七個重建dimension

| Dimension | 核心輸入 | 收縮／主要規則 |
|---|---|---|
| speed_engine | raw_l400 | 70% existing L400 domain bands + 30% within-race lower-is-better percentile; then reliability 0.65；missing L400 remains neutral 60, not penalized |
| stability | last6_runs, last6_mean_finish, last6_best_finish, last6_worst_finish, last6_top3_count | 50% mean-finish relative + 35% top3-rate relative + 15% finish-range relative; reliability=min(runs/4,1)；zero prior runs remains neutral 60 |
| distance_context | same_distance_starts, same_distance_wins, same_distance_seconds, same_distance_thirds, same_venue_distance_starts, same_venue_distance_wins, same_venue_distance_seconds, same_venue_distance_thirds, prior_class_distance_place_rate | same-distance place rate blended 65/35 with same-venue-distance when present; 4-run Bayesian shrink to class-distance prior, then within-race relative；untried distance remains neutral instead of negative |
| class_weight | card_rating, weight_carried, starts | 75% higher-rating within-race relative + 25% lower-weight relative; reliability from rating/weight availability and min(starts/4,1)；missing rating/weight component is omitted and weights renormalized |
| trainer_signal | prior_combo_starts, prior_combo_place_rate, prior_jockey_cd_starts, prior_jockey_cd_place_rate, prior_trainer_cd_starts, prior_trainer_cd_place_rate, prior_class_distance_place_rate | combo/jockey-CD/trainer-CD weights 35/35/30; each place-rate delta vs class-distance baseline shrunk n/(n+20); 10-point place-rate delta maps to 8 score points；unmapped or zero-sample prior remains neutral |
| readiness_risk | days_since_last, raw_weight_trend_span | structured rest/weight-span domain bands around neutral 60; reliability is available inputs / 2；unknown readiness remains neutral |
| form_line | raw_formline_higher_win_count, raw_formline_same_win_count, raw_formline_lower_win_count | opponent strength=(3*higher + same - lower)/total; raw=60+6*strength; reliability=total/(total+3)；no opponent follow-up evidence remains neutral |

## 分數分布（不含賽果）

| Dimension | Mean | SD | 中性60 | 平均可靠度 | 低可靠度<0.25 | Min–Max |
|---|---:|---:|---:|---:|---:|---:|
| speed_engine | 60.58 | 2.55 | 15.6% | 0.55 | 15.2% | 55.5–65.9 |
| stability | 60.17 | 4.47 | 7.1% | 0.86 | 6.9% | 50.8–70.0 |
| distance_context | 59.97 | 0.87 | 81.0% | 0.05 | 94.3% | 54.0–63.3 |
| class_weight | 60.00 | 3.24 | 3.4% | 0.97 | 0.0% | 52.5–69.6 |
| trainer_signal | 60.72 | 4.24 | 1.7% | 0.62 | 3.7% | 47.7–79.7 |
| readiness_risk | 60.81 | 1.96 | 14.1% | 0.71 | 2.6% | 53.0–65.0 |
| form_line | 64.45 | 3.74 | 24.3% | 0.38 | 22.4% | 57.0–73.8 |

## 跨split分數／可靠度（不含賽果）

每格係 `平均分／平均可靠度`；用嚟確認coverage漂移主要反映喺可靠度，而唔係製造跨版本分數偏移。

| Dimension | Development | Temporal | 近期獨立 | 07-15 |
|---|---:|---:|---:|---:|
| speed_engine | 60.76/0.42 | 60.37/0.63 | 60.52/0.62 | 60.56/0.64 |
| stability | 60.18/0.80 | 60.17/0.89 | 60.17/0.89 | 60.12/0.95 |
| distance_context | 59.97/0.05 | 59.98/0.05 | 59.96/0.05 | 59.98/0.05 |
| class_weight | 60.00/0.94 | 60.00/0.99 | 59.99/0.98 | 59.99/1.00 |
| trainer_signal | 60.66/0.60 | 61.25/0.62 | 60.61/0.63 | 60.35/0.65 |
| readiness_risk | 60.57/0.54 | 60.86/0.82 | 60.97/0.80 | 61.10/0.81 |
| form_line | 64.29/0.37 | 64.21/0.33 | 64.59/0.40 | 65.46/0.49 |

## Dimension重疊警報

| Dimension A | Dimension B | Correlation |
|---|---|---:|
| stability | trainer_signal | +0.208 |
| speed_engine | stability | +0.182 |
| stability | class_weight | +0.156 |
| class_weight | trainer_signal | +0.150 |
| class_weight | form_line | +0.144 |
| speed_engine | trainer_signal | +0.108 |
| stability | form_line | -0.103 |
| distance_context | form_line | +0.068 |
| speed_engine | class_weight | +0.066 |
| stability | distance_context | -0.063 |

## Step 3狀態

- 產生3054匹outcome-blind dimension rows；validation errors：0。
- 初出／資料薄弱馬保留neutral upside；`supported_upside_count`只計可靠度≥0.50而分數≥64嘅支持訊號。
- 現有完成時間調整、操練量及敘事flag只記coverage，今版不進能力公式。
- 尚未用賽果做單項診斷、ablation、權重、排名或第三選升格測試；正式Auto engine不變。
