# HKJC Wong Choi ML Program

- [x] Audit archive coverage, schema integrity, race/runner joins, targets, odds availability, and point-in-time leakage.
- [x] Repair only reproducible data-pipeline defects and publish `hkjc_ml_readiness_report.md` with a readiness verdict.
- [x] Freeze and reproduce the current odds-free Matrix Champion, including score-band definitions and calibration.
- [x] Build leakage-safe chronological datasets for Win and HKJC field-size-aware Place targets.
- [x] Train and compare regularised Logistic Regression, LightGBM, and XGBoost challengers.
- [x] Run strict walk-forward, temporal holdout, learning-curve, calibration, segment, uncertainty, and explainability tests.
- [x] Evaluate Matrix+ML hybrids and diagnose 0-hit/1-hit races without post-race hindsight features.
- [x] Evaluate odds/value/betting in a separate layer; report N/A because complete timestamped odds are unavailable.
- [x] Publish scorecards, failure reviews, model card, promotion recommendation, and context handoff documents.
- [x] Verify every requested deliverable and tests; commit research artifacts. Production remains frozen because the gate failed.
