# Calibration and Score-band Report

The fixed score bands are probability intervals, not retrospective grades. A useful band must show increasing observed strike rate and a small expected-versus-observed gap.

## Band definitions

- Win: A ≥15%, B 10–15%, C 6–10%, D <6%.
- Place: A ≥35%, B 25–35%, C 15–25%, D <15%.

## Results

| period | target | model | score_band | runners | mean_probability | observed_rate | calibration_gap |
|---|---|---|---|---|---|---|---|
| walk_forward | Win | Matrix Champion | A ≥15% | 198 | 0.1856 | 0.2424 | 0.0568 |
| walk_forward | Win | Matrix Champion | B 10–15% | 364 | 0.1221 | 0.1154 | -0.0067 |
| walk_forward | Win | Matrix Champion | C 6–10% | 596 | 0.0780 | 0.0805 | 0.0026 |
| walk_forward | Win | Matrix Champion | D <6% | 861 | 0.0387 | 0.0267 | -0.0120 |
| walk_forward | Win | Logistic Regression | A ≥15% | 254 | 0.1969 | 0.2165 | 0.0197 |
| walk_forward | Win | Logistic Regression | B 10–15% | 320 | 0.1229 | 0.1000 | -0.0229 |
| walk_forward | Win | Logistic Regression | C 6–10% | 478 | 0.0770 | 0.0858 | 0.0088 |
| walk_forward | Win | Logistic Regression | D <6% | 967 | 0.0361 | 0.0341 | -0.0020 |
| walk_forward | Place | Matrix Champion | A ≥35% | 501 | 0.4639 | 0.4172 | -0.0468 |
| walk_forward | Place | Matrix Champion | B 25–35% | 441 | 0.2967 | 0.2653 | -0.0314 |
| walk_forward | Place | Matrix Champion | C 15–25% | 594 | 0.1958 | 0.1869 | -0.0090 |
| walk_forward | Place | Matrix Champion | D <15% | 483 | 0.1112 | 0.0952 | -0.0160 |
| walk_forward | Place | Logistic Regression | A ≥35% | 472 | 0.4628 | 0.4343 | -0.0285 |
| walk_forward | Place | Logistic Regression | B 25–35% | 361 | 0.2940 | 0.3019 | 0.0079 |
| walk_forward | Place | Logistic Regression | C 15–25% | 534 | 0.1959 | 0.1854 | -0.0105 |
| walk_forward | Place | Logistic Regression | D <15% | 652 | 0.1021 | 0.1074 | 0.0053 |
| external_holdout | Win | Matrix Champion | A ≥15% | 13 | 0.1855 | 0.0769 | -0.1086 |
| external_holdout | Win | Matrix Champion | B 10–15% | 22 | 0.1183 | 0.1364 | 0.0181 |
| external_holdout | Win | Matrix Champion | C 6–10% | 31 | 0.0789 | 0.1290 | 0.0501 |
| external_holdout | Win | Matrix Champion | D <6% | 41 | 0.0376 | 0.0244 | -0.0132 |
| external_holdout | Win | Logistic Regression | A ≥15% | 15 | 0.2150 | 0.0667 | -0.1483 |
| external_holdout | Win | Logistic Regression | B 10–15% | 16 | 0.1188 | 0.1875 | 0.0687 |
| external_holdout | Win | Logistic Regression | C 6–10% | 28 | 0.0768 | 0.1071 | 0.0303 |
| external_holdout | Win | Logistic Regression | D <6% | 48 | 0.0359 | 0.0417 | 0.0058 |
| external_holdout | Place | Matrix Champion | A ≥35% | 28 | 0.4450 | 0.3571 | -0.0879 |
| external_holdout | Place | Matrix Champion | B 25–35% | 31 | 0.2952 | 0.2581 | -0.0371 |
| external_holdout | Place | Matrix Champion | C 15–25% | 26 | 0.1912 | 0.2308 | 0.0396 |
| external_holdout | Place | Matrix Champion | D <15% | 22 | 0.1086 | 0.1364 | 0.0278 |
| external_holdout | Place | Logistic Regression | A ≥35% | 22 | 0.4588 | 0.3182 | -0.1406 |
| external_holdout | Place | Logistic Regression | B 25–35% | 21 | 0.2947 | 0.3810 | 0.0863 |
| external_holdout | Place | Logistic Regression | C 15–25% | 33 | 0.2008 | 0.2121 | 0.0114 |
| external_holdout | Place | Logistic Regression | D <15% | 31 | 0.1003 | 0.1613 | 0.0610 |

A fixed ten-bin reliability curve for every evaluated period/target/model is published in `calibration_curve.csv`; ECE is included in the model scorecard.
