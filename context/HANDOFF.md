# Handoff

## Current task

Execute the HKJC Wong Choi ML program described in `hkjc-ml-program.md`.

## Immediate next actions

1. Complete dataset-integrity and point-in-time leakage audit.
2. Fix reproducible data misalignment in the dataset builder and add regression tests.
3. Resolve the local OpenMP runtime needed by installed LightGBM/XGBoost.
4. Generate readiness report; proceed automatically only if READY or READY WITH LIMITATIONS.

## Guardrails

- Preserve the current Matrix production scorer.
- Do not stage unrelated AU or Tennis worktree changes.
- Do not use odds in the analysis layer.
- Do not claim CLV, Place ROI, or an untouched holdout where the required snapshots/data do not exist.

## AU Wong Choi completed work — 2026-08-11

### Completed

- Root-cause audit for cold Model Top-3 runners finishing last and successful market favourites ranked 5+.
- Facts-to-Logic refresh alignment fix with regression coverage.
- Point-in-time historical Performance Quality backfill/recovery and canonical validation.
- Reproducible ML dataset builder, feature/leakage audit, Logistic/LightGBM/XGBoost pipelines, chronological calibration, five-period walk-forward, learning curve, bootstrap, SHAP/permutation importance, segment analysis, hybrid and separate betting evaluation.
- Readiness and final experiment reports generated.

### Findings

- Historical PQ recovery reduced cold-last errors 32→30 and missed-favourite errors 81→78 while improving terminal Top-5 AUC with positive paired-bootstrap support.
- On the 211-race final ML holdout, Matrix Top-1/Top-3 were 22.75%/55.92%; XGBoost was 21.33%/50.24%.
- XGBoost improved against Matrix in only 2/5 development walk-forward periods. The selected 50% hybrid also failed the full promotion gate.
- No historical Place dividends or timestamped odds snapshots exist, so Place ROI and CLV remain N/A.

### Main files

- `au_ml_readiness_report.md`
- `au_ml_experiment_report.md`
- `au_ml_experiment_results.json`
- `.agents/skills/au_racing/au_wong_choi_auto/scripts/au_ml_dataset.py`
- `.agents/skills/au_racing/au_wong_choi_auto/scripts/au_ml_program.py`
- `.agents/skills/au_racing/au_wong_choi_auto/resources/19_failure_cause_attribution_20260809.md`

### Verification and next action

- AU Wong Choi test suite: 396 passed before the research commit; rerun after any future feature change.
- Keep current Matrix. Prioritise new versioned pre-race evidence (trainer/jockey condition splits, timed trials/jump-outs, captured trackwork/gear, carefully gated pedigree priors) instead of additional weight or slot micro-adjustments.
