# Calibration and Score-band Report

The fixed score bands are probability intervals, not retrospective grades. A useful band must show increasing observed strike rate and a small expected-versus-observed gap.

## Band definitions

- Win: A ≥15%, B 10–15%, C 6–10%, D <6%.
- Place: A ≥35%, B 25–35%, C 15–25%, D <15%.

## Results

| period | target | model | score_band | runners | mean_probability | observed_rate | calibration_gap |
|---|---|---|---|---|---|---|---|
| walk_forward | Win | Matrix Champion | A ≥15% | 189 | 0.1854 | 0.2434 | 0.0580 |
| walk_forward | Win | Matrix Champion | B 10–15% | 381 | 0.1218 | 0.1102 | -0.0115 |
| walk_forward | Win | Matrix Champion | C 6–10% | 600 | 0.0777 | 0.0817 | 0.0039 |
| walk_forward | Win | Matrix Champion | D <6% | 849 | 0.0388 | 0.0283 | -0.0105 |
| walk_forward | Win | Logistic Regression | A ≥15% | 254 | 0.1969 | 0.2165 | 0.0197 |
| walk_forward | Win | Logistic Regression | B 10–15% | 320 | 0.1229 | 0.1000 | -0.0229 |
| walk_forward | Win | Logistic Regression | C 6–10% | 478 | 0.0770 | 0.0858 | 0.0088 |
| walk_forward | Win | Logistic Regression | D <6% | 967 | 0.0361 | 0.0341 | -0.0020 |
| walk_forward | Place | Matrix Champion | A ≥35% | 480 | 0.4592 | 0.4188 | -0.0405 |
| walk_forward | Place | Matrix Champion | B 25–35% | 450 | 0.2973 | 0.2667 | -0.0307 |
| walk_forward | Place | Matrix Champion | C 15–25% | 612 | 0.1966 | 0.1879 | -0.0087 |
| walk_forward | Place | Matrix Champion | D <15% | 477 | 0.1117 | 0.0985 | -0.0132 |
| walk_forward | Place | Logistic Regression | A ≥35% | 472 | 0.4628 | 0.4343 | -0.0285 |
| walk_forward | Place | Logistic Regression | B 25–35% | 361 | 0.2940 | 0.3019 | 0.0079 |
| walk_forward | Place | Logistic Regression | C 15–25% | 534 | 0.1959 | 0.1854 | -0.0105 |
| walk_forward | Place | Logistic Regression | D <15% | 652 | 0.1021 | 0.1074 | 0.0053 |
| external_holdout | Win | Matrix Champion | A ≥15% | 13 | 0.1851 | 0.0769 | -0.1082 |
| external_holdout | Win | Matrix Champion | B 10–15% | 23 | 0.1197 | 0.1304 | 0.0108 |
| external_holdout | Win | Matrix Champion | C 6–10% | 27 | 0.0806 | 0.1481 | 0.0675 |
| external_holdout | Win | Matrix Champion | D <6% | 44 | 0.0378 | 0.0227 | -0.0151 |
| external_holdout | Win | Logistic Regression | A ≥15% | 15 | 0.2150 | 0.0667 | -0.1483 |
| external_holdout | Win | Logistic Regression | B 10–15% | 16 | 0.1188 | 0.1875 | 0.0687 |
| external_holdout | Win | Logistic Regression | C 6–10% | 28 | 0.0768 | 0.1071 | 0.0303 |
| external_holdout | Win | Logistic Regression | D <6% | 48 | 0.0359 | 0.0417 | 0.0058 |
| external_holdout | Place | Matrix Champion | A ≥35% | 31 | 0.4360 | 0.3871 | -0.0489 |
| external_holdout | Place | Matrix Champion | B 25–35% | 26 | 0.2988 | 0.1923 | -0.1065 |
| external_holdout | Place | Matrix Champion | C 15–25% | 25 | 0.1989 | 0.2000 | 0.0011 |
| external_holdout | Place | Matrix Champion | D <15% | 25 | 0.1129 | 0.2000 | 0.0871 |
| external_holdout | Place | Logistic Regression | A ≥35% | 22 | 0.4588 | 0.3182 | -0.1406 |
| external_holdout | Place | Logistic Regression | B 25–35% | 21 | 0.2947 | 0.3810 | 0.0863 |
| external_holdout | Place | Logistic Regression | C 15–25% | 33 | 0.2008 | 0.2121 | 0.0114 |
| external_holdout | Place | Logistic Regression | D <15% | 31 | 0.1003 | 0.1613 | 0.0610 |

A fixed ten-bin reliability curve for every evaluated period/target/model is published in `calibration_curve.csv`; ECE is included in the model scorecard.
