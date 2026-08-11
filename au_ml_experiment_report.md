# AU Wong Choi ML Experiment Report

## AU WONG CHOI ML RESULT

Current Production Model: **Current AU Wong Choi Rating Matrix**

Best Independent Analysis Model: **lightgbm**

Best Analysis Hybrid: **Matrix + lightgbm @ 50% ML**

Historical Dataset: **802 races / 8222 runners**

Final Out-of-Sample Test: **210 races / 2145 runners**

> This final chronological block was untouched by this ML model-selection run, but the archive was previously used to optimise the Rating Matrix. It is not claimed as globally untouched.

## ANALYSIS PERFORMANCE

| Metric | Current Matrix | Logistic | LightGBM | XGBoost | Hybrid |
|---|---:|---:|---:|---:|---:|
| Win Brier | 0.083533 | 0.084910 | 0.084671 | 0.084159 | 0.083801 |
| Win Log Loss | 0.295252 | 0.306427 | 0.300668 | 0.298955 | 0.296477 |
| Top-1 | 22.86% | 28.10% | 19.52% | 20.95% | 22.38% |
| Top-2 | 44.29% | 42.86% | 37.14% | 37.62% | 40.48% |
| Top-3 | 55.71% | 55.24% | 50.95% | 49.52% | 54.76% |
| Top-5 | 77.62% | 74.29% | 71.90% | 75.71% | 74.29% |
| Place Brier | 0.181390 | 0.188490 | 0.182377 | 0.181495 | 0.180935 |
| Place Log Loss | 0.542741 | 0.621617 | 0.544894 | 0.542596 | 0.541416 |
| Place precision | 47.38% | 46.51% | 43.73% | 45.00% | 45.71% |
| Winner average rank | 3.728571 | 3.857143 | 4.085714 | 4.009524 | 3.900000 |
| Place-getter average rank | 4.311667 | 4.328333 | 4.343333 | 4.318333 | 4.275000 |
| Ranking correlation | 0.322891 | 0.323215 | 0.292689 | 0.294264 | 0.323207 |
| Gold | 18.57% | 19.05% | 18.57% | 16.19% | 18.10% |
| Gold strict | 6.67% | 6.67% | 5.71% | 4.76% | 7.62% |
| Good | 24.76% | 27.14% | 21.90% | 21.90% | 22.38% |
| Pass | 49.05% | 49.52% | 50.00% | 45.24% | 48.10% |

### WIN

Current Matrix Top-1: **22.86%**

Best ML Top-1: **19.52%**

Difference: **-3.33 percentage points**

Current Matrix Top-3: **55.71%**

Best ML Top-3: **50.95%**

Difference: **-4.76 percentage points**

Current Matrix Win Brier: **0.083533**

Best ML Win Brier: **0.084671**

Improvement: **-1.36%**

Current Matrix Win Log Loss: **0.295252**

Best ML Win Log Loss: **0.300668**

Improvement: **-1.83%**

### PLACE

Current Matrix Place Brier: **0.181390**

Best ML Place Brier: **0.182377**

Improvement: **-0.54%**

Current Matrix Place Log Loss: **0.542741**

Best ML Place Log Loss: **0.544894**

Improvement: **-0.40%**

## WALK-FORWARD ANALYSIS

ML improved vs Matrix: **1 / 5 periods**

ML underperformed Matrix: **4 / 5 periods**

| Period | Train end | Validation | Matrix score | Best ML score | Hybrid score |
|---:|---|---|---:|---:|---:|
| 1 | 2026-04-04 | 2026-04-06→2026-04-15 | -0.301617 | -0.303271 | -0.289480 |
| 2 | 2026-04-15 | 2026-04-16→2026-04-24 | -0.307610 | -0.310517 | -0.297376 |
| 3 | 2026-04-24 | 2026-04-25→2026-05-23 | -0.271421 | -0.286347 | -0.274574 |
| 4 | 2026-05-23 | 2026-05-24→2026-06-08 | -0.316093 | -0.318736 | -0.307608 |
| 5 | 2026-06-08 | 2026-06-10→2026-07-01 | -0.274788 | -0.274122 | -0.255641 |

