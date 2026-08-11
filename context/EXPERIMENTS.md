# Experiments

Common evidence identity unless stated otherwise:

- Experiment date: 2026-08-11
- Champion freeze commit: `39155166df7fdba5162b19aa872e6fe004b7f3c3`
- Research implementation/results commit: `9ddcd7abd5493c067bce15e2f81a5b8d40d0169a`
- Dataset: 2026-04-12–2026-07-15; 250 valid races / 3,109 runners
- Expanding train range: starts 2026-04-12 and ends strictly before each test meeting
- Walk-forward validation: 2026-05-09–2026-07-12; 161 races / 2,019 runners
- External block: 2026-07-15; 9 races / 107 runners; ML-unseen here, not globally pristine
- Betting result: N/A for every model because complete fixed-time Win/Place prices and settlement data are absent

## EXP-HKJC-ML-001 — Dataset readiness and PIT integrity

- Features/model: schema, identity, label, venue/track/course, field-size and leakage rules; no predictive model.
- Hyperparameters: none.
- Result: READY WITH LIMITATIONS; three incomplete/non-contiguous result joins excluded; duplicate runner keys 0; one winner and contiguous finish order enforced; Place cutoff matches HKJC field-size rule.
- Conclusion: proceed with conservative ML; canonical jockey/trainer IDs, going/rail, entity rename registry and event/settlement lifecycle remain unavailable.

## EXP-HKJC-ML-002 — Frozen Matrix Champion

- Features: seven official Matrix dimensions plus one fold-local calibrated probability mapping from frozen `ability_score`.
- Model/hyperparameters: deterministic Matrix weights; Logistic probability calibrator `C=1.0`, L2, `max_iter=1000`; fitted inside each fold.
- Win walk-forward: Brier 0.069533; Log Loss 0.255374; Top-1 24.84%; Top-3 53.42%; Top-3 capture@5 62.94%; 0-hit 25.47%.
- Place walk-forward: Brier 0.168201; Log Loss 0.511811.
- Conclusion: production Champion benchmark; unchanged.

## EXP-HKJC-ML-003 — Regularised Logistic Regression

- Features: selected `matrix_7d` group: seven absolute Matrix dimensions plus seven within-race relative values.
- Hyperparameters: `C=0.25`, L2, `lbfgs`, `max_iter=1500`, seed 20260811; fold-local median imputation and standardisation.
- Win walk-forward: Brier 0.069566; Log Loss 0.254912; Top-1 24.22%; Top-3 52.80%; Top-3 capture@5 62.73%; 0-hit 27.95%.
- Place walk-forward: Brier 0.164769; Log Loss 0.502814.
- External Win: Brier 0.078424; Log Loss 0.294133; Top-3 capture@5 51.85%.
- Conclusion: best independent ML probability model, but ranking/external regression means no promotion.

## EXP-HKJC-ML-004 — LightGBM

- Features: selected `matrix_7d` group.
- Hyperparameters: 140 trees, learning rate 0.03, depth 3, 7 leaves, min child 35, row/feature subsampling 0.8, L1 0.6, L2 2.5, seed 20260811.
- Win walk-forward: Brier 0.070017; Log Loss 0.258530; Top-3 51.55%; Top-3 capture@5 61.90%.
- Place walk-forward: Brier 0.1655; Log Loss 0.5051.
- Conclusion: nonlinear model underperformed Matrix/Logistic; retain diagnostics only.

## EXP-HKJC-ML-005 — XGBoost

- Features: selected `matrix_7d` group.
- Hyperparameters: 160 trees, learning rate 0.03, depth 3, min child weight 8, row/feature subsampling 0.8, L1 0.6, L2 3.0, seed 20260811.
- Win walk-forward: Brier 0.072612; Log Loss 0.273149; Top-3 36.02%; Top-3 capture@5 56.11%.
- Place walk-forward: Brier 0.1701; Log Loss 0.5178.
- Conclusion: clear ranking regression; reject.

## EXP-HKJC-ML-006 — Feature groups

- Models: regularised Logistic Regression with the same fixed hyperparameters.
- Features: `matrix_7d` vs 92 numeric + 4 categorical pre-race facts vs their combination.
- Result: facts-only Win Log Loss 0.2714 / Top-3 capture@5 58.39%; combined 0.2617 / 61.49%; both worse than `matrix_7d` 0.2549 / 62.73%.
- Conclusion: wider facts do not justify complexity; select `matrix_7d`.

## EXP-HKJC-ML-007 — Matrix + ML probability hybrid

