# AU Wong Choi ML Experiment Report

## AU WONG CHOI ML RESULT

Current Production Model: **Current AU Wong Choi Rating Matrix**

Best Independent Analysis Model: **lightgbm**

Best Analysis Hybrid: **Matrix + lightgbm @ 50% ML**

Historical Dataset: **805 races / 8249 runners**

Final Out-of-Sample Test: **211 races / 2157 runners**

> This final chronological block was untouched by this ML model-selection run, but the archive was previously used to optimise the Rating Matrix. It is not claimed as globally untouched.

## ANALYSIS PERFORMANCE

| Metric | Current Matrix | Logistic | LightGBM | XGBoost | Hybrid |
|---|---:|---:|---:|---:|---:|
| Win Brier | 0.083892 | 0.085257 | 0.085081 | 0.084406 | 0.084185 |
| Win Log Loss | 0.296480 | 0.307530 | 0.302526 | 0.299435 | 0.297964 |
| Top-1 | 22.75% | 27.96% | 18.01% | 22.27% | 20.85% |
| Top-2 | 44.08% | 43.13% | 33.65% | 36.97% | 37.91% |
| Top-3 | 55.92% | 55.45% | 47.87% | 53.55% | 53.55% |
| Top-5 | 77.73% | 73.93% | 69.67% | 75.83% | 74.88% |
| Place Brier | 0.181239 | 0.188572 | 0.182283 | 0.182015 | 0.180769 |
| Place Log Loss | 0.542392 | 0.622724 | 0.544643 | 0.543905 | 0.541005 |
| Place precision | 47.47% | 46.76% | 43.84% | 43.92% | 45.02% |
| Winner average rank | 3.754717 | 3.877358 | 4.264151 | 3.915094 | 3.948113 |
| Place-getter average rank | 4.313433 | 4.331675 | 4.346600 | 4.353234 | 4.298507 |
| Ranking correlation | 0.322871 | 0.321274 | 0.287787 | 0.300030 | 0.323971 |
| Gold | 18.48% | 18.48% | 16.11% | 16.59% | 18.01% |
| Gold strict | 6.64% | 6.16% | 6.16% | 6.16% | 7.58% |
| Good | 24.64% | 27.01% | 19.91% | 21.80% | 21.80% |
| Pass | 49.29% | 48.82% | 45.97% | 47.39% | 47.39% |

### WIN

Current Matrix Top-1: **22.75%**

Best ML Top-1: **18.01%**

Difference: **-4.74 percentage points**

Current Matrix Top-3: **55.92%**

Best ML Top-3: **47.87%**

Difference: **-8.06 percentage points**

Current Matrix Win Brier: **0.083892**

Best ML Win Brier: **0.085081**

Improvement: **-1.42%**

Current Matrix Win Log Loss: **0.296480**

Best ML Win Log Loss: **0.302526**

Improvement: **-2.04%**

### PLACE

Current Matrix Place Brier: **0.181239**

Best ML Place Brier: **0.182283**

Improvement: **-0.58%**

Current Matrix Place Log Loss: **0.542392**

Best ML Place Log Loss: **0.544643**

Improvement: **-0.42%**

## WALK-FORWARD ANALYSIS

ML improved vs Matrix: **0 / 5 periods**

ML underperformed Matrix: **5 / 5 periods**

| Period | Train end | Validation | Matrix score | Best ML score | Hybrid score |
|---:|---|---|---:|---:|---:|
| 1 | 2026-04-04 | 2026-04-06→2026-04-15 | -0.301617 | -0.303271 | -0.289480 |
| 2 | 2026-04-15 | 2026-04-16→2026-04-24 | -0.307610 | -0.310517 | -0.297376 |
| 3 | 2026-04-24 | 2026-04-25→2026-05-23 | -0.268378 | -0.283755 | -0.271778 |
| 4 | 2026-05-23 | 2026-05-24→2026-06-08 | -0.316331 | -0.318877 | -0.305706 |
| 5 | 2026-06-08 | 2026-06-10→2026-07-01 | -0.272797 | -0.275096 | -0.255353 |

Hybrid improved vs Matrix: **4 / 5 periods**

