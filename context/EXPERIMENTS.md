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

- Core research commit: `b2fbee8`
- Audit-completeness supplement: `31f0a267`
- Whole-race segment / fit-window variance integrity commit: `9df53ff8`
- Complete all-model segment output commit: `f679b197`
- Multiple-winner dead-heat exclusion commit: `06f7cc67`
- Placing-boundary dead-heat exclusion commit: `e76a8442`
- Result-aligned versus pre-scratch field-size reporting commit: `4feee216`
- Champion baseline: `b186575`
- Aligned archive: 805 races / 8,249 runners, 2025-09-06 to 2026-08-07
- Fixed-mass modelling dataset: 802 races / 8,222 runners after whole-race exclusion of 3 verified dead heats (27 runners)
- Average field sizes: 10.25 result-aligned starters per usable race versus 12.21 in the pre-scratch analysis field
- Development period: 2025-09-06 to 2026-07-01 (592 races / 6,077 runners)
- Expanding walk-forward: 5 whole-date periods
- Walk-forward validation periods:
  - Fold 1: train through 2026-04-04 (238 races); validate 2026-04-06 to 2026-04-15 (53 races)
  - Fold 2: train through 2026-04-15 (291 races); validate 2026-04-16 to 2026-04-24 (49 races)
  - Fold 3: train through 2026-04-24 (340 races); validate 2026-04-25 to 2026-05-23 (73 races)
  - Fold 4: train through 2026-05-23 (413 races); validate 2026-05-24 to 2026-06-08 (93 races)
  - Fold 5: train through 2026-06-08 (506 races); validate 2026-06-10 to 2026-07-01 (86 races)
- Final chronological holdout: 2026-07-03 to 2026-08-07 (210 races / 2,145 runners)
- Features: point-in-time raw race/form/people/PF/shape inputs plus Matrix leaf scores and evidence-state flags; names, aggregate Matrix score/matrices, odds and outcomes excluded

| ID | Model / experiment | Fixed hyperparameters | Holdout analysis result | Betting result | Conclusion |
|---|---|---|---|---|---|
| AU-ML-001 | Readiness / leakage audit | Explicit allow-list; target-date history blocked; incompatible dead heats excluded whole | READY WITH LIMITATIONS; 0 duplicate races/runners, 0 target/future Facts records, 0 market features; all 802 usable races have exactly one Win target and the applicable Place-target count | N/A | Training permitted with disclosed limitations |
| AU-ML-002 | Regularised Logistic Win + Place | L2, C=0.35, liblinear, chronological Platt calibration, fit-window zero-variance pruning | Top-1 28.10%; Top-3 55.24%; Win Brier 0.084910; Place Brier 0.188490 | ROI -47.50% | Better Top-1 but materially worse probabilities; reject |
| AU-ML-003 | LightGBM Win + Place | 220 trees, depth 4, 15 leaves, lr 0.025, min child 55, L1 0.6, L2 2.5 | Top-1 19.52%; Top-3 50.95%; Win Brier 0.084671; Place Brier 0.182377 | ROI -46.49% | Development-selected, but worse than Matrix on final ranking/probability and only 1/5 walk-forward periods; reject |
| AU-ML-004 | XGBoost Win + Place | 240 trees, depth 3, lr 0.025, min child 24, L1 0.6, L2 3.0 | Top-1 20.95%; Top-3 49.52%; Win Brier 0.084159; Place Brier 0.181495 | ROI -61.36% | Some probability metrics approach Matrix, but ranking and betting risk remain worse; reject |
| AU-ML-005 | Matrix + LightGBM | Development-selected 50% ML / 50% Matrix | Top-1 22.38%; Top-3 54.76%; Win Brier 0.083801; Place Brier 0.180935 | ROI -50.50% | Place probability improved slightly, but final probability/ranking/bootstrap/betting gates fail; reject promotion |
| AU-ML-006 | Frozen 5% win-edge betting layer | Flat 1u, SP 1.5–50; odds introduced after analysis freeze | Matrix remains analysis Champion: Top-1 22.86%, Top-3 55.71%, Gold 18.57%, Good 24.76%, Pass 49.05% | Matrix ROI -37.17%; LightGBM -46.49%; hybrid -50.50%; Place/CLV N/A | No betting edge demonstrated |
