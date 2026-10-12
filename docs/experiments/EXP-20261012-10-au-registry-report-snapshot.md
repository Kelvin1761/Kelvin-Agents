# EXP-20261012-10 — AU registry report/snapshot integration

Status: structural metadata integration; Phase A/G3 PARTIAL. No model improvement claim.

New report captures versioned/hash-bound AU spec; actual dashboard parser and JSON model retain it. Legacy reports remain unknown. Eight tests including registry-only dimension in a fresh copied package reach actual engine/report/parser/eval. Full captured3,385-race/34,473-runner mapper/composition/verdict/report-body/dashboard equivalence passes. No fit/outcome/price/shadow analysis.

See ../../docs/audits/au-full-model-20261011/REGISTRY_REPORT_SNAPSHOT_REVIEW.md for source bindings, scope/remaining acceptance and retained failures. Reproduce with frozen environment.json and saved verify_registry_transport_corpus_v2.py; requires a fresh versioned output/work directory. Targeted command: python3 -B -m pytest -q Horse_Racing_Dashboard/backend/tests/test_au_registry_transport.py -p no:cacheprovider. Generator and required quick/full wrapper saved as run_registry_transport_checks_v1.py. All hashes/checks bound in registry_transport_check_manifest_v1.json.

Baseline SHA0328f13a9564c787837e3c4aa1cfff19235c9b0c. No scoring/contract/golden/production/profile change, release, commit or push. Arbitrary new leaf and full registry/parameter/shadow lifecycle integration still pending.
