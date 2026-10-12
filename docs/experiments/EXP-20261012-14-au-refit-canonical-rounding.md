# EXP-20261012-14 — Refit canonical rounding

- Date/platform:2026-10-12 Australia/Sydney; AU.
- Hypothesis: refit numerical vectors must obey canonical mapper, ordered composition and both Python publication-rounding stages independently of model outcomes.
- Prior evidence: production training projection/registry audits and EXP-20261012-04; plugin baseline exposes independent NumPy half-rounding mismatch. This is a correctness defect, not a fitted candidate.
- Baseline: retained au_matrix_refit_before_canonical_rounding_v1.py.snapshot; locked0328f13a9564c787837e3c4aa1cfff19235c9b0c serving capture.
- Correction: only Dataset.__init__/ability; remaining full module AST/search parameters unchanged. No model/weights/threshold/contract changes.
- Evidence:5 scope tests pass;3,385/34,473 scoring-only corpus has exact matrices/published abilities. Old937 >1e-9 mismatches/max0.0039 become0. Intermediate6,852 last-bit mismatches and flawed old-round inventory retained; superseded v2 zero.
- Runtime: five local calls measured, slower canonical path; no efficiency gain claim. See local benchmark.
- Decision: scoped harness correctness correction, no ranking improvement/PIT/OOS acceptance. Legacy score-only evaluate/split/complete-safety policy still unresolved; arithmetic versions cannot be mixed.
- Checks: quick/full PASS, golden unchanged; HK contract SKIP/AU stale baseline explicit. No real outcome metrics, price analysis, blind shadow reads, candidate fitting or release.
- Reproduce: frozen environment.json; pytest test_refit_production_rounding.py and test_refit_registry_dimensions.py; verify_refit_canonical_matrix_corpus_v2.py; benchmark_refit_rounding_v1.py; run_plugin_refit_checks_v1.py. Use fresh versioned outputs; scoring-only input hash/source bindings in check manifest. No commit/push/deploy.

See docs/audits/au-full-model-20261011/REFIT_ROUNDING_AND_GENUINE_PLUGIN_REVIEW.md.
