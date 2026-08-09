# HKJC Iterative Feature Audit

- Coverage: 25 meetings / 245 races / 3054 runners
- Adjusted exclusions: 79
- Stable signals: last6_mean_finish, raw_last_finish, last6_top5_count, raw_last_margin, last6_top3_count, raw_finish_time_adj, last6_best_finish, card_rating_change, prior_jockey_cd_place_edge, raw_l400, prior_combo_place_edge, forensic_flag_balance, prior_weight_class_place_edge, finish_competitive, prior_rest_bucket_place_edge

| Signal | Stable | Coverage | Dev AUC | Holdout AUC | Adjusted AUC | Adjusted Top5 AUC | 07-15 AUC |
|---|:---:|---:|---:|---:|---:|---:|---:|
| last6_mean_finish | YES | 93.1% | 0.674 | 0.690 | 0.709 | 0.647 | 0.679 |
| raw_last_finish | YES | 69.4% | 0.629 | 0.662 | 0.670 | 0.583 | 0.625 |
| last6_top5_count | YES | 100.0% | 0.642 | 0.662 | 0.669 | 0.619 | 0.666 |
| raw_last_margin | YES | 60.5% | 0.610 | 0.644 | 0.658 | 0.578 | 0.664 |
| last6_top3_count | YES | 100.0% | 0.634 | 0.650 | 0.658 | 0.615 | 0.635 |
| raw_finish_time_adj | YES | 62.1% | 0.628 | 0.650 | 0.657 | 0.579 | 0.602 |
| last6_best_finish | YES | 93.1% | 0.620 | 0.632 | 0.638 | 0.566 | 0.592 |
| card_rating_change | YES | 90.6% | 0.622 | 0.635 | 0.631 | 0.604 | 0.000 |
| prior_jockey_cd_place_edge | YES | 52.0% | 0.577 | 0.557 | 0.612 | 0.601 | 0.000 |
| raw_l400 | YES | 84.8% | 0.566 | 0.607 | 0.583 | 0.551 | 0.589 |
| prior_combo_place_edge | YES | 50.4% | 0.564 | 0.593 | 0.583 | 0.584 | 0.000 |
| forensic_flag_balance | YES | 100.0% | 0.551 | 0.561 | 0.571 | 0.528 | 0.494 |
| prior_weight_class_place_edge | YES | 54.5% | 0.543 | 0.527 | 0.561 | 0.612 | 0.000 |
| finish_competitive | YES | 100.0% | 0.527 | 0.558 | 0.545 | 0.542 | 0.471 |
| prior_rest_bucket_place_edge | YES | 56.5% | 0.526 | 0.537 | 0.542 | 0.562 | 0.000 |
| prior_draw_class_place_edge | NO | 59.1% | 0.559 | 0.464 | 0.571 | 0.528 | 0.000 |
| prior_horse_style_place_edge | NO | 22.4% | 0.513 | 0.595 | 0.562 | 0.587 | 0.000 |
| prior_horse_cd_place_edge | NO | 24.0% | 0.535 | 0.476 | 0.553 | 0.592 | 0.000 |
| prior_trainer_cd_place_edge | NO | 56.1% | 0.542 | 0.487 | 0.544 | 0.548 | 0.000 |
| starts | NO | 88.3% | 0.527 | 0.543 | 0.544 | 0.472 | 0.563 |
| prior_runstyle_cd_place_edge | NO | 48.0% | 0.526 | 0.491 | 0.537 | 0.545 | 0.000 |
| prior_horse_rest_place_edge | NO | 28.3% | 0.512 | 0.468 | 0.532 | 0.531 | 0.000 |
| career_win_rate_shrunk | NO | 84.7% | 0.510 | 0.518 | 0.531 | 0.510 | 0.449 |
| card_rating | NO | 95.0% | 0.519 | 0.525 | 0.524 | 0.547 | 0.000 |
| margin_narrowing | NO | 100.0% | 0.511 | 0.498 | 0.518 | 0.487 | 0.477 |
| progressive | NO | 100.0% | 0.510 | 0.531 | 0.518 | 0.494 | 0.545 |
| trackwork_entries | NO | 77.0% | 0.538 | 0.506 | 0.510 | 0.492 | 0.498 |
| medical_issue_inverse | NO | 100.0% | 0.506 | 0.510 | 0.504 | 0.497 | 0.452 |
| hidden_form | NO | 100.0% | 0.501 | 0.500 | 0.499 | 0.496 | 0.500 |
| forgiveness | NO | 100.0% | 0.498 | 0.500 | 0.499 | 0.514 | 0.500 |
| trackwork_jockey_present | NO | 100.0% | 0.500 | 0.499 | 0.498 | 0.492 | 0.500 |
| trackwork_gallops | NO | 77.0% | 0.522 | 0.484 | 0.497 | 0.526 | 0.448 |
| season_place_rate_k8 | NO | 32.2% | 0.435 | 0.455 | 0.441 | 0.456 | 0.498 |
| same_distance_place_rate_k6 | NO | 22.6% | 0.430 | 0.455 | 0.426 | 0.362 | 0.510 |
| same_venue_distance_place_rate_k6 | NO | 14.4% | 0.425 | 0.494 | 0.417 | 0.353 | 0.562 |
| prior_class_distance_place_edge | NO | 0.0% | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