- Features/models: fold-local Matrix and Logistic probabilities only; no odds.
- Hyperparameters: fixed convex search Matrix weights 0.25, 0.50, 0.75 selected on walk-forward only.
- Best Win hybrid: Matrix weight 0.25; walk-forward Brier 0.0695 / Log Loss 0.2547 / Top-3 capture@5 62.11%; external capture@5 55.56%.
- Best Place hybrid: Matrix weight 0.75; walk-forward Brier 0.1670 / Log Loss 0.5091.
- Conclusion: no cross-period promotion candidate.

## EXP-HKJC-ML-008 — Top-2 Place rank overlay

- Features/models: Matrix Win rank plus best ML Place rank; diagnostic synthetic rank only.
- Hyperparameters: Matrix rank weight 0.50–1.00 in 0.05 steps, selected on walk-forward.
- Result: strongest Place overlay reduced walk-forward 0-hit from 25.47% to 24.84%, but external Top-3 capture@5 fell from 62.96% to 59.26%. A Win-rank overlay reached 22.98% 0-hit but also only 59.26% external capture@5 and reduced walk-forward Winner@3.
- Conclusion: rejected; no blind swap or micro tie-break.

## EXP-HKJC-ML-009 — Explainability and interactions

- Features/models: Logistic coefficients; LightGBM/XGBoost model importance, SHAP and tree SHAP interactions; race-preserving external permutation.
- Hyperparameters: 30 permutation repeats per selected feature, seed 20260811; diagnostics use the nine-race external block and never choose the model.
- Result: relative trainer signal, race shape and stability dominate; stable nonlinear improvement is absent; form line/horse health appear weaker conditionally.
- Conclusion: monitor relative signals on new data; do not reweight production from this archive.

## EXP-HKJC-ML-010 — Separate betting/value layer

- Features/model: would compare independent probabilities with fixed-time HKJC Win/Place odds after analysis; no odds enter analysis X.
- Hyperparameters: no edge/stake threshold selected because required inputs are absent.
- Analysis result: unaffected.
- Betting result: ROI, turnover, strike rate, average odds/edge, drawdown, losing streak and CLV all N/A.
- Conclusion: betting question remains unanswerable until timestamped prices, dividends, scratches and settlement rules are captured.

## EXP-HKJC-ML-011 — Current-contract ability alignment

- Finding: archived `current_live_recomputed_ability` matched the pre-2026-08-01 outer weights (maximum rounding error 0.005) rather than the contract identified by the evidence pack.
- Repair: preserve the archived score as `archived_live_recomputed_ability`, then rebuild the research Champion from all seven stored dimensions using the frozen production weights.
- Scope: 3,109/3,109 rows rebuilt; 3,044 rows changed by more than 0.01; maximum absolute change 1.150735 points.
- Result: refreshed the complete main evidence pack and serialized Matrix calibrators. Production scoring code was not changed.

## EXP-HKJC-DIM-001 — Individual-dimension ablation and bounded residual ML

- Dimensions: `trainer_signal`, `race_shape`, `stability`; odds, result priors, pace/run-style scores, micro tie-breaks and blind swaps excluded.
- Method: expanding-window fold-local ablation, standalone diagnostic Logistic model, and Matrix-offset residual Logistic model with L2=1.0 and development-only caps 0.05/0.10/0.20.
- Ablation: deleting any of the three dimensions worsened development ranking; all three remain structurally useful.
- `trainer_signal`: selected cap 0.20; development 0/1-hit severity worsened 0.62pp and Winner@3 fell 0.62pp. Reject.
- `race_shape`: selected cap 0.05; Winner@3 rose 1.24pp but 0/1-hit severity was unchanged and capture@5 fell 0.21pp. Diagnostic only.
- `stability`: selected cap 0.05; development Top2 two-hit rose 22.36%→26.09%, Winner@2 rose 41.61%→43.48%, six weak races improved and one worsened. Seven actual Top-3 runners moved Rank 3→2. However 0-hit rose 25.47%→26.09%, and the nine-race external block lost 3.70pp capture@5 / 4.13pp NDCG@5 despite one additional two-hit race.
- Conclusion: `stability` is the only credible shadow candidate, but it fails the external non-regression gate. No production promotion.

## EXP-HKJC-DIM-002 — Frozen stability residual shadow integration

- Contract: `HKJC_STABILITY_RESIDUAL_SHADOW_V1`; final development fit; 15 stability features; L2=1.0; bounded log-odds delta ±0.05; model checksum pinned.
- Runtime: standalone reflector runner plus opt-in Auto flag `--stability-residual-shadow`; default Auto never loads the ML dependency.
- Outputs: separate race/meeting CSV and JSON with mainline/shadow probability, ranks, Rank-3→Top-2 entry/exit and optional post-race hit comparison.
- Safety: Logic input hash checked before/after; mainline Logic, ranking, Grade, verdict, Top Pick, reports and recommendations are not modified. Result labels are attached only after scoring when an explicit results file is supplied.
- Conclusion: approved for shadow monitoring only; production promotion remains rejected.
