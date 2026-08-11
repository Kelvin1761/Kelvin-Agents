# Experiments

## HKJC ML program

| Experiment | Status | Decision |
|---|---|---|
| Dataset readiness and PIT leakage audit | Complete | READY WITH LIMITATIONS; 250 valid races |
| Frozen Matrix probability calibration | Complete | Remains production Champion |
| Logistic Regression: Win / Place | Complete | Best ML, but external ranking regression; no promotion |
| LightGBM: Win / Place | Complete | Underperformed Matrix / Logistic |
| XGBoost: Win / Place | Complete | Clear walk-forward ranking regression |
| Matrix+ML hybrid | Complete | No cross-period promotion candidate |
| Top-2 Place overlay | Complete | Lower walk-forward 0-hit, but external Top-5 capture regression |
| Separate odds/value layer | Complete | N/A: complete timestamped odds/Place prices unavailable |
