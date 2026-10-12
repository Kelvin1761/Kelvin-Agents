# EXP-20261012-08 — Result reader boundaries

Status: bounded compatibility/metadata verification; G2 PARTIAL. No model-performance claim.

Hypothesis: source-bound identity repair and dated missing-value fill remain readable by actual independent CSV consumers without altering nonmissing values or label identity.

See ../../docs/audits/au-full-model-20261011/RESULT_READER_BOUNDARY_REVIEW.md for results, limitations, retained failures and remaining work. Five readers: original 0/25, both repaired views 25/25. 57,027 missing-value fills; Trainer/runner Time remain absent. Retest date count remains25 and is not PIT evidence. No price analysis, candidate fitting or shadow reveal.

Reproduction uses the saved verify_result_reader_boundaries_v2.py and verify_result_operational_readers_v1.py with environment.json and frozen source/view hashes. The boundary collector requires a fresh output directory: preserve existing outputs before any separately versioned rerun. Operational fixtures consume the existing three versioned views. Current ./檢查.sh --quick and ./檢查.sh both exit0, with HK data skip/AU stale warning explicit. The invariant artifact independently compares identity/combined cells; only empty-string/em-dash original cells change.

Baseline SHA: 0328f13a9564c787837e3c4aa1cfff19235c9b0c. Source/code/environment/check hashes: result_reader_check_manifest_v1.json. Prior fixture import/API failures retained. No production/release/commit/push.
