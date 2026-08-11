# Final HKJC ML Report

## Executive result

- Readiness: **READY WITH LIMITATIONS**.
- Production decision: **DO NOT PROMOTE**.
- Selected feature group: **matrix_7d**.
- Best standalone ML: **Logistic Regression**.
- Best overall evaluated ranking: **Matrix Champion**.
- Betting layer: **N/A — complete timestamped odds are unavailable**.

## Analysis-layer scorecard

| period | target | model | feature_group | rows | races | log_loss | brier | ece_10 | winner_top1 | winner_top2 | winner_top3 | winner_average_rank | placegetter_average_rank | ranking_correlation | top3_capture_at3 | top3_capture_at5 | ndcg_at5 | top2_zero_hit | top2_one_hit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| walk_forward | Win | Matrix Champion | frozen_matrix | 2019.0000 | 161.0000 | 0.2554 | 0.0695 | 0.0090 | 0.2484 | 0.4161 | 0.5342 | 4.2050 | 4.8944 | 0.3494 | 0.4451 | 0.6294 | 0.5312 | 0.2547 | 0.5217 |
| external_holdout | Win | Matrix Champion | frozen_matrix | 107.0000 | 9.0000 | 0.2872 | 0.0770 | 0.0189 | 0.1111 | 0.1111 | 0.3333 | 4.7778 | 5.4444 | 0.2500 | 0.3704 | 0.6296 | 0.4868 | 0.5556 | 0.3333 |
| walk_forward | Win | Logistic Regression | matrix_7d | 2019.0000 | 161.0000 | 0.2549 | 0.0696 | 0.0050 | 0.2422 | 0.4037 | 0.5280 | 4.2671 | 4.9213 | 0.3508 | 0.4410 | 0.6273 | 0.5265 | 0.2795 | 0.5093 |
| external_holdout | Win | Logistic Regression | matrix_7d | 107.0000 | 9.0000 | 0.2941 | 0.0784 | 0.0210 | 0.1111 | 0.2222 | 0.4444 | 5.1111 | 5.3333 | 0.2870 | 0.4074 | 0.5185 | 0.4133 | 0.4444 | 0.3333 |
| walk_forward | Win | LightGBM | matrix_7d | 2019.0000 | 161.0000 | 0.2585 | 0.0700 | 0.0074 | 0.2236 | 0.3789 | 0.5155 | 4.4410 | 4.9379 | 0.3384 | 0.4161 | 0.6190 | 0.5100 | 0.2981 | 0.4969 |
| external_holdout | Win | LightGBM | matrix_7d | 107.0000 | 9.0000 | 0.2913 | 0.0785 | 0.0325 | 0.1111 | 0.2222 | 0.2222 | 4.6667 | 5.3704 | 0.2855 | 0.3333 | 0.5556 | 0.4171 | 0.3333 | 0.5556 |
| walk_forward | Win | XGBoost | matrix_7d | 2019.0000 | 161.0000 | 0.2731 | 0.0726 | 0.0052 | 0.1677 | 0.2547 | 0.3602 | 5.4720 | 5.6294 | 0.3383 | 0.3375 | 0.5611 | 0.4298 | 0.3913 | 0.4720 |
| external_holdout | Win | XGBoost | matrix_7d | 107.0000 | 9.0000 | 0.2866 | 0.0767 | 0.0030 | 0.2222 | 0.3333 | 0.3333 | 5.0000 | 5.2963 | 0.3367 | 0.3333 | 0.5556 | 0.4720 | 0.2222 | 0.5556 |
| walk_forward | Place | Matrix Champion | frozen_matrix | 2019.0000 | 161.0000 | 0.5118 | 0.1682 | 0.0249 | 0.2484 | 0.4161 | 0.5342 | 4.2050 | 4.8944 | 0.3494 | 0.4451 | 0.6294 | 0.5312 | 0.2547 | 0.5217 |
| external_holdout | Place | Matrix Champion | frozen_matrix | 107.0000 | 9.0000 | 0.5612 | 0.1871 | 0.0649 | 0.1111 | 0.1111 | 0.3333 | 4.7778 | 5.4444 | 0.2500 | 0.3704 | 0.6296 | 0.4868 | 0.5556 | 0.3333 |
| walk_forward | Place | Logistic Regression | matrix_7d | 2019.0000 | 161.0000 | 0.5028 | 0.1648 | 0.0088 | 0.2174 | 0.3789 | 0.5155 | 4.2919 | 4.8820 | 0.3679 | 0.4369 | 0.6356 | 0.5245 | 0.2671 | 0.5280 |
| external_holdout | Place | Logistic Regression | matrix_7d | 107.0000 | 9.0000 | 0.5608 | 0.1871 | 0.0382 | 0.1111 | 0.2222 | 0.3333 | 5.1111 | 5.3333 | 0.3108 | 0.3704 | 0.5926 | 0.4435 | 0.4444 | 0.3333 |
| walk_forward | Place | LightGBM | matrix_7d | 2019.0000 | 161.0000 | 0.5051 | 0.1655 | 0.0111 | 0.2422 | 0.3975 | 0.5093 | 4.3789 | 4.9503 | 0.3462 | 0.4058 | 0.6211 | 0.5146 | 0.2857 | 0.5217 |
| external_holdout | Place | LightGBM | matrix_7d | 107.0000 | 9.0000 | 0.5528 | 0.1841 | 0.0766 | 0.1111 | 0.2222 | 0.2222 | 5.2222 | 5.3333 | 0.3262 | 0.3704 | 0.5556 | 0.4097 | 0.4444 | 0.4444 |
| walk_forward | Place | XGBoost | matrix_7d | 2019.0000 | 161.0000 | 0.5178 | 0.1701 | 0.0208 | 0.1863 | 0.3354 | 0.4845 | 4.9379 | 5.3768 | 0.3247 | 0.3872 | 0.5673 | 0.4636 | 0.3354 | 0.5031 |
| external_holdout | Place | XGBoost | matrix_7d | 107.0000 | 9.0000 | 0.5564 | 0.1850 | 0.0496 | 0.1111 | 0.2222 | 0.2222 | 5.6667 | 5.6667 | 0.2742 | 0.2963 | 0.5556 | 0.4114 | 0.4444 | 0.4444 |
| walk_forward | Win | Matrix+Logistic Regression α=0.25 | hybrid | 2019.0000 | 161.0000 | 0.2547 | 0.0695 | 0.0014 | 0.2484 | 0.4286 | 0.5280 | 4.2547 | 4.9234 | 0.3503 | 0.4389 | 0.6253 | 0.5275 | 0.2484 | 0.5280 |
| external_holdout | Win | Matrix+Logistic Regression α=0.25 | hybrid | 107.0000 | 9.0000 | 0.2917 | 0.0780 | 0.0170 | 0.1111 | 0.2222 | 0.4444 | 5.0000 | 5.3333 | 0.2897 | 0.4074 | 0.5556 | 0.4314 | 0.4444 | 0.3333 |
| walk_forward | Place | Matrix+Logistic Regression α=0.75 | hybrid | 2019.0000 | 161.0000 | 0.5079 | 0.1667 | 0.0203 | 0.2484 | 0.4286 | 0.5404 | 4.1677 | 4.8654 | 0.3574 | 0.4493 | 0.6232 | 0.5328 | 0.2422 | 0.4969 |
| external_holdout | Place | Matrix+Logistic Regression α=0.75 | hybrid | 107.0000 | 9.0000 | 0.5588 | 0.1862 | 0.0708 | 0.1111 | 0.1111 | 0.5556 | 4.5556 | 5.2593 | 0.2765 | 0.4815 | 0.5926 | 0.4594 | 0.5556 | 0.3333 |

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

## What changed

1. Meeting-folder venue now overrides stale per-race venue text.
2. AWT is separated from venue and represented as track/course.
3. Actual matched starters define field size and HKJC Place cutoff.
4. Incomplete result joins are hard-excluded from training.
5. Historical replay always receives its race date, enforcing PIT prior guards.
6. Score bands are calibrated probability intervals with observed strike rates.

## Decision discipline

No model is promoted because it fits history. Promotion requires consistent probability, ranking, calibration, segment, and external-block evidence. See `promotion_recommendation.md` for the binding gate.

The exact requested result layout is published in `final_hkjc_scorecard.md`; the complete experiment narrative is `hkjc_ml_experiment_report.md`.
