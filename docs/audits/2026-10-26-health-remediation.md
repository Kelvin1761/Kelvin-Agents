# 2026-10-26 health-check remediation

Base reviewed: `d311735a` (latest origin/main when the fix worktree was created).
This change repairs automation/diagnostics; it does not change scoring, ranking,
weights, evaluation rules, or historical run manifests.

## Reproductions and fixes

- NBA 2026-10-26 09:03 incremental postgame returned `not_due`, exit 0, but the
  canonical adapter recorded `unknown Wong Choi run status`. Explicit mappings
  now cover `not_due`/`no_prediction` (dormant), `updated`/`unchanged` (succeeded).
  The original source status remains in the operation evidence.
- NBA 2026-10-25 nightly review failed repeatedly with `No analysable NBA reports`.
  All eight current reports have valid hash-bound sidecars but zero eligible
  combos. The reflector now accepts this only when every included report has
  an explicit empty combo list and nonempty unpicked candidate legs in a matching
  supported sidecar. It records no DB/training observations or ML evaluation.
  The archive still requires final results covering every report, balanced
  verification, and the existing dashboard no-bet validation. The postgame text
  reports zero recommendations and N/A hit rate, never an invented performance.
- Health checked the old checkout-local NBA DB instead of
  `~/WongChoiData/NBA/nba_reflector.db`. Read-only inspection found 175 legs, all
  settled. The canonical path now has precedence.
- Text-only timestamp scanning counted replayed September Tennis JSON errors
  under “last three days.” The scanner now reads explicit JSON execution times
  or the referenced canonical attempt's execution time. Undated errors are
  reported separately; target dates and file modification times are not treated
  as execution times. Referenced JSON reads are confined to the control run root.
- An unreadable File Provider mirror produced `OK 0/0`. Traversal/stat errors,
  empty paired scans, missing roots, and failed backfill verification now return
  nonzero. Partial scans cannot authorize backfill. Existing freshness semantics
  and size comparison are retained; this is not a cryptographic mirror audit.
- HKJC 2026-10-25 late prerace/startup runs observed all pools closed but still
  re-extracted racecards, then failed on unavailable formguides. Automatic same-day
  prerace now stops when the existing odds capture explicitly returns `closed`.
  Disabled/unavailable odds capture does not imply closure; explicit force remains.
- The COLD message now distinguishes already verified provider copies from the
  remaining unverified artifacts instead of implying that all copies are missing.

## AU warning diagnosis (no model repair warranted)

Command: read `Race_*_Logic.json` in the canonical AU root and `Archive/`, meeting
names dated 2026-10-19 through 2026-10-25; count `python_auto.score_provenance` and
`feature_evidence_state` for every horse with `feature_scores`.

- W43: 3,459 horses; trial weak/missing 2,507, of which 2,505 were explicitly
  `disabled_neutral`. Only 2/954 applicable horses had weak trial evidence.
- Trial disabling is implemented by the existing career-start policy in
  `engine_core._trial_score`; it is not lost extraction evidence.
- Track neutral base moved to 60 in `dd22b05d`; W43 track evidence weak rate is
  138/3,459 (4.0%) despite 32.3% numerically neutral scores. Numeric neutrality
  does not establish missing evidence.
- Trend output now appends the measured disabled share and contemporaneous
  evidence weak rate. Warnings and thresholds remain intact, so actual future
  degradation is not suppressed.

## Validation

- `./檢查.sh --quick`: passed after the changes.
- Final targeted regression run: 187 passed, covering NBA reflector/scheduler,
  control adapter, HKJC scheduler, mirror/log scanning, and field-health trends.
- Full check and immutable release gate results are recorded by the normal Central
  release process; no model evaluation claim is made.

## Operational follow-up

- Drive mirror directories deny this process access (`PermissionError: Operation
  not permitted`), including outside the filesystem sandbox. Backfill remains
  blocked by macOS/File Provider access; it must not be reported as complete.
- Remaining COLD object is the 86,016-byte NBA reflector-runtime-recovery snapshot
  `wc-artifact:2ad4a78e0bff222ab80ce88e`. The WARM object exists. Upload to the
  existing shared Drive archive was rejected by automatic approval review pending
  explicit user authorization for that payload/destination. No upload occurred.
- HOT is approximately 22 GiB free: below the 30 GiB warning floor, above the
  20 GiB critical floor. No original files were deleted.
- Historical SLO failures remain append-only. A repaired future run does not
  retroactively rewrite their outcome.
