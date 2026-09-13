# Wong Choi Stage 5 D-Tennis producer engineering checkpoint — 2026-09-13

## Decision

The D-Tennis prediction and settlement evidence builders are locally
implemented and tested, but they are **not connected to the Tennis daily or
settlement workflows**. No database row, prediction snapshot, evidence record,
model, scoring rule, scheduler, Dashboard or Telegram message was changed.
Production integration remains a separate production-adapter release.

## Scope implemented

- `research_evidence.build_prediction_artifacts` accepts the exact in-memory
  feature snapshots, pricing outputs and raw API rows used by one pricing run.
  It emits deterministic v3 feature evidence and one hash-bound raw artifact per
  used response without querying the database or writing a file.
- All eleven current match-winner components are mapped to exact feature paths.
  Dynamic opponent-rank buckets, participant identity, decision inputs, raw
  provider/endpoint identity, source chronology and prediction chronology are
  validated. Unknown components, missing raw rows, future inputs and unpriced
  predictions fail closed.
- A warned non-Elo nudge at probability exactly `0.5` is projected inactive
  because it contributes zero to the current model. Warned Elo backbone inputs
  and any warned component with a non-zero effect remain blocked. This is only
  an evidence projection rule; no Tennis component activation, weight,
  probability or scoring code changed.
- `research_evidence.build_settlement_artifacts` accepts exact settled outcomes,
  prediction cutoff metadata and raw result rows. It emits the existing central
  v2 settlement outcome plus hash-pinned v1 raw-result artifacts. It checks the
  player pair and winner inside the raw response, source identity, participant
  IDs, probabilities and complete prediction/result/cutoff chronology.
- Both builders are pure and deny implicit authority: they do not publish,
  settle, promote a model, mutate input data or grant monitoring-sample status.

## TDD and contract evidence

The prediction producer began with an import failure, then passed its initial
contract tests. A separate RED test proved active warnings were being rejected
before the zero-effect rule was introduced. The final prediction slice has 11
tests, including guards that keep a `0.5` Elo backbone warning blocked and keep
a non-backbone warning blocked whenever its probability is not exactly `0.5`.

The settlement producer also began with an import failure. Its emitted artifacts
are fed directly to the existing central `_outcomes` verifier in the test suite;
the verifier accepts one complete fixture and rejects a winner mismatch,
provider mismatch, pre-cutoff raw result, post-result raw creation, invalid
participant, missing raw row and duplicate prediction. The combined Stage 5
producer slice passed 19 tests, and the full Tennis suite passed 570 tests.

## Read-only live feasibility scan

A read-only scan against the mutable `2026-09-13` local database state observed
60 Sportsbet feature snapshots, two assembly skips, 58 priced predictions and
two unpriced predictions. Two priced rows could produce complete Stage 5
feature evidence. Thirty-two were blocked by an active component with a real
unresolved warning; another 24 were blocked because projecting a zero-effect
H2H nudge inactive left no verified active model component. The central contract
explicitly requires at least one active, sourced component, so these rows must
not be treated as research-ready.

The active-warning inventory at that instant was:

- `head_to_head_edge:low_h2h_sample`: 59;
- `surface_elo_edge:missing_surface`: 32;
- surface and overall `elo_not_as_of`: 11 each;
- surface and overall `rank_seed_elo`: 11 each;
- opponent-rank missing-current-rank warnings: three total.

This rebuild used current mutable database state to test producer feasibility.
It is not historical point-in-time evidence and must never be used as a research
sample or model-promotion claim.

## Production gaps found

- Current daily evidence freezes only `Tennis_Daily_Report.txt`; it does not
  include the compact feature projection and raw inputs supplied to pricing.
- The current prediction evidence recommendation list includes every stored
  prediction, including unpriced rows. A future adapter must define and preserve
  one exact set that matches the feature evidence contract; it must not silently
  rewrite old evidence.
- Across every date from `2026-09-01` through `2026-09-12`, the live database had
  43 to 124 predictions with a result per day, but zero predictions linked to a
  `match_results.raw_response_id`. Existing TennisMyLife and TennisExplorer
  result ingestion writes `raw_response_id = NULL`, so no current result can be
  promoted to a hash-verifiable Stage 5 label even though a winner is stored.
- Current `settle-bets` records a summary settlement without pinning a canonical
  outcome artifact and its original raw result. The new builder cannot repair
  this after the fact when the original raw response was never retained.

## Explicitly not done

- no import or call from `cli.py`, `tennis_daily_schedule.py`, result ingestion
  or settlement code;
- no database schema/data update, result refetch, backfill or historical rewrite;
- no model/component activation, warning semantics, weight, feature value,
  recommendation, bankroll or release-policy change;
- no evidence-store write, commit, push, merge, activation, installer change,
  Dashboard deployment or Telegram notification.

## Required production integration

A separate explicitly approved scope must capture the raw result response before
normalisation and persist its ID with `match_results`, then use the pure builders
before prediction and settlement evidence publication. The adapter must make the
prediction recommendation ID set identical to the feature-evidence row set,
create a canonical append-only bundle, and block Stage 5 research qualification
when any required feature or raw result is missing. Historical rows with null
raw IDs remain unverified unless their exact original response can be recovered
and independently matched; they must not be reconstructed from current state.
