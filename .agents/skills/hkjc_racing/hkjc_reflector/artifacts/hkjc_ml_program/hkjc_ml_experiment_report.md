# HKJC ML Experiment Report

## Question and answer

**Does proper ML independently analyse HKJC races better than the production Matrix?** No. Logistic Regression is the best standalone challenger, but Matrix Champion remains the best overall ranking and no candidate passed the production gate.

## Reproducibility identity

- Dataset manifest: `276a4ac2de6c6ace808f4b50aa06d80d7a843ed7175c6714953eda69eaf2ba9c`.
- Research freeze commit: `39155166df7fdba5162b19aa872e6fe004b7f3c3`.
- Seed: `20260811`.
- Dataset: 250 valid races / 3109 runners, 2026-04-12–2026-07-15.
- Selected feature group: `matrix_7d`.
- Production changed: **No**.

## Architecture

The analysis layer uses racing information only to produce Win/Place probabilities, ranking and confidence. Odds are introduced only in the separate betting layer; that layer is N/A because fixed-time prices and complete settlement data are unavailable.

## Models and fixed conservative hyperparameters

| model | hyperparameters |
|---|---|
| Logistic Regression | {"C": 0.25, "class_weight": null, "dual": false, "fit_intercept": true, "intercept_scaling": 1, "l1_ratio": null, "max_iter": 1500, "multi_class": "deprecated", "n_jobs": null, "penalty": "l2", "random_state": 20260811, "solver": "lbfgs", "tol": 0.0001, "verbose": 0, "warm_start": false} |
| LightGBM | {"boosting_type": "gbdt", "class_weight": null, "colsample_bytree": 0.8, "importance_type": "split", "learning_rate": 0.03, "max_depth": 3, "min_child_samples": 35, "min_child_weight": 0.001, "min_split_gain": 0.0, "n_estimators": 140, "n_jobs": 1, "num_leaves": 7, "objective": null, "random_state": 20260811, "reg_alpha": 0.6, "reg_lambda": 2.5, "subsample": 0.8, "subsample_for_bin": 200000, "subsample_freq": 0, "verbosity": -1} |
| XGBoost | {"base_score": null, "booster": null, "callbacks": null, "colsample_bylevel": null, "colsample_bynode": null, "colsample_bytree": 0.8, "device": null, "early_stopping_rounds": null, "enable_categorical": false, "eval_metric": "logloss", "feature_types": null, "gamma": null, "grow_policy": null, "importance_type": null, "interaction_constraints": null, "learning_rate": 0.03, "max_bin": null, "max_cat_threshold": null, "max_cat_to_onehot": null, "max_delta_step": null, "max_depth": 3, "max_leaves": null, "min_child_weight": 8, "missing": NaN, "monotone_constraints": null, "multi_strategy": null, "n_estimators": 160, "n_jobs": 1, "num_parallel_tree": null, "objective": "binary:logistic", "random_state": 20260811, "reg_alpha": 0.6, "reg_lambda": 3.0, "sampling_method": null, "scale_pos_weight": null, "subsample": 0.8, "tree_method": null, "validate_parameters": null, "verbosity": null} |

No broad hyperparameter search, random row split, deep learning, odds feature or holdout-driven tuning was used.

## Chronological validation

- Development dates: 2026-04-12 to 2026-07-12.
- Expanding walk-forward starts after 8 meetings and predicts each next meeting as a whole race block.
- External block: 2026-07-15, nine races; ML-unseen in this program but previously inspected by Matrix research.
- Fold-local imputation, scaling and Matrix probability calibration prevent future-fold leakage.

## Feature-group experiment

| target | feature_group | races | log_loss | brier | winner_top3 | top3_capture_at5 | ndcg_at5 | selected |
|---|---|---|---|---|---|---|---|---|
| Win | matrix_7d | 161.0000 | 0.2549 | 0.0696 | 0.5280 | 0.6273 | 0.5265 | True |
| Place | matrix_7d | 161.0000 | 0.5028 | 0.1648 | 0.5155 | 0.6356 | 0.5245 | True |
| Win | facts_compact | 161.0000 | 0.2714 | 0.0724 | 0.4099 | 0.5839 | 0.4687 | False |
| Place | facts_compact | 161.0000 | 0.5152 | 0.1695 | 0.4099 | 0.5983 | 0.4702 | False |
| Win | matrix_plus_facts | 161.0000 | 0.2617 | 0.0708 | 0.5155 | 0.6149 | 0.5152 | False |
| Place | matrix_plus_facts | 161.0000 | 0.5079 | 0.1667 | 0.4783 | 0.6398 | 0.5224 | False |

