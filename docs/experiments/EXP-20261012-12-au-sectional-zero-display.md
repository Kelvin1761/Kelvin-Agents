# EXP-20261012-12 — Sectional numeric-zero display

- Date:2026-10-12 Australia/Sydney; AU.
- Hypothesis: a typed numeric0 is a supplied base, distinct from missing/None; the no-PI helper must preserve it independently of model results.
- Prior evidence: audit silent_failure_zero_display_reproduction.json and zero_display_full_corpus_occurrence.json; prior source scan/reproduction, no prior correction found in scoped experiment search.
- Baseline: locked0328f13a9564c787837e3c4aa1cfff19235c9b0c plus retained renderer_before_zero_display_v1.py.snapshot.
- Candidate: one no-PI display fallback; all other top-level renderer AST nodes unchanged.
- Tests: three focused tests PASS; independent boundary/source check PASS; captured rich corpus3,385 races/34,473 runners gives identical Markdown, Logic/verdict/full ordering, matrix composition and dashboard parsed JSON; current quick/full checks PASS after required explanation regeneration. Failed initial stale-document gate retained.
- Decision: scoped correctness correction; latent helper not reached by current standard formula loop. No ranking or analytical improvement claim. No fit/dev/holdout/reveal experiment, source/PIT acceptance or performance metrics.
- Limits: all other silent-failure/E2E/calibration requirements remain open; numeric-domain/None tests do not define a new general malformed-input policy.
- Commands: python3 -B -m pytest -q .agents/skills/au_racing/au_wong_choi_auto/tests/test_au_sectional_display_zero.py -p no:cacheprovider; python3 -B docs/audits/au-full-model-20261011/audit_zero_display_boundary_v1.py; python3 -B docs/audits/au-full-model-20261011/verify_zero_display_corpus_v1.py; python3 -B docs/audits/au-full-model-20261011/run_zero_display_checks_v2.py. Collector outputs immutable; reproduce with versioned output paths and frozen environment.json. No production apply/commit/push/release.

See docs/audits/au-full-model-20261011/ZERO_DISPLAY_CORRECTNESS_REVIEW.md and zero_display_check_manifest_v1.json for source paths/hashes and checks.
