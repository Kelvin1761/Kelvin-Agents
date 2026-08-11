# HKJC ML Program Requirements Audit

| # | Required deliverable | Evidence | Status |
|---:|---|---|---|
| 1 | `hkjc_ml_readiness_report.md` | 250 valid races; READY WITH LIMITATIONS verdict and constraints | Complete |
| 2 | cleaned training dataset | `training_dataset_clean.csv`, 3,109 runners | Complete |
| 3 | `data_quality_tests.json` | duplicate, labels, finish uniqueness, temporal order, Place cutoff tests | Complete |
| 4 | `point_in_time_leakage_test.md` | feature blacklist, fold-local preprocessing, historical prior guard | Complete |
| 5 | `dataset_manifest.json` | source hashes, dates, split and seed | Complete |
| 6 | `feature_dictionary.csv` | role, missingness, cardinality and PIT note per column | Complete |
| 7 | `feature_group_comparison.csv` | Matrix 7D vs facts vs combined | Complete |
| 8 | `model_comparison_scorecard.csv` | Matrix, Logistic, LightGBM, XGBoost and hybrid, Win/Place | Complete |
| 9 | `walk_forward_results.csv` | 160 model/target/date fold rows | Complete |
| 10 | `holdout_results.csv` | 2026-07-15 temporal block | Complete with global-pristine caveat |
| 11 | `learning_curve.csv` | 50/100/150/188 training-race points | Complete; 250+ unavailable |
| 12 | `calibration_report.md` | fixed Win/Place score bands and observed rates | Complete |
| 13 | `segment_analysis.csv` | venue, track, distance, class and field-size slices | Complete |
| 14 | `failure_review.md` | Matrix: 128 0/1-hit races; ML challenger: 127; normal vs abnormal cohorts | Complete |
| 15 | `model_card.md` | use, data, models, metrics, limitations and runtime | Complete |
| 16 | `promotion_recommendation.md` | strict DO NOT PROMOTE decision with binding failures | Complete |
| 17 | `betting_layer_report.md` | N/A table and precise missing-data requirement | Complete without fabricated ROI |
| 18 | `final_hkjc_ml_report.md` | executive decision and consolidated scorecards | Complete |

Additional evidence: `score_band_analysis.csv`, `metric_uncertainty.csv`, `shap_summary.csv`, `feature_importance.csv`, `top2_rank_overlay_search.csv`, OOF/holdout prediction ledgers, serialized research models, and regression tests.

Production Matrix code/weights were not changed. Only alignment/PIT safeguards and research artifacts are eligible for this research commit.
