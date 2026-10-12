# EXP-20261012-17 — Dashboard registry cache schema

- Date/platform:2026-10-12 Australia/Sydney; shared dashboard parse cache/AU metadata.
- Hypothesis: adding dimension_registry to parsed shape must invalidate a cache that predates it even when report fingerprint remains unchanged.
- Prior: EXP-20261012-10 parser metadata addition; generator source says CACHE_VERSION must bump for shape changes but remains5. No actual cache contents inspected.
- Correction: CACHE_VERSION6 with documented AU metadata shape; no parser/scoring policy or model changes. Shared cache may reparse AU/HK after a future release; model implementations remain separate.
- Evidence: actual old/new cache write/load on isolated stale/fresh/missing/corrupt fixtures, unchanged source fingerprint and preserved old bytes. No live cache read/apply or generate_html/multisport/deploy call.
- Decision: schema correctness, not observed production defect/PIT or ranking improvement. Valid-version corruption/fingerprint collision policy remains separate.
- Checks: final quick/full v2PASS, golden unchanged; no real outcomes/price/blind reads/fit/source CSV mutation/commit/push/deploy.
- Reproduce: frozen environment.json; audit_registry_cache_version_v1.py; source before/after and fixture hashes in registry_display_cache_check_manifest_v1.json. Outputs immutable; new versioned paths for reproduction.

Full review: docs/audits/au-full-model-20261011/REGISTRY_DISPLAY_AND_CACHE_REVIEW.md.