## CALIBRATION AND STATISTICAL SUPPORT

| Model | Win ECE | Place ECE |
|---|---:|---:|
| champion | 0.012278 | 0.038309 |
| logistic | 0.015745 | 0.053672 |
| lightgbm | 0.004933 | 0.028541 |
| xgboost | 0.003851 | 0.028518 |
| hybrid | 0.006379 | 0.035211 |

Selected lightgbm chronological-holdout probability buckets:

| Target | Probability bucket | Runners | Mean predicted | Observed |
|---|---|---:|---:|---:|
| win | (-0.001, 0.1] | 1343 | 6.23% | 6.18% |
| win | (0.1, 0.2] | 669 | 13.57% | 14.35% |
| win | (0.2, 0.3] | 126 | 23.70% | 20.63% |
| win | (0.3, 0.4] | 16 | 32.94% | 31.25% |
| win | (0.4, 0.5] | 2 | 41.95% | 50.00% |
| win | (0.5, 0.6] | 1 | 52.88% | 100.00% |
| place | (-0.001, 0.1] | 49 | 8.43% | 8.16% |
| place | (0.1, 0.2] | 562 | 15.63% | 12.63% |
| place | (0.2, 0.3] | 718 | 24.86% | 23.82% |
| place | (0.3, 0.4] | 486 | 34.49% | 38.27% |
| place | (0.4, 0.5] | 227 | 43.84% | 42.29% |
| place | (0.5, 0.6] | 87 | 53.55% | 65.52% |
| place | (0.6, 0.7] | 22 | 63.78% | 72.73% |
| place | (0.7, 0.8] | 4 | 74.37% | 50.00% |
| place | (0.8, 0.9] | 1 | 85.70% | 0.00% |
| place | (0.9, 1.0] | 1 | 90.94% | 0.00% |

Paired race bootstrap (candidate minus Matrix; positive means improvement):

| Candidate | Metric | Mean | 95% CI |
|---|---|---:|---:|
| lightgbm | win_brier_improvement | -0.001514 | [-0.003034, +0.000002] |
| lightgbm | win_log_loss_improvement | -0.007231 | [-0.013119, -0.001585] |
| lightgbm | place_brier_improvement | -0.002885 | [-0.005925, +0.000180] |
| lightgbm | place_log_loss_improvement | -0.006440 | [-0.014228, +0.000395] |
| lightgbm | top1_difference | -0.048133 | [-0.094787, +0.000000] |
| lightgbm | top3_difference | -0.080995 | [-0.142180, -0.023697] |
| hybrid | win_brier_improvement | -0.000428 | [-0.001178, +0.000326] |
| hybrid | win_log_loss_improvement | -0.001968 | [-0.004799, +0.000752] |
| hybrid | place_brier_improvement | -0.000398 | [-0.001899, +0.001097] |
| hybrid | place_log_loss_improvement | -0.000554 | [-0.004248, +0.002793] |
| hybrid | top1_difference | -0.019796 | [-0.056872, +0.023697] |
| hybrid | top3_difference | -0.024076 | [-0.066351, +0.018957] |

## LEARNING CURVE

| Training races | Validation races | Win Brier | Place Brier | Top-1 | Top-3 |
|---:|---:|---:|---:|---:|---:|
| 100 | 150 | 0.077336 | 0.178627 | 23.33% | 47.33% |
| 200 | 150 | 0.076248 | 0.176329 | 24.00% | 53.33% |
| 300 | 150 | 0.075927 | 0.178606 | 23.33% | 52.67% |
| 400 | 150 | 0.076818 | 0.177991 | 19.33% | 51.33% |
| 444 | 150 | 0.076385 | 0.177989 | 24.67% | 50.67% |

The maximum training point is 444 races because the last 150 development races remain a fixed chronological learning-curve validation block. Testing 500/600 training races would overlap that block and violate the point-in-time comparison. Win Brier continued to improve modestly, while Top-1/Top-3 remained unstable; more races may help probability estimation but current data do not show a stable ranking breakthrough.

## BETTING PERFORMANCE

Market odds were introduced only after all analysis predictions and model selection were frozen.

