# EXP-20261012-13 — Field-size leaf diagnostic uncertainty

- Date/platform:2026-10-12 Australia/Sydney; AU.
- Purpose: complete the pre-existing19-leaf/four-bucket description with canonical race-day uncertainty, not fit new coefficients or select leaves.
- Prior review: EXP-20260821-04 and EXP-20260831-14; baseline_description_registration.json and existing source-bound description. Historical REJECT/UNRESOLVABLE decisions are not reopened.
- Baseline: locked0328f13a9564c787837e3c4aa1cfff19235c9b0c serving capture, exact raw source/label hashes; fixed08-05–09-26 leaf diagnostic window.
- Registration: field_size_diagnostic_registration_v1.json locks nine source/code inputs, all leaf keys, four cohorts,2,000 day bootstrap draws, seed7 and descriptive limits before this diagnostic run.
- Sample:1,399 admitted complete reported-roster races /13,423 runners /43 days;624 in-window exclusions.0 PIT fit-eligible races granted.
- Results: all76 existing point-stat/count cells exactly reproduced; nominal descriptive day CIs/coverage/SD/constant-score counts available for every cell. No simultaneous confidence/Holm inference, model judgement, fit, candidate comparison, marginal-value or source-PIT claim.
- Tests:3 focused clustering/neutral-score/bucket tests PASS; quick/full checks PASS. Source hashes checked before/after; no model, golden/calibration, production CSV, real blind shadow status/outcomes or release changes.
- Decision: DESCRIPTIVE_ONLY; Phase F PARTIAL. Provenance-verified coverage and candidate incremental performance remain unknown. No AUC-driven rebuild recommendation.
- Reproduce: frozen environment.json; python3 -B -m pytest -q docs/audits/au-full-model-20261011/test_field_size_leaf_diagnostics_v1.py -p no:cacheprovider; python3 -B docs/audits/au-full-model-20261011/au_field_size_leaf_diagnostics_v1.py; python3 -B docs/audits/au-full-model-20261011/run_field_size_checks_v1.py. Outputs immutable; use new versioned outputs for reproduction.

Full table/limits in docs/audits/au-full-model-20261011/FIELD_SIZE_LEAF_DIAGNOSTIC_REVIEW.md; check manifest binds source and results. No commit/push/deploy/notification.