Hybrid improved vs Matrix: **4 / 5 periods**

## CALIBRATION AND STATISTICAL SUPPORT

| Model | Win ECE | Place ECE |
|---|---:|---:|
| champion | 0.012082 | 0.037642 |
| logistic | 0.015104 | 0.053099 |
| lightgbm | 0.011048 | 0.027213 |
| xgboost | 0.008542 | 0.027773 |
| hybrid | 0.011568 | 0.038144 |

Selected lightgbm chronological-holdout probability buckets:

| Target | Probability bucket | Runners | Mean predicted | Observed |
|---|---|---:|---:|---:|
| win | (-0.001, 0.1] | 1331 | 6.25% | 5.79% |
| win | (0.1, 0.2] | 676 | 13.64% | 15.24% |
| win | (0.2, 0.3] | 118 | 23.51% | 19.49% |
| win | (0.3, 0.4] | 18 | 32.91% | 27.78% |
| win | (0.4, 0.5] | 1 | 41.21% | 100.00% |
| win | (0.5, 0.6] | 1 | 51.69% | 100.00% |
| place | (-0.001, 0.1] | 52 | 8.59% | 7.69% |
| place | (0.1, 0.2] | 537 | 15.67% | 11.36% |
| place | (0.2, 0.3] | 744 | 24.86% | 24.46% |
| place | (0.3, 0.4] | 484 | 34.59% | 38.02% |
| place | (0.4, 0.5] | 217 | 44.17% | 45.62% |
| place | (0.5, 0.6] | 84 | 53.78% | 61.90% |
| place | (0.6, 0.7] | 21 | 63.72% | 76.19% |
| place | (0.7, 0.8] | 4 | 72.56% | 50.00% |
| place | (0.8, 0.9] | 1 | 84.24% | 0.00% |
| place | (0.9, 1.0] | 1 | 91.41% | 0.00% |

Paired race bootstrap (candidate minus Matrix; positive means improvement):

| Candidate | Metric | Mean | 95% CI |
|---|---|---:|---:|
| lightgbm | win_brier_improvement | -0.001371 | [-0.002857, +0.000102] |
| lightgbm | win_log_loss_improvement | -0.006192 | [-0.011763, -0.000744] |
| lightgbm | place_brier_improvement | -0.002693 | [-0.005646, +0.000182] |
| lightgbm | place_log_loss_improvement | -0.006109 | [-0.013220, +0.000641] |
| lightgbm | top1_difference | -0.033390 | [-0.085714, +0.019048] |
| lightgbm | top3_difference | -0.047374 | [-0.109524, +0.019048] |
| hybrid | win_brier_improvement | -0.000360 | [-0.001095, +0.000375] |
| hybrid | win_log_loss_improvement | -0.001512 | [-0.004283, +0.001130] |
| hybrid | place_brier_improvement | -0.000347 | [-0.001785, +0.001043] |
| hybrid | place_log_loss_improvement | -0.000497 | [-0.003851, +0.002712] |
| hybrid | top1_difference | -0.004774 | [-0.042857, +0.033333] |
| hybrid | top3_difference | -0.009829 | [-0.052381, +0.033333] |

## LEARNING CURVE

| Training races | Validation races | Win Brier | Place Brier | Top-1 | Top-3 |
|---:|---:|---:|---:|---:|---:|
| 100 | 149 | 0.077641 | 0.178191 | 22.15% | 45.64% |
| 200 | 149 | 0.075817 | 0.176222 | 24.83% | 51.68% |
| 300 | 149 | 0.076176 | 0.178491 | 22.82% | 51.68% |
| 400 | 149 | 0.076788 | 0.177516 | 20.81% | 53.02% |
| 443 | 149 | 0.076343 | 0.177793 | 24.83% | 50.34% |

The maximum training point is 444 races because the last 150 development races remain a fixed chronological learning-curve validation block. Testing 500/600 training races would overlap that block and violate the point-in-time comparison. Win Brier continued to improve modestly, while Top-1/Top-3 remained unstable; more races may help probability estimation but current data do not show a stable ranking breakthrough.

