# Wong Choi Stage 5 D-HKJC production adapter — 2026-09-19

## Decision

The HKJC Stage 5 producer is now wired into a locally tested production-adapter
candidate. It is not committed, pushed, merged or activated. Production and
historical evidence remain unchanged until an immutable automation release is
separately approved.

## Adapter behavior

- Future successful pre-race runs build a canonical create-only
  `_prediction_snapshots` bundle before evidence publication and Dashboard
  deployment. Existing `Prediction_Snapshots` folders and their legacy helper
  remain readable and are never rewritten.
- One timezone-aware cutoff is shared by the canonical manifest and
  `HKJC_Research_Feature_Provenance.json`.
- The bundle hash-pins Facts, racecards, structured trackwork JSON, Logic,
  scoring and analysis outputs. The projection binds every scored feature to
  its allowlisted source and always carries `model_promotion_allowed=false`.
- Recommendations come only from the canonical `HKJC_Auto_Scoring.csv`, avoiding
  duplicate rows from per-race scoring files. A missing or unparseable canonical
  meeting scoring artifact fails closed.
- Missing or mismatched feature metadata fails before prediction evidence and
  before Dashboard deployment. It does not silently create a research sample.
- Future settlement evidence requires and pins exactly one `*全日賽果.json`
  together with `HKJC_Reflection_Report.md`. Missing or ambiguous result truth
  leaves settlement pending and prevents the post-race Dashboard refresh for
  that meeting.

## TDD evidence

The initial RED run produced five failures: no canonical adapter entry point,
no publication block for missing feature metadata, settlement pinned only the
reflection report, and missing full-day result truth did not block settlement.
After the minimum scheduler wiring, the adapter, scheduler and producer slice
passed 39 tests. A second RED test proved the first version still accepted
per-race scoring when the canonical meeting scoring file was absent. The final
implementation now rejects that case and the same slice passes 40 tests.

The broader HKJC daily plus shared immutable-snapshot, HKJC provenance and HKJC
settlement-source slice passed 111 tests after the canonical-scoring tightening.

## Final validation

- `./檢查.sh --quick`: passed; AU and HKJC golden fixtures remained identical.
- `./檢查.sh`: passed every suite. Relevant totals include HKJC 119, HKJC daily
  88, HKJC extractor 61, HKJC reflector 48 and shared Wong Choi 1,213 tests.
  AU, Tennis, NBA, Dashboard and the remaining shared suites also passed.
- AU and HKJC data-contract checks were explicitly skipped by the gate because
  this isolated worktree has no configured scored-race corpus. The real-data
  smoke above independently exercised the production HKJC artifact shape.

## Real-data smoke

A copy of the completed production meeting `2026-09-13_ShaTin` was exercised in
`/private/tmp`; the production meeting itself was not written. The candidate
created a `wong-choi-prediction-snapshot/v1` bundle containing 74 files and:

- 10 Logic files;
- 139 horses;
- 2,363 hash-bound feature entries;
- 50 recommendations, all sourced only from `HKJC_Auto_Scoring.csv`;
- both settlement artifacts: `2026-09-13_ShaTin_全日賽果.json` and
  `HKJC_Reflection_Report.md`;
- `model_promotion_allowed=false`.

The temporary copy was removed after the smoke test. The production meeting has
no `_prediction_snapshots` folder and remains unchanged.

## Explicitly unchanged

- no scoring, feature value, weight, grade, Gold/Good ruler or model stage;
- no evaluation contract, holdout, bankroll or promotion decision;
- no historical snapshot rewrite or evidence backfill;
- no Dashboard code or deployment;
- no scheduler installer, launchd plist, credential, deletion or migration;
- no production evidence/state write;
- no commit, push, merge or activation in this checkpoint.