### WIN

Current Matrix Betting ROI: **-37.72%**

Best ML Betting ROI: **-63.33%**

Difference: **-25.61 percentage points**

### PLACE

Current Matrix Betting ROI: **N/A**

Best ML Betting ROI: **N/A**

Reason: historical place dividends are unavailable; win SP is not a valid proxy.

## RISK

Current Matrix Max Drawdown: **117.50 units**

ML Max Drawdown: **164.60 units**

### Full win betting scorecard

| Model | Bets | Profit (u) | ROI | Strike | Avg odds | Max DD (u) | Longest losing streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| champion | 228 | -86.00 | -37.72% | 4.39% | 19.40 | 117.50 | 64 |
| logistic | 272 | -129.20 | -47.50% | 6.62% | 15.87 | 146.20 | 49 |
| lightgbm | 222 | -140.60 | -63.33% | 2.70% | 19.28 | 164.60 | 107 |
| xgboost | 218 | -120.00 | -55.05% | 2.75% | 18.78 | 155.00 | 87 |
| hybrid | 205 | -106.50 | -51.95% | 3.41% | 19.59 | 128.50 | 49 |

### Post-analysis betting segments

Favourite status, odds and edge are created only after predictions are frozen. Full venue/distance/class/track/race-type/field-size breakdowns are preserved in the JSON result.

| Model | Segment | Group | Bets | Profit (u) | ROI | Strike | Max DD (u) |
|---|---|---|---:|---:|---:|---:|---:|
| champion | market_status | NonFavourite | 228 | -86.00 | -37.72% | 4.39% | 117.50 |
| champion | odds_band | 12-25 | 103 | -34.00 | -33.01% | 3.88% | 44.00 |
| champion | odds_band | 25-50 | 67 | -36.00 | -53.73% | 1.49% | 61.00 |
| champion | odds_band | 3-6 | 8 | -8.00 | -100.00% | 0.00% | 8.00 |
| champion | odds_band | 6-12 | 50 | -8.00 | -16.00% | 10.00% | 27.00 |
| champion | predicted_edge | 10-20% | 42 | -3.50 | -8.33% | 9.52% | 12.50 |
| champion | predicted_edge | 20%+ | 2 | -2.00 | -100.00% | 0.00% | 2.00 |
| champion | predicted_edge | 5-10% | 184 | -80.50 | -43.75% | 3.26% | 116.00 |
| champion | confidence | High | 164 | -46.50 | -28.35% | 4.88% | 82.00 |
| champion | confidence | Low | 18 | 0.00 | 0.00% | 5.56% | 9.00 |
| champion | confidence | Medium | 46 | -39.50 | -85.87% | 2.17% | 39.50 |
| lightgbm | market_status | Favourite/TiedFavourite | 1 | 3.20 | 320.00% | 100.00% | 0.00 |
| lightgbm | market_status | NonFavourite | 221 | -143.80 | -65.07% | 2.26% | 167.80 |
| lightgbm | odds_band | 12-25 | 81 | -47.00 | -58.02% | 2.47% | 47.00 |
| lightgbm | odds_band | 25-50 | 69 | -38.00 | -55.07% | 1.45% | 64.00 |
| lightgbm | odds_band | 3-6 | 12 | -3.60 | -30.00% | 16.67% | 7.00 |
| lightgbm | odds_band | 6-12 | 60 | -52.00 | -86.67% | 1.67% | 56.00 |
| lightgbm | predicted_edge | 10-20% | 49 | -41.00 | -83.67% | 2.04% | 43.00 |
| lightgbm | predicted_edge | 20%+ | 4 | -4.00 | -100.00% | 0.00% | 4.00 |
| lightgbm | predicted_edge | 5-10% | 169 | -95.60 | -56.57% | 2.96% | 121.60 |
| lightgbm | confidence | High | 167 | -85.60 | -51.26% | 3.59% | 111.60 |
| lightgbm | confidence | Low | 14 | -14.00 | -100.00% | 0.00% | 14.00 |
| lightgbm | confidence | Medium | 41 | -41.00 | -100.00% | 0.00% | 41.00 |
| hybrid | market_status | NonFavourite | 205 | -106.50 | -51.95% | 3.41% | 128.50 |
| hybrid | odds_band | 12-25 | 84 | -50.00 | -59.52% | 2.38% | 50.00 |
| hybrid | odds_band | 25-50 | 65 | -34.00 | -52.31% | 1.54% | 58.00 |
| hybrid | odds_band | 3-6 | 5 | -5.00 | -100.00% | 0.00% | 5.00 |
| hybrid | odds_band | 6-12 | 51 | -17.50 | -34.31% | 7.84% | 28.00 |
| hybrid | predicted_edge | 10-20% | 34 | -26.00 | -76.47% | 2.94% | 32.00 |
| hybrid | predicted_edge | 20%+ | 3 | -3.00 | -100.00% | 0.00% | 3.00 |
| hybrid | predicted_edge | 5-10% | 168 | -77.50 | -46.13% | 3.57% | 98.50 |
| hybrid | confidence | High | 149 | -57.00 | -38.26% | 4.03% | 81.00 |
| hybrid | confidence | Low | 15 | -15.00 | -100.00% | 0.00% | 15.00 |
| hybrid | confidence | Medium | 41 | -34.50 | -84.15% | 2.44% | 34.50 |