## BETTING PERFORMANCE

Market odds were introduced only after all analysis predictions and model selection were frozen.

### WIN

Current Matrix Betting ROI: **-37.17%**

Best ML Betting ROI: **-46.49%**

Difference: **-9.32 percentage points**

### PLACE

Current Matrix Betting ROI: **N/A**

Best ML Betting ROI: **N/A**

Reason: historical place dividends are unavailable; win SP is not a valid proxy.

## RISK

Current Matrix Max Drawdown: **115.50 units**

ML Max Drawdown: **104.60 units**

### Full win betting scorecard

| Model | Bets | Profit (u) | ROI | Strike | Avg odds | Max DD (u) | Longest losing streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| champion | 226 | -84.00 | -37.17% | 4.42% | 19.46 | 115.50 | 62 |
| logistic | 272 | -129.20 | -47.50% | 6.62% | 16.01 | 146.20 | 48 |
| lightgbm | 225 | -104.60 | -46.49% | 4.00% | 19.36 | 104.60 | 35 |
| xgboost | 220 | -135.00 | -61.36% | 2.27% | 18.65 | 156.00 | 86 |
| hybrid | 199 | -100.50 | -50.50% | 3.52% | 19.36 | 122.50 | 45 |

### Post-analysis betting segments

Favourite status, odds and edge are created only after predictions are frozen. Full venue/distance/class/track/race-type/field-size breakdowns are preserved in the JSON result.

| Model | Segment | Group | Bets | Profit (u) | ROI | Strike | Max DD (u) |
|---|---|---|---:|---:|---:|---:|---:|
| champion | market_status | NonFavourite | 226 | -84.00 | -37.17% | 4.42% | 115.50 |
| champion | odds_band | 12-25 | 102 | -33.00 | -32.35% | 3.92% | 43.00 |
| champion | odds_band | 25-50 | 67 | -36.00 | -53.73% | 1.49% | 61.00 |
| champion | odds_band | 3-6 | 7 | -7.00 | -100.00% | 0.00% | 7.00 |
| champion | odds_band | 6-12 | 50 | -8.00 | -16.00% | 10.00% | 27.00 |
| champion | predicted_edge | 10-20% | 42 | -3.50 | -8.33% | 9.52% | 12.50 |
| champion | predicted_edge | 20%+ | 2 | -2.00 | -100.00% | 0.00% | 2.00 |
| champion | predicted_edge | 5-10% | 182 | -78.50 | -43.13% | 3.30% | 114.00 |
| champion | confidence | High | 162 | -44.50 | -27.47% | 4.94% | 80.00 |
| champion | confidence | Low | 18 | 0.00 | 0.00% | 5.56% | 9.00 |
| champion | confidence | Medium | 46 | -39.50 | -85.87% | 2.17% | 39.50 |
| lightgbm | market_status | Favourite/TiedFavourite | 1 | 3.20 | 320.00% | 100.00% | 0.00 |
| lightgbm | market_status | NonFavourite | 224 | -107.80 | -48.12% | 3.57% | 107.80 |
| lightgbm | odds_band | 12-25 | 83 | -28.00 | -33.73% | 3.61% | 37.00 |
| lightgbm | odds_band | 25-50 | 70 | -39.00 | -55.71% | 1.43% | 51.00 |
| lightgbm | odds_band | 3-6 | 13 | 1.40 | 10.77% | 23.08% | 7.00 |
| lightgbm | odds_band | 6-12 | 59 | -39.00 | -66.10% | 3.39% | 50.00 |
| lightgbm | predicted_edge | 10-20% | 52 | -44.00 | -84.62% | 1.92% | 47.00 |
| lightgbm | predicted_edge | 20%+ | 6 | -6.00 | -100.00% | 0.00% | 6.00 |
| lightgbm | predicted_edge | 5-10% | 167 | -54.60 | -32.69% | 4.79% | 54.60 |
| lightgbm | confidence | High | 170 | -70.60 | -41.53% | 4.71% | 70.60 |
| lightgbm | confidence | Low | 15 | -15.00 | -100.00% | 0.00% | 15.00 |
| lightgbm | confidence | Medium | 40 | -19.00 | -47.50% | 2.50% | 30.00 |
| hybrid | market_status | NonFavourite | 199 | -100.50 | -50.50% | 3.52% | 122.50 |
| hybrid | odds_band | 12-25 | 82 | -48.00 | -58.54% | 2.44% | 48.00 |
| hybrid | odds_band | 25-50 | 61 | -30.00 | -49.18% | 1.64% | 54.00 |
| hybrid | odds_band | 3-6 | 6 | -6.00 | -100.00% | 0.00% | 6.00 |
| hybrid | odds_band | 6-12 | 50 | -16.50 | -33.00% | 8.00% | 29.00 |
| hybrid | predicted_edge | 10-20% | 30 | -18.00 | -60.00% | 3.33% | 24.00 |
| hybrid | predicted_edge | 20%+ | 4 | -4.00 | -100.00% | 0.00% | 4.00 |
| hybrid | predicted_edge | 5-10% | 165 | -78.50 | -47.58% | 3.64% | 100.50 |
| hybrid | confidence | High | 146 | -54.00 | -36.99% | 4.11% | 78.00 |
| hybrid | confidence | Low | 13 | -13.00 | -100.00% | 0.00% | 13.00 |
| hybrid | confidence | Medium | 40 | -33.50 | -83.75% | 2.50% | 33.50 |

