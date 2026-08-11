# HKJC Full ML Program Completion Audit

## Required deliverables

| # | Deliverable | Authoritative evidence | Status |
|---:|---|---|---|
| 1 | `hkjc_ml_readiness_report.md` | coverage breakdown, feature dictionary, READY WITH LIMITATIONS verdict | Complete |
| 2 | `hkjc_ml_experiment_report.md` | reproducibility identity, models, splits, scorecards, conclusion | Complete |
| 3 | reproducible historical dataset builder | `build_hkjc_ranking_dataset.py`, alignment tests, manifest/source hashes | Complete |
| 4 | point-in-time feature pipeline | `hkjc_ml_program.py`, `point_in_time_leakage_test.md`, blacklist and chronological guards | Complete with documented source limitations |
| 5 | ML training pipeline | Logistic, LightGBM, XGBoost Win/Place code and eight loadable research models | Complete |
| 6 | chronological validation | whole-race expanding splits; `model_comparison_scorecard.csv` | Complete |
| 7 | walk-forward evaluation | `walk_forward_results.csv` and prediction ledger | Complete: 16 meeting folds / 161 races |
| 8 | learning curve | `learning_curve.csv` | Complete to maximum 188 train races; unavailable larger points not extrapolated |
| 9 | calibration analysis | `calibration_report.md`, `score_band_analysis.csv`, fixed ten-bin `calibration_curve.csv` | Complete |
| 10 | feature importance / SHAP | coefficients/native importance, permutation, SHAP and SHAP interaction CSVs plus narrative | Complete with nine-race diagnostic caveat |
| 11 | HKJC segment analysis | venue, surface, course, distance, class, field size and model confidence | Complete; going/rail explicitly N/A |
| 12 | Matrix vs ML comparison | probability, Top-1/2/3, average ranks, rank correlation, capture and NDCG metrics | Complete |
| 13 | Matrix + ML hybrid | `hybrid_weight_search.csv`, `hybrid_config.json` | Complete; rejected |
| 14 | separate betting/value evaluation | `betting_layer_report.md` | Complete as NOT EVALUABLE; no fabricated ROI/CLV |
| 15 | final analysis scorecard | `final_hkjc_scorecard.md` exact requested layout | Complete |
| 16 | final betting scorecard | N/A fields in exact scorecard and separate betting report | Complete to available evidence |
| 17 | production recommendation | `promotion_recommendation.md` | Complete: KEEP CURRENT MATRIX |
| 18 | updated cross-tool context | `context/PROJECT_STATE.md`, `DECISIONS.md`, `HANDOFF.md`, `EXPERIMENTS.md` | Complete |

## Objective sections

| Section | Requirement | Evidence/result | Status |
|---:|---|---|---|
| 1 | two-layer architecture | system/experiment audits; odds blacklist; separate betting report | Proven |
| 2 | understand existing system end-to-end | `system_architecture_audit.md`, `champion_snapshot.md` | Proven |
| 3 | dataset readiness and feature coverage | readiness report, coverage CSV, expanded feature dictionary | Proven |
| 4 | historical integrity | integrity audit, excluded-race manifest, regression tests | Proven with explicit unresolved limitations |
| 5 | point-in-time/leakage | PIT report, feature blacklist, fold-local preprocessing, historical date guard | Proven for selected features |
| 6 | readiness report/automatic continuation | READY WITH LIMITATIONS then ML run completed | Proven |
| 7 | freeze Rating Matrix | contract, commits, dimensions, weights, thresholds and rules captured | Proven |
| 8 | Win/Place targets | separate targets; field-size-aware HKJC Place labels | Proven |
| 9 | no odds in analysis X | blacklist and quality assertion | Proven |
| 10 | four core models | Matrix, Logistic, LightGBM, XGBoost | Proven |
| 11 | feature engineering | facts, Matrix and combined groups; relative-field features | Proven to available PIT data |
| 12 | chronological validation | no random split; race groups intact | Proven |
| 13 | walk-forward | 16 expanding meeting folds | Proven |
| 14 | holdout protection | 2026-07-15 excluded from model/feature/hybrid selection; contamination caveat stated | Proven with caveat |
| 15 | overfitting control | fixed shallow regularised models; small grids only | Proven |
| 16 | learning curve | 50/100/150/188; larger requested samples unavailable | Proven to archive limit |
| 17 | independent analysis metrics | dataset, Win/Place loss/calibration/ranking metrics | Proven |
| 18 | probability calibration | Brier, Log Loss, ECE and fixed buckets | Proven |
| 19 | required comparison | exact model scorecard and exact final result | Proven |
| 20 | market external benchmark | not used; unavailable complete odds documented | N/A by evidence |
| 21 | betting layer | architecturally separate; inputs specified | Proven; evaluation unavailable |
| 22 | betting performance | all unsupported metrics explicitly N/A | Complete without fabrication |
| 23 | segments | racing segments complete where data exists; betting/going/rail N/A | Proven with limitations |
| 24 | explainability/diagnosis | ten questions answered with coefficient, permutation, SHAP, interaction and ablation evidence | Proven |
| 25 | Matrix + ML hybrid | chronological convex hybrid search | Proven; rejected |
| 26 | strict promotion gate | cross-period probability/ranking/calibration/evidence gates | Proven; no promotion |
| 27 | exact final scorecard | `final_hkjc_scorecard.md` | Proven |
| 28 | cross-tool context | four context files, detailed per-experiment records | Proven |
| 29 | deliverables/primary questions | all 18 rows above; truth-seeking verdict retained | Proven |

## Binding conclusion

The primary question is answered: proper ML did **not** demonstrate a repeatable out-of-sample ranking improvement over the current Rating Matrix. The secondary betting question cannot be answered from this archive because complete fixed-time odds and settlement records do not exist. Production Matrix code and weights remain unchanged.
