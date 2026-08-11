# HKJC Competitiveness Model Card

## Intended use

Rank HKJC runners by pre-race competitiveness. It is not a betting instruction and does not ingest odds.

## Data

250 valid races / 3109 runners from 2026-04-12 to 2026-07-15. The final ML-unseen block is 2026-07-15 (nine races), with the historical-contamination caveat documented in the readiness report.

## Models

- Frozen Matrix Champion with fold-local probability calibration.
- Regularised Logistic Regression.
- Shallow LightGBM.
- Shallow XGBoost.
- Matrix+ML convex hybrid selected only on walk-forward predictions.

## Scorecard

| period | target | model | feature_group | races | log_loss | brier | ece_10 | winner_top1 | winner_top3 | top3_capture_at3 | top3_capture_at5 | ndcg_at5 | top2_zero_hit | top2_one_hit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| walk_forward | Win | Matrix Champion | frozen_matrix | 161.0000 | 0.2560 | 0.0696 | 0.0068 | 0.2547 | 0.5342 | 0.4451 | 0.6273 | 0.5279 | 0.2609 | 0.5342 |
| external_holdout | Win | Matrix Champion | frozen_matrix | 9.0000 | 0.2866 | 0.0769 | 0.0217 | 0.1111 | 0.4444 | 0.4074 | 0.6296 | 0.4886 | 0.5556 | 0.3333 |
| walk_forward | Win | Logistic Regression | matrix_7d | 161.0000 | 0.2549 | 0.0696 | 0.0050 | 0.2422 | 0.5280 | 0.4410 | 0.6273 | 0.5265 | 0.2795 | 0.5093 |
| external_holdout | Win | Logistic Regression | matrix_7d | 9.0000 | 0.2941 | 0.0784 | 0.0210 | 0.1111 | 0.4444 | 0.4074 | 0.5185 | 0.4133 | 0.4444 | 0.3333 |
| walk_forward | Win | LightGBM | matrix_7d | 161.0000 | 0.2585 | 0.0700 | 0.0074 | 0.2236 | 0.5155 | 0.4161 | 0.6190 | 0.5100 | 0.2981 | 0.4969 |
| external_holdout | Win | LightGBM | matrix_7d | 9.0000 | 0.2913 | 0.0785 | 0.0325 | 0.1111 | 0.2222 | 0.3333 | 0.5556 | 0.4171 | 0.3333 | 0.5556 |
| walk_forward | Win | XGBoost | matrix_7d | 161.0000 | 0.2731 | 0.0726 | 0.0052 | 0.1677 | 0.3602 | 0.3375 | 0.5611 | 0.4298 | 0.3913 | 0.4720 |
| external_holdout | Win | XGBoost | matrix_7d | 9.0000 | 0.2866 | 0.0767 | 0.0030 | 0.2222 | 0.3333 | 0.3333 | 0.5556 | 0.4720 | 0.2222 | 0.5556 |
| walk_forward | Place | Matrix Champion | frozen_matrix | 161.0000 | 0.5136 | 0.1687 | 0.0222 | 0.2547 | 0.5342 | 0.4451 | 0.6273 | 0.5279 | 0.2609 | 0.5342 |
| external_holdout | Place | Matrix Champion | frozen_matrix | 9.0000 | 0.5634 | 0.1876 | 0.0577 | 0.1111 | 0.4444 | 0.4074 | 0.6296 | 0.4886 | 0.5556 | 0.3333 |
| walk_forward | Place | Logistic Regression | matrix_7d | 161.0000 | 0.5028 | 0.1648 | 0.0088 | 0.2174 | 0.5155 | 0.4369 | 0.6356 | 0.5245 | 0.2671 | 0.5280 |
| external_holdout | Place | Logistic Regression | matrix_7d | 9.0000 | 0.5608 | 0.1871 | 0.0382 | 0.1111 | 0.3333 | 0.3704 | 0.5926 | 0.4435 | 0.4444 | 0.3333 |
| walk_forward | Place | LightGBM | matrix_7d | 161.0000 | 0.5051 | 0.1655 | 0.0111 | 0.2422 | 0.5093 | 0.4058 | 0.6211 | 0.5146 | 0.2857 | 0.5217 |
| external_holdout | Place | LightGBM | matrix_7d | 9.0000 | 0.5528 | 0.1841 | 0.0766 | 0.1111 | 0.2222 | 0.3704 | 0.5556 | 0.4097 | 0.4444 | 0.4444 |
| walk_forward | Place | XGBoost | matrix_7d | 161.0000 | 0.5178 | 0.1701 | 0.0208 | 0.1863 | 0.4845 | 0.3872 | 0.5673 | 0.4636 | 0.3354 | 0.5031 |
| external_holdout | Place | XGBoost | matrix_7d | 9.0000 | 0.5564 | 0.1850 | 0.0496 | 0.1111 | 0.2222 | 0.2963 | 0.5556 | 0.4114 | 0.4444 | 0.4444 |
| walk_forward | Win | Matrix+Logistic Regression α=0.25 | hybrid | 161.0000 | 0.2547 | 0.0695 | 0.0018 | 0.2484 | 0.5280 | 0.4389 | 0.6211 | 0.5241 | 0.2671 | 0.5031 |
| external_holdout | Win | Matrix+Logistic Regression α=0.25 | hybrid | 9.0000 | 0.2914 | 0.0779 | 0.0169 | 0.1111 | 0.4444 | 0.4074 | 0.5556 | 0.4314 | 0.4444 | 0.3333 |
| walk_forward | Place | Matrix+Logistic Regression α=0.75 | hybrid | 161.0000 | 0.5091 | 0.1670 | 0.0191 | 0.2422 | 0.5342 | 0.4493 | 0.6294 | 0.5331 | 0.2484 | 0.5031 |
| external_holdout | Place | Matrix+Logistic Regression α=0.75 | hybrid | 9.0000 | 0.5601 | 0.1864 | 0.0640 | 0.1111 | 0.3333 | 0.4074 | 0.5926 | 0.4513 | 0.5556 | 0.3333 |

## Known limitations

- Small race-level sample, particularly AWT and rare class segments.
- Archive has been used in earlier Matrix design cycles.
- No complete odds/CLV dataset.
- Probabilities should be refreshed and re-audited when a new HK season supplies genuinely unseen races.
- Race-cluster bootstrap intervals are supplied in `metric_uncertainty.csv`; the nine-race external interval is necessarily wide.

## Runtime

- python: 3.9.6
- numpy: 2.0.2
- pandas: 2.3.3
- scikit-learn: 1.6.1
- lightgbm: 4.6.0
- xgboost: 2.1.4