## CLV

Current Matrix: **N/A**

ML: **N/A**

No timestamped opening/closing odds snapshots exist in the aligned archive.

## EXPLAINABILITY

Top permutation features for Place Brier:

- `leaf_pace_figure_score`: +0.005119
- `leaf_form_score`: +0.003734
- `leaf_rating_score`: +0.003358
- `field_size`: +0.001661
- `pf_l600_delta_avg`: +0.001292
- `barrier`: +0.001188
- `leaf_performance_quality_score`: +0.000951
- `leaf_trial_score`: +0.000758
- `trainer_ly_log_rides`: +0.000687
- `jockey_ly_place_rate`: +0.000656
- `trainer_ly_place_rate`: +0.000648
- `trainer_ly_win_rate`: +0.000496
- `jockey_ly_win_rate`: +0.000463
- `leaf_jockey_horse_fit_score`: +0.000452
- `days_since_last_run`: +0.000328
- `current_jockey_win_rate`: +0.000300
- `recent_finish_mean_3`: +0.000295
- `leaf_jockey_score`: +0.000204
- `same_track_place_rate`: +0.000180
- `pf_race_time_diff_avg`: +0.000176

Top TreeSHAP features for the selected Place model:

- `numeric__leaf_pace_figure_score`: 0.181881
- `numeric__leaf_rating_score`: 0.160955
- `numeric__leaf_form_score`: 0.119839
- `numeric__trainer_ly_log_rides`: 0.107719
- `numeric__field_size`: 0.101655
- `numeric__trainer_ly_place_rate`: 0.092504
- `numeric__barrier`: 0.084124
- `numeric__leaf_trial_score`: 0.083545
- `numeric__jockey_ly_place_rate`: 0.080596
- `numeric__leaf_trainer_score`: 0.072404
- `numeric__pf_l600_delta_avg`: 0.071354
- `numeric__recent_finish_mean_3`: 0.068556
- `numeric__trainer_ly_win_rate`: 0.060707
- `numeric__leaf_jockey_horse_fit_score`: 0.053359
- `numeric__jockey_ly_win_rate`: 0.052722
- `numeric__leaf_performance_quality_score`: 0.050743
- `numeric__leaf_pace_map_score`: 0.045560
- `numeric__leaf_class_score`: 0.041530
- `numeric__days_since_last_run`: 0.040434
- `categorical__race_type_Benchmark`: 0.039470

### Ten diagnostic questions

