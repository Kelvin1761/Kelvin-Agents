# Experiments

## HKJC ML program

| Experiment | Status | Decision |
|---|---|---|
| Dataset readiness and PIT leakage audit | In progress | Training blocked until integrity verdict |
| Frozen Matrix probability calibration | Pending | Baseline for all comparisons |
| Logistic Regression: Win / Place | Pending | Simple interpretable challenger |
| LightGBM: Win / Place | Pending | Shallow regularised tree challenger |
| XGBoost: Win / Place | Pending | Shallow regularised tree challenger |
| Matrix+ML hybrid | Pending | Test only after standalone validation |
| Separate odds/value layer | Pending | Analysis probabilities frozen first |

## AU ML program — 2026-08-11

Shared setup for `AU-ML-001` to `AU-ML-006`:

- Research commit: `b2fbee8`
- Champion baseline: `b186575`
- Dataset: 805 races / 8,249 runners, 2025-09-06 to 2026-08-07
- Development period: 2025-09-06 to 2026-07-01 (594 races)
- Expanding walk-forward: 5 whole-date periods
- Walk-forward validation periods:
  - Fold 1: train through 2026-04-04 (238 races); validate 2026-04-06 to 2026-04-15 (53 races)
  - Fold 2: train through 2026-04-15 (291 races); validate 2026-04-16 to 2026-04-24 (49 races)
  - Fold 3: train through 2026-04-24 (340 races); validate 2026-04-25 to 2026-05-23 (74 races)
  - Fold 4: train through 2026-05-23 (414 races); validate 2026-05-24 to 2026-06-08 (93 races)
  - Fold 5: train through 2026-06-08 (507 races); validate 2026-06-10 to 2026-07-01 (87 races)
- Final chronological holdout: 2026-07-03 to 2026-08-07 (211 races / 2,157 runners)
- Features: point-in-time raw race/form/people/PF/shape inputs plus Matrix leaf scores and evidence-state flags; names, aggregate Matrix score/matrices, odds and outcomes excluded

| ID | Model / experiment | Fixed hyperparameters | Holdout analysis result | Betting result | Conclusion |
|---|---|---|---|---|---|
| AU-ML-001 | Readiness / leakage audit | Explicit allow-list; target-date history blocked | READY WITH LIMITATIONS; 0 duplicate runners, 0 target/future Facts records, 0 market features | N/A | Training permitted with disclosed limitations |
| AU-ML-002 | Regularised Logistic Win + Place | L2, C=0.35, liblinear, chronological Platt calibration | Top-1 27.96%; Top-3 55.92%; Win Brier 0.085254; Place Brier 0.188506 | ROI -47.69% | Better Top-1 but materially worse probabilities; reject |
| AU-ML-003 | LightGBM Win + Place | 220 trees, depth 4, 15 leaves, lr 0.025, min child 55, L1 0.6, L2 2.5 | Top-1 18.01%; Top-3 47.87%; Win Brier 0.085081; Place Brier 0.182283 | ROI -63.33% | Reject |
| AU-ML-004 | XGBoost Win + Place | 240 trees, depth 3, lr 0.025, min child 24, L1 0.6, L2 3.0 | Top-1 21.33%; Top-3 50.24%; Win Brier 0.084657; Place Brier 0.181451 | ROI -52.66% | Best independent challenger, but worse than Matrix; reject promotion |
| AU-ML-005 | Matrix + XGBoost | Development-selected 50% ML / 50% Matrix | Top-1 24.64%; Top-3 55.92%; Win Brier 0.084001; Place Brier 0.180497 | ROI -46.28% | Some place/Gold gains, but full gate fails; reject promotion |
| AU-ML-006 | Frozen 5% win-edge betting layer | Flat 1u, SP 1.5–50; odds introduced after analysis freeze | Matrix remains analysis Champion | Matrix ROI -37.72%; XGBoost -52.66%; hybrid -46.28%; Place/CLV N/A | No betting edge demonstrated |
