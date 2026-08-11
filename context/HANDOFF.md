# Handoff

## Current task

Execute the HKJC Wong Choi ML program described in `hkjc-ml-program.md`.

## Completed work

1. Dataset-integrity and PIT leakage audit completed: READY WITH LIMITATIONS.
2. Venue/track, actual-starter, Place-target, distance fallback, incomplete-result, and replay-date alignment fixes implemented with regression tests.
3. Matrix, Logistic, LightGBM, XGBoost, hybrid, and Top-2 overlay experiments completed for Win/Place.
4. Walk-forward, external temporal block, learning curve, calibration/score bands, segments, bootstrap uncertainty, SHAP, and 0/1-hit reviews published.
5. Production promotion rejected; Matrix Champion unchanged.

## Next evidence milestone

Collect new-season local HKJC races and complete fixed-time Win/Place odds snapshots. Re-run the same frozen harness without changing thresholds first.

## Guardrails

- Preserve the current Matrix production scorer.
- Do not stage unrelated AU or Tennis worktree changes.
- Do not use odds in the analysis layer.
- Do not claim CLV, Place ROI, or a globally pristine holdout where the required snapshots/data do not exist.