1. **Which features genuinely improve prediction?** Permutation and TreeSHAP agree that pace figure, official rating, recent form, trainer place performance and Performance Quality are the strongest reusable signals. This is predictive association on the holdout, not a causal claim.
2. **Which Matrix features remain strong?** `leaf_pace_figure_score`, `leaf_rating_score`, `leaf_form_score` and `leaf_performance_quality_score` all appear near the top, supporting the core Matrix design.
3. **Which are weak?** Features outside the leading permutation set, including heavily neutral report leaves, add little stable holdout value. Examples: sectional importance -0.000084, health +0.000038, confidence +0.000067.
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
| distance | Middle1500-1800 | 47 | 0.078674 | 0.081470 | 59.57% | 48.94% |
| distance | Sprint1200-1400 | 85 | 0.081663 | 0.082152 | 55.29% | 55.29% |
| distance | Sprint<=1100 | 49 | 0.090515 | 0.091416 | 51.02% | 46.94% |
| distance | Staying1900-2200 | 22 | 0.085340 | 0.086014 | 54.55% | 45.45% |
| distance | Staying2300+ | 7 | 0.090524 | 0.091190 | 71.43% | 57.14% |
| class | Benchmark | 65 | 0.079893 | 0.080071 | 50.77% | 49.23% |
| class | Handicap | 20 | 0.084004 | 0.081855 | 40.00% | 65.00% |
| class | Maiden | 22 | 0.085948 | 0.088364 | 59.09% | 59.09% |
| class | Other | 101 | 0.085638 | 0.087685 | 61.39% | 46.53% |
| race_type | Benchmark | 65 | 0.079893 | 0.080071 | 50.77% | 49.23% |
| race_type | Handicap | 20 | 0.084004 | 0.081855 | 40.00% | 65.00% |
| race_type | Maiden | 22 | 0.085948 | 0.088364 | 59.09% | 59.09% |
| race_type | Other | 101 | 0.085638 | 0.087685 | 61.39% | 46.53% |
| track_condition | Good/Firm | 40 | 0.091738 | 0.092405 | 55.00% | 47.50% |
| track_condition | Heavy | 38 | 0.082135 | 0.084549 | 50.00% | 55.26% |
| track_condition | Soft | 108 | 0.080624 | 0.081497 | 55.56% | 50.93% |
| track_condition | Synthetic | 24 | 0.087364 | 0.088471 | 66.67% | 50.00% |
| field_size | Large12+ | 121 | 0.074590 | 0.075091 | 51.24% | 47.93% |
| field_size | Medium8-11 | 79 | 0.097681 | 0.100606 | 59.49% | 53.16% |
| field_size | Small<=7 | 10 | 0.138079 | 0.133920 | 80.00% | 70.00% |
| confidence | High | 153 | 0.082970 | 0.084258 | 53.59% | 49.67% |
| confidence | Low | 14 | 0.088687 | 0.091011 | 50.00% | 57.14% |
| confidence | Medium | 43 | 0.083951 | 0.084152 | 65.12% | 53.49% |
| market_status | FavouriteWon | 81 | 0.080042 | 0.080279 | 80.25% | 70.37% |
| market_status | NonFavouriteWon | 129 | 0.085622 | 0.087300 | 40.31% | 38.76% |

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
| lightgbm | FAIL | FAIL | FAIL (1/5) | FAIL | FAIL | FAIL |
| hybrid | FAIL | FAIL | PASS (4/5) | FAIL | FAIL | FAIL |

- Candidate assessed: lightgbm
- Probability gate: FAIL
- Top-rank gate: FAIL
- Walk-forward consistency: 1/5 periods (FAIL)
- Paired bootstrap support: FAIL
- Betting not materially worse (5pp tolerance): FAIL

## FINAL VERDICT

**KEEP CURRENT MATRIX**

Neither the independent challenger nor the hybrid cleared every probability, ranking, walk-forward, statistical-support and betting-risk gate. Keep the deterministic Champion and preserve the ML pipeline/results as research.

Production Rating Matrix code was not changed by model training or betting results.
