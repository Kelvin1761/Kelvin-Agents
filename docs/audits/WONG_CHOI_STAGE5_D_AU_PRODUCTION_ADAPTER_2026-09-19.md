# Wong Choi Stage 5 D-AU production adapter checkpoint — 2026-09-19

## Decision

The D-AU metadata producer is now connected locally to the existing AU
prediction and settlement evidence steps, with fail-closed tests. This is a
release candidate only: it has not been committed, pushed, merged or activated,
and the running AU production checkout was not changed.

## Exact behaviour added

- Before a future AU prediction decision is recorded, the scheduler builds
  `AU_Research_Feature_Provenance.json` at the same timezone-aware cutoff used
  by the immutable snapshot.
- The snapshot now hash-pins Racecard, Formguide, Facts, Logic, scoring outputs,
  `odds_history.json` and the generated projection. The source meeting folder is
  not rewritten by the producer.
- The projection selects only the earliest `analysis` odds snapshot at or before
  cutoff. A morning refresh is never substituted. Missing analysis odds remain
  explicit `missing_analysis` evidence with
  `model_promotion_allowed=false`; they do not stop ordinary AU prediction
  publication or masquerade as market-complete research evidence.
- Future AU settlement evidence must include both
  `Race_Results_Reflector.md` and the event reflector report. Missing either
  artifact fails the evidence step and makes the run retryable.
- Morning review now records settlement evidence for meetings it archives; this
  closes the previous path where only the evening orchestration called the
  settlement evidence step.

## TDD evidence

The RED phase reproduced five production gaps: missing source/projection files
in the snapshot, no explicit missing-analysis projection, settlement evidence
pinning only the rendered report, missing canonical results being accepted, and
morning archive review not calling settlement evidence.

After the minimal adapter change:

- `test_stage5_production_adapter.py`: 5 passed;
- producer/consumer focused slice: 30 passed;
- full AU daily automation suite: 349 passed before the morning-path addition;
  the complete suite is rerun by the repository gates below.

## Read-only production-corpus checks

No production file or evidence record was written.

- `2026-09-18 Newcastle Race 1-8` produced an in-memory projection covering
  8 races, 84 horses and 1,596 feature entries; all 8 races had earliest
  analysis odds; both canonical settlement artifacts resolved; promotion
  remained denied.
- A bounded scan of the latest 24 archived meetings found 21 market-complete
  meetings and three explicit `missing_analysis` meetings. This evidence caused
  removal of an initially over-strict adapter check that would have blocked an
  entire AU Dashboard publication when one meeting lacked prices. The final
  design preserves incomplete market provenance without silently replacing it
  or granting research authority.

## Safety boundaries

- no AU score, feature value, weight, grade, recommendation or odds policy was
  changed;
- no evaluation ruler, holdout, power profile or model stage was changed;
- no Dashboard, Telegram, launchd, installer, betting, bankroll or external
  ledger code was changed;
- no historical snapshot or settlement was rewritten or backfilled;
- existing historical evidence remains unchanged and may remain insufficient;
- the adapter can only improve evidence for runs observed after activation.

## Release status and required approval

This scope is production scheduler code and therefore requires a separate
full-gate code release and immutable human approval. Activation must wait until
all four domain runs are inactive, the three already merged Stage 5 releases
have activated in order, and production rollback state is clean. After future
activation, the first live AU prediction and settlement pair must be inspected
before D-AU real-evidence acceptance is recorded.
