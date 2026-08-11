# HKJC Explainability and Diagnosis

## Evidence tables

### Best ML signed/absolute coefficient evidence

| model | target | feature | importance | signed_effect |
|---|---|---|---|---|
| Logistic Regression | Win | num__rel_matrix_trainer_signal | 0.2792 | 0.2792 |
| Logistic Regression | Win | num__rel_matrix_race_shape | 0.1930 | 0.1930 |
| Logistic Regression | Win | num__matrix_race_shape | 0.1796 | 0.1796 |
| Logistic Regression | Win | num__rel_matrix_stability | 0.1480 | 0.1480 |
| Logistic Regression | Win | num__matrix_trainer_signal | 0.1444 | 0.1444 |
| Logistic Regression | Win | num__matrix_stability | 0.1309 | 0.1309 |
| Logistic Regression | Win | num__rel_matrix_sectional | 0.1225 | 0.1225 |
| Logistic Regression | Win | num__matrix_class_advantage | 0.0777 | 0.0777 |
| Logistic Regression | Win | num__matrix_sectional | 0.0670 | 0.0670 |
| Logistic Regression | Win | num__matrix_horse_health | 0.0612 | -0.0612 |

### Race-preserving permutation diagnostic

| feature | baseline_log_loss | mean_log_loss_increase | std_log_loss_increase | external_races |
|---|---|---|---|---|
| rel_matrix_race_shape | 0.2941 | 0.0026 | 0.0049 | 9 |
| matrix_race_shape | 0.2941 | 0.0022 | 0.0052 | 9 |
| rel_matrix_trainer_signal | 0.2941 | 0.0017 | 0.0073 | 9 |
| rel_matrix_horse_health | 0.2941 | 0.0008 | 0.0008 | 9 |
| rel_matrix_form_line | 0.2941 | 0.0007 | 0.0008 | 9 |
| matrix_trainer_signal | 0.2941 | 0.0004 | 0.0025 | 9 |
| matrix_form_line | 0.2941 | -0.0001 | 0.0004 | 9 |
| rel_matrix_class_advantage | 0.2941 | -0.0004 | 0.0017 | 9 |
| matrix_class_advantage | 0.2941 | -0.0006 | 0.0016 | 9 |
| matrix_horse_health | 0.2941 | -0.0010 | 0.0015 | 9 |

### Tree SHAP interactions

| model | feature_a | feature_b | mean_abs_shap_interaction | external_races |
|---|---|---|---|---|
| LightGBM | num__rel_matrix_race_shape | num__rel_matrix_trainer_signal | 0.0348 | 9 |
| LightGBM | num__rel_matrix_stability | num__rel_matrix_race_shape | 0.0164 | 9 |
| LightGBM | num__rel_matrix_stability | num__rel_matrix_trainer_signal | 0.0161 | 9 |
| LightGBM | num__matrix_race_shape | num__rel_matrix_trainer_signal | 0.0155 | 9 |
| LightGBM | num__matrix_stability | num__rel_matrix_race_shape | 0.0151 | 9 |
| LightGBM | num__matrix_stability | num__rel_matrix_stability | 0.0144 | 9 |
| LightGBM | num__matrix_sectional | num__rel_matrix_trainer_signal | 0.0131 | 9 |
| LightGBM | num__rel_matrix_sectional | num__rel_matrix_trainer_signal | 0.0094 | 9 |
| LightGBM | num__matrix_race_shape | num__rel_matrix_stability | 0.0093 | 9 |
| LightGBM | num__matrix_stability | num__matrix_race_shape | 0.0089 | 9 |

### Feature-group ablation

| feature_group | log_loss | brier | winner_top3 | top3_capture_at5 | ndcg_at5 | selected |
|---|---|---|---|---|---|---|
| matrix_7d | 0.2549 | 0.0696 | 0.5280 | 0.6273 | 0.5265 | True |
| facts_compact | 0.2714 | 0.0724 | 0.4099 | 0.5839 | 0.4687 | False |
| matrix_plus_facts | 0.2617 | 0.0708 | 0.5155 | 0.6149 | 0.5152 | False |

## Answers to the ten diagnosis questions

1. **Strongest features:** relative trainer signal, race shape and stability dominate the best linear Win challenger; tree SHAP broadly agrees on those dimensions.
2. **Matrix factors adding value:** trainer signal, race shape, stability, and sectional evidence repeatedly appear in coefficient/tree diagnostics.
3. **Weak factors:** form-line and horse-health terms are consistently smaller in the selected seven-dimension challenger.
4. **Possible duplication:** absolute and race-relative versions of each Matrix dimension intentionally coexist and can be correlated; the wider facts group also repeats information already compressed into Matrix dimensions.
5. **Neutral/default dependence:** exact per-column rates are in `feature_dictionary.csv`; features with high neutral/default rates are not promoted merely because a tree can split on them.
6. **Potentially overweighted:** negative/small conditional coefficients for absolute horse health and form line are a warning, not causal proof. Production weights remain frozen because no challenger passed external gates.
7. **Potentially underweighted:** relative trainer, race-shape and stability signals merit future monitoring, but archive-only reweighting would be overfit.
8. **Nonlinearity:** shallow trees and their interactions did not improve overall chronological ranking, so there is no stable evidence that nonlinear complexity presently adds value.
9. **Missing interactions/data:** barrier × exact configuration × running style, pace × running style, going, rail, and fully point-in-time jockey/trainer combinations remain incomplete or unavailable.
10. **What ML learned beyond Matrix:** chiefly that within-race relative values matter at least as much as absolute scores. That insight slightly improves probability loss but not enough ranking/external evidence to replace the Matrix.

Permutation and interaction results use only nine external races and are diagnostic, never a selection or promotion input.
