# Project State

## HKJC Wong Choi ML research

- Status: full objective completion audit complete; production promotion rejected by the strict gate.
- Production Champion: frozen deterministic odds-free 7-dimension Matrix on the `codex` lineage.
- Research objective: test whether simple supervised models or a Matrix+ML hybrid improve pre-race competitiveness ranking without leakage or overfitting.
- Archive: 24 development meetings plus the 2026-07-15 external meeting; 250 valid races / 3,109 runners after three incomplete/non-contiguous result joins were excluded.
- Production scoring has not been changed.
- Best standalone challenger: Logistic Regression on the seven Matrix dimensions. It marginally improved walk-forward probability loss but worsened 0-hit rate and external ranking capture; the Matrix remains best overall.
- LightGBM and XGBoost underperformed the simpler models.
- A Place overlay reduced walk-forward 0-hit races from 26.1% to 23.6%, but reduced external Top-3 capture@5 from 63.0% to 59.3%; rejected.
- Complete timestamped runner-level odds are absent, so betting ROI/CLV remain N/A.
- Exact final scorecard, experiment report, Champion snapshot, integrity audit, feature coverage, course/confidence segments, ranking-quality metrics, permutation importance and SHAP interaction diagnostics are published in the evidence pack.
- Champion freeze commit: `39155166df7fdba5162b19aa872e6fe004b7f3c3`; first research commit: `9ddcd7abd5493c067bce15e2f81a5b8d40d0169a`.
