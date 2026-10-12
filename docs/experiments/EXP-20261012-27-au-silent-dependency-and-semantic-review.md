# EXP-20261012-27 — Silent dependency correctness and 75-hit semantic review

- Type: isolated import-failure correctness plus source-bound semantic inventory; no model-performance WIN.
- Prior search: scoped experiment records for ImportError/BeautifulSoup/silent failure before hypothesis; EXP12 zero-display and EXP19 swallowed people-cache write failure are separate precedents, not a blanket verdict on all catches.
- RED: 7 new tests, 5F/2P. Missing bs4 returns empty source; actual people refresh silently skips while preserving cache; missing each dump enrichment still writes synthetic one-race/four-runner output.
- Fix: four import fallback handlers removed across three files; exact all-other-AST equality proof and before/fixed witnesses/patches. Normal parser empty source behavior remains; no scoring/weights/profile change.
- Checks: 7 tests GREEN; focused existing people tests, quick, full all return0. Golden unchanged; AU stale-baseline/HK contract SKIP explicit.
- Semantic review:75 original hits source-hash verified and rebound, each has a disposition/rationale/remaining work. Original scan retained; exact current witnesses, duplicate AST occurrence alignment, prior zero/fill fixes recognized. Market11 excluded, no real blind status/results.
- Remaining: all open failure paths and initial scanner blind spots; real extractor/publish/log/refresh/Drive/browser/PIT. Printed runtime enrichment exceptions still tolerated. No complete-pipeline PASS or accuracy claim.
- Failure retained:review script file-loading UTF8 error twice despite decoded bytes/tokenize/AST PASS; explicit cookie only retry succeeded, cause unknown.
- Reproduce: test_missing_parser_and_dump_dependencies.py; review_silent_failure_semantics_v1.py (one-shot witness paths, use fresh versions); run_silent_dependency_checks_v1.py; source_change metadata and exact patches.
- Artifacts: docs/audits/au-full-model-20261011/SILENT_DEPENDENCY_CORRECTNESS_REVIEW.md and SILENT_FAILURE_SEMANTIC_REVIEW_V1.md; original scan and JSON bindings retained.
- Decision: scoped missing-import failure behavior verified; full audit still PARTIAL. No production apply/commit/push/deploy or model promotion.
