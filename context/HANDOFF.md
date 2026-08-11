# Handoff

## Current task

Execute the HKJC Wong Choi ML program described in `hkjc-ml-program.md`.

## Completed work

1. Dataset-integrity and PIT leakage audit completed: READY WITH LIMITATIONS.
2. Venue/track, actual-starter, Place-target, distance fallback, incomplete-result, and replay-date alignment fixes implemented with regression tests.
3. Matrix, Logistic, LightGBM, XGBoost, hybrid, and Top-2 overlay experiments completed for Win/Place.
4. Walk-forward, external temporal block, learning curve, calibration/score bands, segments, bootstrap uncertainty, SHAP, and 0/1-hit reviews published.
5. Production promotion rejected; Matrix Champion unchanged.
6. Requirement-by-requirement completion audit added the exact requested scorecard, experiment report, Champion snapshot, system/integrity audits, expanded feature coverage, ranking metrics, race confidence, course segments, permutation importance and SHAP interactions.
7. Fixed an evidence-baseline alignment bug: the archived ability score used the previous outer weights. The current-contract Champion is now rebuilt from seven dimensions while the archived score is retained for audit.
8. Completed individual-dimension ablation and bounded residual ML for trainer signal, race shape and stability. Stability improved six weak development races and promoted seven actual Top-3 Rank-3 runners into Top 2, but failed external capture/NDCG non-regression; no production change.
9. Froze stability residual V1 as an opt-in shadow runner and Auto CLI flag. Model checksum, target, cap and feature contract fail closed; Logic input remains byte-identical and outputs are separate.

## Verification

- HKJC reflector unittest suite: 37 passed, including stability-shadow replay/rank-drift checks and five dimension artifact-contract checks.
- Original main ML artifact-contract pytest suite: 5 passed.
- HKJC production auto tests: 72 passed, including opt-in shadow/mainline identity.
- Serialized research models: all 14 reload successfully (eight main-program plus six dimension residual bundles).
- Data quality, PIT blacklist, full weak-race detail count, sensitive-path scan and `git diff --check`: passed.

## Unresolved issues

- Going/rail, canonical jockey/trainer IDs, effective-dated rename registry and complete scratch/reserve/incident/settlement lifecycle data are unavailable.
- Complete fixed-time Win/Place prices and official settlement inputs are unavailable, so betting ROI/CLV remain N/A.
- The nine-race external block is too small and not globally pristine; no production promotion is authorized.

## Next evidence milestone

Collect new-season local HKJC races and complete fixed-time Win/Place odds snapshots. Re-run the same frozen harness without changing thresholds first.

## Guardrails

- Preserve the current Matrix production scorer.
- Do not stage unrelated AU or Tennis worktree changes.
- Do not use odds in the analysis layer.
- Do not claim CLV, Place ROI, or a globally pristine holdout where the required snapshots/data do not exist.
- Treat `final_hkjc_scorecard.md` and `hkjc_ml_experiment_report.md` as the primary user-facing research results.
- Treat `hkjc_dimension_ml_report.md` and `dimension_rank_movements.csv` as the primary individual-dimension evidence; do not turn the stability result into a conditional 1200m/Class-4 rule from this archive.
- Use `--stability-residual-shadow` only for collective local-meeting monitoring; never manually substitute its Top 2 into the production recommendation.
