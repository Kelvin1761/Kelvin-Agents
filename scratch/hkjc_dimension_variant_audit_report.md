# HKJC Dimension Variant Audit

- Coverage: 25 meetings / 245 races / 3054 runners
- Primary target: leading-third competitive tier（最少3、最多5匹）

| Family | Variant | Dev AUC | Temporal AUC | Recent AUC | 07-15 AUC | Archive AUC |
|---|---|---:|---:|---:|---:|---:|
| class | class_current_rebuilt | 0.530 | 0.538 | 0.546 | 0.544 | 0.539 |
| class | class_rating_only | 0.536 | 0.552 | 0.547 | 0.557 | 0.544 |
| class | class_lower_weight_only | 0.469 | 0.421 | 0.455 | 0.405 | 0.455 |
| class | class_rating_weight_50_50 | 0.484 | 0.440 | 0.503 | 0.402 | 0.486 |
| class | class_rating_weight_75_25 | 0.531 | 0.537 | 0.545 | 0.543 | 0.539 |
| class | class_effective_rating_minus_weight | 0.482 | 0.448 | 0.470 | 0.371 | 0.471 |
| class | class_rating_experience | 0.539 | 0.555 | 0.555 | 0.555 | 0.549 |
| class | class_rating_season_place | 0.532 | 0.542 | 0.544 | 0.565 | 0.539 |
| trainer | trainer_current_rebuilt | 0.575 | 0.582 | 0.597 | 0.649 | 0.586 |
| trainer | trainer_absolute_stack | 0.572 | 0.584 | 0.602 | 0.644 | 0.588 |
| trainer | trainer_combo_only | 0.574 | 0.542 | 0.597 | 0.682 | 0.580 |
| trainer | trainer_edge_stack | 0.572 | 0.584 | 0.602 | 0.644 | 0.588 |
| formline | formline_current_rebuilt | 0.498 | 0.515 | 0.509 | 0.562 | 0.506 |
| formline | formline_weighted_relative | 0.486 | 0.481 | 0.480 | 0.572 | 0.483 |
| formline | formline_positive_relative | 0.483 | 0.481 | 0.476 | 0.579 | 0.480 |
| formline | formline_higher_relative | 0.473 | 0.480 | 0.474 | 0.541 | 0.475 |

Development-selected variants:
- class: `class_rating_experience`
- trainer: `trainer_current_rebuilt`
- formline: `formline_current_rebuilt`
