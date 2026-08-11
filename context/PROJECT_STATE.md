# Project State

## HKJC Wong Choi ML research

- Status: full objective completion audit plus individual-dimension ML audit complete; production promotion rejected by the strict gate.
- Production Champion: frozen deterministic odds-free 7-dimension Matrix on the `codex` lineage.
- Research objective: test whether simple supervised models or a Matrix+ML hybrid improve pre-race competitiveness ranking without leakage or overfitting.
- Archive: 24 development meetings plus the 2026-07-15 external meeting; 250 valid races / 3,109 runners after three incomplete/non-contiguous result joins were excluded.
- Production scoring has not been changed.
- Best standalone challenger: Logistic Regression on the seven Matrix dimensions. It marginally improved walk-forward probability loss but worsened 0-hit rate and external ranking capture; the Matrix remains best overall.
- LightGBM and XGBoost underperformed the simpler models.
- The archived ability column was aligned to an older outer-weight contract. Research now preserves that value separately and rebuilds the current Champion from the seven stored dimensions; the complete evidence pack was refreshed.
- Current-contract Matrix walk-forward: 0-hit 25.47%, Winner@3 53.42%, Top-3 capture@5 62.94%, NDCG@5 53.12%.
- A Place overlay reduced walk-forward 0-hit races from 25.5% to 24.8%, but reduced external Top-3 capture@5 from 63.0% to 59.3%; rejected.
- Individual ML audit completed for trainer signal, race shape and stability. Stability was the only development-gate candidate: it moved seven actual Top-3 runners from Rank 3 to Rank 2 and improved six 0/1-hit races versus one harmed race, but failed the external NDCG/capture non-regression gate. It remains research-only.
- Complete timestamped runner-level odds are absent, so betting ROI/CLV remain N/A.
- Exact final scorecard, experiment report, Champion snapshot, integrity audit, feature coverage, course/confidence segments, ranking-quality metrics, permutation importance, SHAP interaction diagnostics, dimension ablations, residual-cap search and rank movements are published in the evidence packs.
- Champion freeze commit: `39155166df7fdba5162b19aa872e6fe004b7f3c3`; first research commit: `9ddcd7abd5493c067bce15e2f81a5b8d40d0169a`.