## CLV

Current Matrix: **N/A**

ML: **N/A**

No timestamped opening/closing odds snapshots exist in the aligned archive.

## EXPLAINABILITY

Top permutation features for Place Brier:

- `leaf_pace_figure_score`: +0.004408
- `leaf_rating_score`: +0.002310
- `trainer_ly_place_rate`: +0.002205
- `leaf_form_score`: +0.001904
- `leaf_performance_quality_score`: +0.001695
- `trainer_ly_log_rides`: +0.001549
- `trainer_ly_win_rate`: +0.001351
- `jockey_ly_place_rate`: +0.000845
- `field_size`: +0.000651
- `leaf_trainer_score`: +0.000642
- `leaf_pace_map_score`: +0.000639
- `pf_l600_delta_avg`: +0.000506
- `recent_finish_mean_3`: +0.000409
- `days_since_last_run`: +0.000393
- `leaf_trial_score`: +0.000282
- `recent_finish_mean_5`: +0.000277
- `race_type`: +0.000265
- `pf_race_time_diff_avg`: +0.000265
- `near_distance_place_rate`: +0.000224
- `current_jockey_win_rate`: +0.000170

Top TreeSHAP features for the selected Place model:

- `numeric__leaf_pace_figure_score`: 0.179637
- `numeric__leaf_rating_score`: 0.166251
- `numeric__leaf_form_score`: 0.113314
- `numeric__trainer_ly_log_rides`: 0.107736
- `numeric__trainer_ly_place_rate`: 0.104617
- `numeric__field_size`: 0.102118
- `numeric__barrier`: 0.093236
- `numeric__leaf_trial_score`: 0.087245
- `numeric__jockey_ly_place_rate`: 0.080076
- `numeric__pf_l600_delta_avg`: 0.074370
- `numeric__recent_finish_mean_3`: 0.070467
- `numeric__trainer_ly_win_rate`: 0.062912
- `numeric__leaf_trainer_score`: 0.062717
- `numeric__leaf_performance_quality_score`: 0.054390
- `numeric__leaf_jockey_horse_fit_score`: 0.051526
- `numeric__leaf_class_score`: 0.047664
- `numeric__days_since_last_run`: 0.041422
- `numeric__leaf_pace_map_score`: 0.041020
- `numeric__jockey_ly_win_rate`: 0.038633
- `categorical__race_type_Benchmark`: 0.037037

### Ten diagnostic questions