## Matrix vs ML vs hybrid scorecard

| period | target | model | races | rows | brier | log_loss | winner_top1 | winner_top2 | winner_top3 | winner_average_rank | placegetter_average_rank | ranking_correlation | top3_capture_at5 | ndcg_at5 | ece_10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| walk_forward | Win | Matrix Champion | 161.0000 | 2019.0000 | 0.0695 | 0.2554 | 0.2484 | 0.4161 | 0.5342 | 4.2050 | 4.8944 | 0.3494 | 0.6294 | 0.5312 | 0.0090 |
| external_holdout | Win | Matrix Champion | 9.0000 | 107.0000 | 0.0770 | 0.2872 | 0.1111 | 0.1111 | 0.3333 | 4.7778 | 5.4444 | 0.2500 | 0.6296 | 0.4868 | 0.0189 |
| walk_forward | Win | Logistic Regression | 161.0000 | 2019.0000 | 0.0696 | 0.2549 | 0.2422 | 0.4037 | 0.5280 | 4.2671 | 4.9213 | 0.3508 | 0.6273 | 0.5265 | 0.0050 |
| external_holdout | Win | Logistic Regression | 9.0000 | 107.0000 | 0.0784 | 0.2941 | 0.1111 | 0.2222 | 0.4444 | 5.1111 | 5.3333 | 0.2870 | 0.5185 | 0.4133 | 0.0210 |
| walk_forward | Win | LightGBM | 161.0000 | 2019.0000 | 0.0700 | 0.2585 | 0.2236 | 0.3789 | 0.5155 | 4.4410 | 4.9379 | 0.3384 | 0.6190 | 0.5100 | 0.0074 |
| external_holdout | Win | LightGBM | 9.0000 | 107.0000 | 0.0785 | 0.2913 | 0.1111 | 0.2222 | 0.2222 | 4.6667 | 5.3704 | 0.2855 | 0.5556 | 0.4171 | 0.0325 |
| walk_forward | Win | XGBoost | 161.0000 | 2019.0000 | 0.0726 | 0.2731 | 0.1677 | 0.2547 | 0.3602 | 5.4720 | 5.6294 | 0.3383 | 0.5611 | 0.4298 | 0.0052 |
| external_holdout | Win | XGBoost | 9.0000 | 107.0000 | 0.0767 | 0.2866 | 0.2222 | 0.3333 | 0.3333 | 5.0000 | 5.2963 | 0.3367 | 0.5556 | 0.4720 | 0.0030 |
| walk_forward | Place | Matrix Champion | 161.0000 | 2019.0000 | 0.1682 | 0.5118 | 0.2484 | 0.4161 | 0.5342 | 4.2050 | 4.8944 | 0.3494 | 0.6294 | 0.5312 | 0.0249 |
| external_holdout | Place | Matrix Champion | 9.0000 | 107.0000 | 0.1871 | 0.5612 | 0.1111 | 0.1111 | 0.3333 | 4.7778 | 5.4444 | 0.2500 | 0.6296 | 0.4868 | 0.0649 |
| walk_forward | Place | Logistic Regression | 161.0000 | 2019.0000 | 0.1648 | 0.5028 | 0.2174 | 0.3789 | 0.5155 | 4.2919 | 4.8820 | 0.3679 | 0.6356 | 0.5245 | 0.0088 |
| external_holdout | Place | Logistic Regression | 9.0000 | 107.0000 | 0.1871 | 0.5608 | 0.1111 | 0.2222 | 0.3333 | 5.1111 | 5.3333 | 0.3108 | 0.5926 | 0.4435 | 0.0382 |
| walk_forward | Place | LightGBM | 161.0000 | 2019.0000 | 0.1655 | 0.5051 | 0.2422 | 0.3975 | 0.5093 | 4.3789 | 4.9503 | 0.3462 | 0.6211 | 0.5146 | 0.0111 |
| external_holdout | Place | LightGBM | 9.0000 | 107.0000 | 0.1841 | 0.5528 | 0.1111 | 0.2222 | 0.2222 | 5.2222 | 5.3333 | 0.3262 | 0.5556 | 0.4097 | 0.0766 |
| walk_forward | Place | XGBoost | 161.0000 | 2019.0000 | 0.1701 | 0.5178 | 0.1863 | 0.3354 | 0.4845 | 4.9379 | 5.3768 | 0.3247 | 0.5673 | 0.4636 | 0.0208 |
| external_holdout | Place | XGBoost | 9.0000 | 107.0000 | 0.1850 | 0.5564 | 0.1111 | 0.2222 | 0.2222 | 5.6667 | 5.6667 | 0.2742 | 0.5556 | 0.4114 | 0.0496 |
| walk_forward | Win | Matrix+Logistic Regression α=0.25 | 161.0000 | 2019.0000 | 0.0695 | 0.2547 | 0.2484 | 0.4286 | 0.5280 | 4.2547 | 4.9234 | 0.3503 | 0.6253 | 0.5275 | 0.0014 |
| external_holdout | Win | Matrix+Logistic Regression α=0.25 | 9.0000 | 107.0000 | 0.0780 | 0.2917 | 0.1111 | 0.2222 | 0.4444 | 5.0000 | 5.3333 | 0.2897 | 0.5556 | 0.4314 | 0.0170 |
| walk_forward | Place | Matrix+Logistic Regression α=0.75 | 161.0000 | 2019.0000 | 0.1667 | 0.5079 | 0.2484 | 0.4286 | 0.5404 | 4.1677 | 4.8654 | 0.3574 | 0.6232 | 0.5328 | 0.0203 |
| external_holdout | Place | Matrix+Logistic Regression α=0.75 | 9.0000 | 107.0000 | 0.1862 | 0.5588 | 0.1111 | 0.1111 | 0.5556 | 4.5556 | 5.2593 | 0.2765 | 0.5926 | 0.4594 | 0.0708 |

