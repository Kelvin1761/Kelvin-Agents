# AU Wong Choi ML Experiment Report

## AU WONG CHOI ML RESULT

Current Production Model: **Current AU Wong Choi Rating Matrix**

Best Independent Analysis Model: **xgboost**

Best Analysis Hybrid: **Matrix + xgboost @ 50% ML**

Historical Dataset: **805 races / 8249 runners**

Final Out-of-Sample Test: **211 races / 2157 runners**

> This final chronological block was untouched by this ML model-selection run, but the archive was previously used to optimise the Rating Matrix. It is not claimed as globally untouched.

## ANALYSIS PERFORMANCE

| Metric | Current Matrix | Logistic | LightGBM | XGBoost | Hybrid |
|---|---:|---:|---:|---:|---:|
| Win Brier | 0.083892 | 0.085254 | 0.085081 | 0.084657 | 0.084001 |
| Win Log Loss | 0.296480 | 0.307525 | 0.302526 | 0.300749 | 0.297277 |
| Top-1 | 22.75% | 27.96% | 18.01% | 21.33% | 24.64% |
| Top-2 | 44.08% | 43.13% | 33.65% | 36.02% | 43.60% |
| Top-3 | 55.92% | 55.92% | 47.87% | 50.24% | 55.92% |
| Place Brier | 0.181239 | 0.188506 | 0.182283 | 0.181451 | 0.180497 |
| Place Log Loss | 0.542392 | 0.621698 | 0.544643 | 0.542569 | 0.540500 |
| Place precision | 47.47% | 46.76% | 43.84% | 43.76% | 45.97% |
| Gold | 18.48% | 18.01% | 16.11% | 17.54% | 19.43% |
| Good | 24.64% | 27.01% | 19.91% | 21.33% | 22.75% |
| Pass | 49.29% | 48.82% | 45.97% | 46.45% | 46.92% |

### WIN

Current Matrix Top-1: **22.75%**

Best ML Top-1: **21.33%**

Difference: **-1.42 percentage points**

Current Matrix Top-3: **55.92%**

Best ML Top-3: **50.24%**

Difference: **-5.69 percentage points**

Current Matrix Win Brier: **0.083892**

Best ML Win Brier: **0.084657**

Improvement: **-0.91%**

Current Matrix Win Log Loss: **0.296480**

Best ML Win Log Loss: **0.300749**

Improvement: **-1.44%**

### PLACE

Current Matrix Place Brier: **0.181239**

Best ML Place Brier: **0.181451**

Improvement: **-0.12%**

Current Matrix Place Log Loss: **0.542392**

Best ML Place Log Loss: **0.542569**

Improvement: **-0.03%**

## WALK-FORWARD ANALYSIS

ML improved vs Matrix: **2 / 5 periods**

ML underperformed Matrix: **3 / 5 periods**

| Period | Train end | Validation | Matrix score | Best ML score | Hybrid score |
|---:|---|---|---:|---:|---:|
| 1 | 2026-04-04 | 2026-04-06→2026-04-15 | -0.301617 | -0.308893 | -0.287201 |
| 2 | 2026-04-15 | 2026-04-16→2026-04-24 | -0.307610 | -0.303029 | -0.291538 |
| 3 | 2026-04-24 | 2026-04-25→2026-05-23 | -0.268378 | -0.288389 | -0.271079 |
| 4 | 2026-05-23 | 2026-05-24→2026-06-08 | -0.316331 | -0.321690 | -0.313941 |
| 5 | 2026-06-08 | 2026-06-10→2026-07-01 | -0.272797 | -0.257862 | -0.258484 |

Hybrid improved vs Matrix: **4 / 5 periods**

## CALIBRATION AND STATISTICAL SUPPORT

| Model | Win ECE | Place ECE |
|---|---:|---:|
| champion | 0.012278 | 0.038309 |
| logistic | 0.015764 | 0.054687 |
| lightgbm | 0.004933 | 0.028541 |
| xgboost | 0.006926 | 0.031575 |
| hybrid | 0.011512 | 0.041585 |

Paired race bootstrap (candidate minus Matrix; positive means improvement):

