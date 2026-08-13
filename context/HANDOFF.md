# Handoff

## Current task

Publish the completed AU Wong Choi ML research through the clean `codex-au-ml-release` branch without promoting ML into production.

## Immediate next actions

1. Commit the final regenerated reports and context.
2. Push the remaining clean AU-only release commits.
3. Create and merge one non-draft PR to `main` after explicit PR-creation approval.

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
- One-command archive-to-report rebuild wrapper with input/output hashes and strict completeness by default.
- Readiness and final experiment reports generated.

### Findings

- Historical PQ recovery reduced cold-last errors 32→30 and missed-favourite errors 81→78 while improving terminal Top-5 AUC with positive paired-bootstrap support.
- The aligned archive contains 805 races / 8,249 runners. The fixed-mass modelling dataset contains 802 races / 8,222 runners after excluding two dead heats for first and one placing-boundary dead heat; all usable races now have coherent Win and Place target totals.
- The readiness report now distinguishes 10.25 result-aligned starters per usable race from the 12.21 average pre-scratch analysis field, preventing the latter from overstating the settled runner sample.
- On the 210-race final ML holdout, Matrix Top-1/Top-3 were 22.86%/55.71%; development-selected LightGBM was 19.52%/50.95%.
- LightGBM improved against Matrix in 1/5 development walk-forward periods. The selected 50% Matrix/LightGBM hybrid improved the composite score in 4/5 periods but still failed final probability, ranking, bootstrap and betting gates.
- Whole-race post-hoc market analysis found Matrix Top-3 of 80.25% when a favourite won versus 40.31% when a non-favourite won. LightGBM was worse in both groups (70.37% / 38.76%).
- No historical Place dividends or timestamped odds snapshots exist, so Place ROI and CLV remain N/A.

### Files changed

Unless otherwise stated, `scripts/`, `tests/` and `resources/` below are under `.agents/skills/au_racing/au_wong_choi_auto/`.

- Reports and state: `au_ml_readiness_report.md`, `au_ml_experiment_report.md`, `au_ml_experiment_results.json`, `context/PROJECT_STATE.md`, `context/DECISIONS.md`, `context/EXPERIMENTS.md`, `context/HANDOFF.md`.
- Root-cause and data recovery: `resources/19_failure_cause_attribution_20260809.md`, `scripts/au_failure_cause_attribution.py`, `scripts/au_backfill_sportsbet_performance_quality.py`.
- Reproducible ML program: `scripts/au_ml_dataset.py`, `scripts/au_ml_program.py`, `scripts/au_ml_rebuild.py`.
- Production-alignment fixes: `scripts/racing_engine/engine_core.py`, `scripts/racing_engine/scoring.py`.
- Tests: `tests/test_au_ml_dataset.py`, `tests/test_au_ml_program.py`, `tests/test_au_ml_rebuild.py`, `tests/test_failure_cause_attribution.py`, `tests/test_sportsbet_pq_backfill.py`, `tests/test_facts_enrichment_refresh.py`, `tests/test_performance_quality.py`.
- Environment/dependency declarations: `.gitignore`, `requirements-optional.txt`.

### Verification and next action

- AU Wong Choi test suite: 406 passed after dead-heat target-integrity and field-size-reporting coverage.
- Keep current Matrix. Prioritise new versioned pre-race evidence (trainer/jockey condition splits, timed trials/jump-outs, captured trackwork/gear, carefully gated pedigree priors) instead of additional weight or slot micro-adjustments.