## Learning curve

| target | model | train_races | validation_races | log_loss | brier | winner_top3 | top3_capture_at5 |
|---|---|---|---|---|---|---|---|
| Win | Logistic Regression | 50 | 53 | 0.2478 | 0.0679 | 0.5472 | 0.6352 |
| Place | Logistic Regression | 50 | 53 | 0.4925 | 0.1611 | 0.5283 | 0.6415 |
| Win | Logistic Regression | 100 | 53 | 0.2464 | 0.0677 | 0.5472 | 0.6289 |
| Place | Logistic Regression | 100 | 53 | 0.4892 | 0.1602 | 0.5283 | 0.6541 |
| Win | Logistic Regression | 150 | 53 | 0.2472 | 0.0679 | 0.5283 | 0.6415 |
| Place | Logistic Regression | 150 | 53 | 0.4864 | 0.1593 | 0.5283 | 0.6478 |
| Win | Logistic Regression | 188 | 53 | 0.2470 | 0.0679 | 0.5472 | 0.6289 |
| Place | Logistic Regression | 188 | 53 | 0.4862 | 0.1592 | 0.5283 | 0.6541 |

Available pre-validation training history peaks at 188 races; requested 250/500/750/1000/1500 points do not exist and are not extrapolated.

## Hybrid and Top-2 overlay

The probability hybrid was selected on walk-forward only. The strongest rank-overlay candidate was:

| period | model | matrix_weight | winner_top3 | top3_capture_at5 | top2_zero_hit | ndcg_at5 |
|---|---|---|---|---|---|---|
| walk_forward | Matrix+Place ML rank overlay | 0.5500 | 0.5404 | 0.6273 | 0.2484 | 0.5318 |

It was rejected because its external contender capture regressed. No blind swap or micro tie-break was promoted.

## Calibration, segments and explainability

- Fixed Win/Place probability buckets and observed rates: `calibration_report.md`.
- Venue, surface, course, distance, class, field-size and model-confidence segments: `segment_analysis.csv`.
- Coefficients/model importance, race-preserving permutation, SHAP and tree interactions: `explainability_diagnosis.md` and companion CSVs.
- Going/rail segmentation is N/A because no aligned pre-race fields exist.

## Failure analysis

`failure_review.md` reviews every Matrix and best-ML 0/1-hit race, separates normal outcomes from outsider/incident/injury/abnormal annotations, and prevents single-race hindsight changes.

## Betting result

ROI, turnover, drawdown, losing streak and CLV are all N/A. The archive lacks complete timestamped Win/Place odds, official dividend and settlement snapshots. This does not block the independent analysis conclusion, but it prevents the secondary betting-strategy question from being answered honestly.

## Conclusion

Decision: **KEEP CURRENT MATRIX**. Research artifacts and failed candidates remain reproducible. The next valid test is genuinely unseen local HKJC racing plus fixed-time odds capture, with all thresholds frozen before results arrive.