| Candidate | Metric | Mean | 95% CI |
|---|---|---:|---:|
| xgboost | win_brier_improvement | -0.001045 | [-0.002571, +0.000470] |
| xgboost | win_log_loss_improvement | -0.005325 | [-0.011111, +0.000085] |
| xgboost | place_brier_improvement | -0.001605 | [-0.004261, +0.001038] |
| xgboost | place_log_loss_improvement | -0.003316 | [-0.009828, +0.002987] |
| xgboost | top1_difference | -0.014746 | [-0.066351, +0.037915] |
| xgboost | top3_difference | -0.057464 | [-0.113744, -0.004739] |
| hybrid | win_brier_improvement | -0.000221 | [-0.000978, +0.000534] |
| hybrid | win_log_loss_improvement | -0.001202 | [-0.003972, +0.001390] |
| hybrid | place_brier_improvement | +0.000095 | [-0.001208, +0.001393] |
| hybrid | place_log_loss_improvement | +0.000446 | [-0.002794, +0.003490] |
| hybrid | top1_difference | +0.018050 | [-0.018957, +0.056872] |
| hybrid | top3_difference | +0.000149 | [-0.037915, +0.037915] |

## LEARNING CURVE

| Training races | Validation races | Win Brier | Place Brier | Top-1 | Top-3 |
|---:|---:|---:|---:|---:|---:|
| 100 | 150 | 0.076760 | 0.178118 | 22.00% | 50.67% |
| 200 | 150 | 0.076573 | 0.175942 | 24.00% | 50.67% |
| 300 | 150 | 0.076221 | 0.177766 | 25.33% | 50.00% |
| 400 | 150 | 0.076169 | 0.177607 | 22.00% | 53.33% |
| 444 | 150 | 0.075901 | 0.176773 | 24.00% | 53.33% |

## BETTING PERFORMANCE

Market odds were introduced only after all analysis predictions and model selection were frozen.

### WIN

Current Matrix Betting ROI: **-37.72%**

Best ML Betting ROI: **-52.66%**

Difference: **-14.94 percentage points**

### PLACE

Current Matrix Betting ROI: **N/A**

Best ML Betting ROI: **N/A**

Reason: historical place dividends are unavailable; win SP is not a valid proxy.

## RISK

Current Matrix Max Drawdown: **117.50 units**

ML Max Drawdown: **157.90 units**

### Full win betting scorecard

| Model | Bets | Profit (u) | ROI | Strike | Avg odds | Max DD (u) | Longest losing streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| champion | 228 | -86.00 | -37.72% | 4.39% | 19.40 | 117.50 | 64 |
| logistic | 273 | -130.20 | -47.69% | 6.59% | 15.83 | 147.20 | 49 |
| lightgbm | 222 | -140.60 | -63.33% | 2.70% | 19.28 | 164.60 | 107 |
| xgboost | 233 | -122.70 | -52.66% | 3.86% | 18.53 | 157.90 | 80 |
| hybrid | 215 | -99.50 | -46.28% | 3.72% | 19.20 | 123.50 | 58 |

## CLV

Current Matrix: **N/A**

ML: **N/A**

No timestamped opening/closing odds snapshots exist in the aligned archive.

## EXPLAINABILITY

Top permutation features for Place Brier:

- `leaf_pace_figure_score`: +0.004091
- `leaf_rating_score`: +0.003163
- `trainer_ly_place_rate`: +0.001950
- `leaf_performance_quality_score`: +0.001861
- `leaf_form_score`: +0.001797
- `trainer_ly_log_rides`: +0.001622
- `trainer_ly_win_rate`: +0.001094
- `jockey_ly_place_rate`: +0.001082
- `field_size`: +0.000756
- `recent_finish_mean_3`: +0.000616
- `days_since_last_run`: +0.000397
- `leaf_trainer_score`: +0.000380
- `pf_race_time_diff_avg`: +0.000347
- `pf_l600_delta_avg`: +0.000252
- `recent_finish_mean_5`: +0.000249
- `near_distance_place_rate`: +0.000243
- `leaf_pace_map_score`: +0.000226
- `recent_place_rate_5`: +0.000193
- `leaf_distance_score`: +0.000189
- `race_type`: +0.000152

Top TreeSHAP features for the selected Place model:

- `numeric__leaf_pace_figure_score`: 0.182130
- `numeric__leaf_rating_score`: 0.160406
- `numeric__leaf_form_score`: 0.118246
- `numeric__trainer_ly_place_rate`: 0.107393
- `numeric__barrier`: 0.100043
- `numeric__trainer_ly_log_rides`: 0.099426
- `numeric__leaf_trial_score`: 0.093216
- `numeric__field_size`: 0.089325
- `numeric__jockey_ly_place_rate`: 0.087250
- `numeric__leaf_performance_quality_score`: 0.061829
- `numeric__trainer_ly_win_rate`: 0.054495
- `numeric__recent_finish_mean_3`: 0.052707
- `numeric__pf_l600_delta_avg`: 0.049054
- `numeric__leaf_class_score`: 0.047650
- `numeric__leaf_jockey_horse_fit_score`: 0.044442
- `numeric__leaf_trainer_score`: 0.040033
- `numeric__leaf_pace_map_score`: 0.038140
- `categorical__race_type_Benchmark`: 0.037478
- `numeric__days_since_last_run`: 0.036006
- `numeric__jockey_ly_win_rate`: 0.033163

## SEGMENT ANALYSIS

The full venue breakdown is preserved in the JSON result. Major structural segments are below.

| Segment | Group | Races | Matrix Win Brier | ML Win Brier | Matrix Top-3 | ML Top-3 |
|---|---|---:|---:|---:|---:|---:|
| distance | Middle1500-1800 | 47 | 0.078635 | 0.080315 | 59.57% | 57.45% |
| distance | Sprint1200-1400 | 85 | 0.081654 | 0.081404 | 55.29% | 55.29% |
| distance | Sprint<=1100 | 50 | 0.092027 | 0.093862 | 52.00% | 32.00% |
| distance | Staying1900-2200 | 22 | 0.085332 | 0.086072 | 54.55% | 54.55% |
| distance | Staying2300+ | 7 | 0.090483 | 0.090402 | 71.43% | 57.14% |
| class | Benchmark | 66 | 0.081072 | 0.079890 | 51.52% | 50.00% |
| class | Handicap | 20 | 0.084004 | 0.082557 | 40.00% | 45.00% |
| class | Maiden | 22 | 0.085942 | 0.088321 | 59.09% | 54.55% |
| class | Other | 101 | 0.085627 | 0.087608 | 61.39% | 50.50% |
| track_condition | Good/Firm | 40 | 0.091727 | 0.092128 | 55.00% | 55.00% |
| track_condition | Heavy | 38 | 0.082088 | 0.083299 | 50.00% | 50.00% |
| track_condition | Soft | 109 | 0.081338 | 0.081878 | 55.96% | 49.54% |
| track_condition | Synthetic | 24 | 0.087336 | 0.089094 | 66.67% | 45.83% |
| field_size | Large12+ | 122 | 0.075217 | 0.075341 | 51.64% | 46.72% |
| field_size | Medium8-11 | 79 | 0.097662 | 0.100052 | 59.49% | 54.43% |
| field_size | Small<=7 | 10 | 0.138103 | 0.135673 | 80.00% | 60.00% |
| confidence | High | 154 | 0.083473 | 0.084300 | 53.90% | 48.70% |
| confidence | Low | 14 | 0.088677 | 0.092226 | 50.00% | 35.71% |
| confidence | Medium | 43 | 0.083909 | 0.083541 | 65.12% | 60.47% |

## PRODUCTION PROMOTION GATE

| Candidate | Probability | Top rank | Walk-forward | Bootstrap | Betting risk | Overall |
|---|---|---|---|---|---|---|
| xgboost | FAIL | FAIL | FAIL (2/5) | FAIL | FAIL | FAIL |
| hybrid | FAIL | PASS | PASS (4/5) | FAIL | FAIL | FAIL |

- Candidate assessed: xgboost
- Probability gate: FAIL
- Top-rank gate: FAIL
- Walk-forward consistency: 2/5 periods (FAIL)
- Paired bootstrap support: FAIL
- Betting not materially worse (5pp tolerance): FAIL

## FINAL VERDICT

**KEEP CURRENT MATRIX**

Neither the independent challenger nor the hybrid cleared every probability, ranking, walk-forward, statistical-support and betting-risk gate. Keep the deterministic Champion and preserve the ML pipeline/results as research.

Production Rating Matrix code was not changed by model training or betting results.