1. **Which features genuinely improve prediction?** Permutation and TreeSHAP agree that pace figure, official rating, recent form, trainer place performance and Performance Quality are the strongest reusable signals. This is predictive association on the holdout, not a causal claim.
2. **Which Matrix features remain strong?** `leaf_pace_figure_score`, `leaf_rating_score`, `leaf_form_score` and `leaf_performance_quality_score` all appear near the top, supporting the core Matrix design.
3. **Which are weak?** Features outside the leading permutation set, including heavily neutral report leaves, add little stable holdout value. Examples: sectional importance -0.000172, health +0.000038, confidence +0.000019.
4. **Which are duplicated?** Conceptual overlaps audited: rating, leaf_rating_score; recent_finish_mean_3, recent_finish_mean_5, recent_finish_best_3, leaf_form_score; recent_place_rate_5, recent_win_rate_5, leaf_consistency_score; pf_l600_delta_avg, pf_race_time_diff_avg, leaf_pace_figure_score; jockey_ly_win_rate, jockey_ly_place_rate, leaf_jockey_score; trainer_ly_win_rate, trainer_ly_place_rate, leaf_trainer_score. Exact non-constant duplicates are reported separately in readiness.
5. **Which appear overweighted?** No Matrix dimension can be defensibly labelled overweighted from this experiment: removing the Matrix structure made independent ML ranking materially worse, especially Top-3.
6. **Which appear underweighted?** The hybrid hints that conditional combinations can improve Place Brier, but ranking worsened and bootstrap intervals cross zero. That is insufficient evidence to reweight any live dimension.
7. **Which neutral/default features create noise?** Constant/dead snapshot inputs are: leaf_form_score_derived, leaf_form_score_missing, leaf_trial_score_derived, leaf_trial_score_missing, leaf_sectional_score_derived, leaf_sectional_score_fallback, leaf_pace_map_score_observed, leaf_pace_map_score_derived, leaf_pace_map_score_fallback, leaf_pace_map_score_missing, leaf_jockey_score_derived, leaf_jockey_score_missing, leaf_trainer_score_observed, leaf_trainer_score_derived, leaf_trainer_score_fallback, leaf_trainer_score_missing, leaf_jockey_horse_fit_score_observed, leaf_jockey_horse_fit_score_missing, leaf_class_score_observed, leaf_class_score_missing, leaf_rating_score_derived, leaf_rating_score_missing, leaf_weight_score_derived, leaf_weight_score_fallback, leaf_distance_score_observed, leaf_distance_score_missing, leaf_track_score_derived, leaf_track_score_missing, leaf_formline_score_observed, leaf_formline_score_missing, leaf_consistency_score_observed, leaf_consistency_score_missing, leaf_performance_quality_score_derived, leaf_performance_quality_score_missing, leaf_health_score_observed, leaf_health_score_derived, leaf_health_score_fallback, leaf_health_score_missing, leaf_confidence_score_observed, leaf_confidence_score_derived, leaf_confidence_score_fallback, leaf_confidence_score_missing, leaf_pace_figure_score_derived, leaf_pace_figure_score_fallback. The pipeline now drops zero-variance columns inside each chronological training fit; high-neutral leaves such as weight and sectionals remain documented and should not gain influence without new evidence.
8. **Which nonlinear relationships appear?** XGBoost uses barrier, field size, race type and trainer/jockey rates alongside pace/rating. However, its final Top-3 deficit shows those nonlinearities do not generalise strongly enough yet.
9. **Which interactions are missing from Matrix?** The strongest unresolved candidate is shallow formal history × wet going, plus condition-specific trainer/jockey and timed-trial evidence. Existing archive fields cannot identify these point-in-time effects reliably.
10. **What is ML learning that Wong Choi misses?** Mostly conditional scaling of signals the Matrix already has, rather than a new independent ability source. The 50% hybrid's small Place-probability gains are statistically fragile, ranking and betting performance are worse, so this learning is research-only.

## SEGMENT ANALYSIS

The full venue breakdown is preserved in the JSON result. Major structural segments are below.

