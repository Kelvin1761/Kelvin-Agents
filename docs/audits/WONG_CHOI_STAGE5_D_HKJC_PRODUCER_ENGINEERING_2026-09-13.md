# Wong Choi Stage 5 D-HKJC producer engineering checkpoint — 2026-09-13

## Decision

The metadata-only D-HKJC building blocks are locally implemented and tested,
but they are **not connected to the HKJC production scheduler**. No prediction,
settlement, scoring, Dashboard, Telegram, model, ruler or production state was
changed. Scheduler integration remains a separate production-adapter release.

## Scope implemented

- `hkjc_research_evidence.build_feature_projection` reads one completed HKJC
  meeting and emits deterministic bytes with `model_promotion_allowed=false`.
- Each feature is bound to an allowlisted source family rather than every file:
  draw uses the racecard, trackwork uses the structured trackwork JSON, and the
  remaining current HKJC features use the pre-race Facts artifact. Every source
  reference includes its filename, digest, cutoff, race, horse, feature and
  derivation identity.
- Unknown feature identities, missing feature-specific inputs, duplicate inputs,
  invalid event/folder identity, naive cutoff, empty Logic and unscored input
  races fail closed. The producer never edits its meeting folder.
- `settlement_artifacts` requires exactly one `*全日賽果.json` plus
  `HKJC_Reflection_Report.md` from the same event folder.
- The shared HKJC read-only consumer accepts the new hash-bound projection while
  preserving legacy snapshot readability. It rechecks the projection digest,
  event/cutoff, exact Logic-file digests, exact horse sets and source artifacts.

## TDD and real-data evidence

The first RED run failed during collection because the producer did not exist.
After the pure producer was added, its 8 contract tests passed. The second RED
run then proved the old shared reader treated the projection as a source input,
left legacy Logic unupgraded and did not reject a forged projection binding.
After the reader change, the combined producer/consumer slice passed 19 tests.

A read-only smoke against `2026-09-13_ShaTin` built an in-memory projection for
10 races, 139 horses and 2,363 feature entries. Every current feature identity
and required source resolved, and promotion remained false. Nothing was written
to the meeting, production evidence store or scheduler state.

## Production gaps found

- The live HKJC `create_prediction_snapshot` still emits its older schema using
  `platform`, `meeting`, `size` and `Prediction_Snapshots`. Stage 5 research
  verification requires the canonical append-only manifest fields and byte
  projection. Existing historical snapshots remain untouched; future integration
  must create a new canonical snapshot rather than rewrite history.
- Current HKJC settlement evidence pins only `HKJC_Reflection_Report.md`; it does
  not pin the canonical full-day results JSON required for label authority.

## Explicitly not done

- no import or call from `hkjc_daily_schedule.py`;
- no replacement of the current snapshot implementation;
- no new immutable production snapshot or settlement record;
- no historical backfill or reinterpretation of old snapshots;
- no scoring, feature value, weight, recommendation or model-stage change;
- no commit, push, merge, activation, installer or Dashboard deployment.

## Required production integration

As a separate explicitly approved scope, future HKJC pre-race publication must
build the compact projection and admit it together with Facts, racecards,
structured trackwork, Logic and scoring outputs into a canonical create-only
snapshot before evidence publication. Future settlement must pin both the
canonical full-day result JSON and reflection report. Any missing or mismatched
metadata must block research evidence/publication rather than silently qualify
an unverifiable Stage 5 sample.