| Segment | Group | Races | Matrix Win Brier | ML Win Brier | Matrix Top-3 | ML Top-3 |
|---|---|---:|---:|---:|---:|---:|
| distance | Middle1500-1800 | 47 | 0.078635 | 0.081627 | 59.57% | 44.68% |
| distance | Sprint1200-1400 | 85 | 0.081654 | 0.082076 | 55.29% | 52.94% |
| distance | Sprint<=1100 | 50 | 0.092027 | 0.092858 | 52.00% | 44.00% |
| distance | Staying1900-2200 | 22 | 0.085332 | 0.086361 | 54.55% | 40.91% |
| distance | Staying2300+ | 7 | 0.090483 | 0.091626 | 71.43% | 57.14% |
| class | Benchmark | 66 | 0.081072 | 0.080934 | 51.52% | 46.97% |
| class | Handicap | 20 | 0.084004 | 0.082327 | 40.00% | 50.00% |
| class | Maiden | 22 | 0.085942 | 0.087810 | 59.09% | 54.55% |
| class | Other | 101 | 0.085627 | 0.087973 | 61.39% | 46.53% |
| race_type | Benchmark | 66 | 0.081072 | 0.080934 | 51.52% | 46.97% |
| race_type | Handicap | 20 | 0.084004 | 0.082327 | 40.00% | 50.00% |
| race_type | Maiden | 22 | 0.085942 | 0.087810 | 59.09% | 54.55% |
| race_type | Other | 101 | 0.085627 | 0.087973 | 61.39% | 46.53% |
| track_condition | Good/Firm | 40 | 0.091727 | 0.092918 | 55.00% | 47.50% |
| track_condition | Heavy | 38 | 0.082088 | 0.083923 | 50.00% | 50.00% |
| track_condition | Soft | 109 | 0.081338 | 0.082336 | 55.96% | 48.62% |
| track_condition | Synthetic | 24 | 0.087336 | 0.088419 | 66.67% | 41.67% |
| field_size | Large12+ | 122 | 0.075217 | 0.075495 | 51.64% | 45.08% |
| field_size | Medium8-11 | 79 | 0.097662 | 0.101250 | 59.49% | 49.37% |
| field_size | Small<=7 | 10 | 0.138103 | 0.133728 | 80.00% | 70.00% |
| confidence | High | 154 | 0.083473 | 0.084807 | 53.90% | 46.75% |
| confidence | Low | 14 | 0.088677 | 0.091528 | 50.00% | 50.00% |
| confidence | Medium | 43 | 0.083909 | 0.084020 | 65.12% | 51.16% |
| market_status | FavouriteWon | 81 | 0.079960 | 0.079919 | 80.25% | 70.37% |
| market_status | NonFavouriteWon | 130 | 0.086224 | 0.088143 | 40.77% | 33.85% |

`market_status` is a retrospective race-level slice (`FavouriteWon` / `NonFavouriteWon`) created only after predictions were frozen; every race remains whole. It is not an input feature. Betting segments for every model and every required family are in `au_ml_experiment_results.json`.

## REPRODUCIBILITY

Run the complete archive → runtime snapshot → readiness → ML program with one command:

```bash
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_ml_rebuild.py \
  --archive-root "<AU_Racing archive>" \
  --results-csv "<point-in-time merged results.csv>" \
  --work-dir /private/tmp/au_ml_program \
  --report-dir .
```

The wrapper defaults to `--require-complete`, records commands/input and output hashes in `au_ml_rebuild_manifest.json`, and inherits the caller environment. On macOS, LightGBM/XGBoost may require `DYLD_LIBRARY_PATH` pointing to a trusted `libomp` installation.

## PRODUCTION PROMOTION GATE

| Candidate | Probability | Top rank | Walk-forward | Bootstrap | Betting risk | Overall |
|---|---|---|---|---|---|---|
| lightgbm | FAIL | FAIL | FAIL (0/5) | FAIL | FAIL | FAIL |
| hybrid | FAIL | FAIL | PASS (4/5) | FAIL | FAIL | FAIL |

- Candidate assessed: lightgbm
- Probability gate: FAIL
- Top-rank gate: FAIL
- Walk-forward consistency: 0/5 periods (FAIL)
- Paired bootstrap support: FAIL
- Betting not materially worse (5pp tolerance): FAIL

## FINAL VERDICT

**KEEP CURRENT MATRIX**

Neither the independent challenger nor the hybrid cleared every probability, ranking, walk-forward, statistical-support and betting-risk gate. Keep the deterministic Champion and preserve the ML pipeline/results as research.

Production Rating Matrix code was not changed by model training or betting results.
