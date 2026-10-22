# Stage 5 research notification single-attempt transport

## Goal

Preserve the durable research outbox's uncertain-send/reconcile semantics through
the actual shared Telegram helper, without removing ordinary racing retries.

## Tasks

- [x] Inspect deployed call chain: the outbox commits one intent, but the helper
  retries transient POST failures up to four times. A lost response can follow
  server acceptance; invocation deduplication alone cannot prevent duplicates.
- [x] RED: CLI single-attempt and outbox argv tests fail (2 failed, 40 deselected,
  0.31 s; external scratch `wc-run-2dwoa_nd`). No live Telegram request was made.
- [x] Add an explicit helper `--single-attempt` mode, including message/document
  API plumbing; research outbox always selects it. Default racing behavior stays
  unchanged. Existing unconfirmed outcomes still require reconciliation.
- [x] Verify direct CLI, real helper/outbox lost-response integration, ordinary
  retry, recipient/credential isolation, crash/restart and catch-up tests; quick
  gate. Do not equate helper acknowledgement with independent delivery proof.
- [ ] Preserve exact five-path source/test/plan WIP; after the live Tennis and
  queued cadence releases, reconcile current main and use the existing scoped
  controller with fresh full source/clean approval gates and immutable checks.
- [ ] Verify four-domain activation and record actual evidence. This source fix
  does not install a notification scheduler, enable a route, send a message,
  clear old uncertain intents, weaken gates or complete Task 7 acceptance.

## Scope and safety

The five paths are the shared racing helper and its retry tests, the research
outbox and its tests, and this plan. No credentials/configuration, historical
outcomes, model/ruler/holdout, external ledger, bankroll or data deletion change.
No duplicate live release is started while the original Tennis refresh runs.
The original single-attempt implementation prevents application-level retries;
it does not claim exactly-once remote delivery or resolve an uncertain POST.

## Verification checkpoint

Focused outbox/runtime/catch-up and helper tests passed 118 cases in 67.95 s
(`wc-run-bcnn4w47`). After adding the full real-helper lost-response/recreated-
dispatcher case and document CLI default/single-attempt coverage, the final
helper/outbox tree passed 45 tests in 15.78 s (`wc-run-90lsejya`). The first
118-case run is not claimed to include the three subsequently added cases.
The final quick gate passed (`wc-run-9ghmff7j`); scoring goldens are unchanged.
Existing AU sparse/new-field and HKJC stale-calibration warnings remain visible.
No thresholds, historical intents, retries for default racing calls, route
configuration, credentials or delivery-authority claims were changed. Full
source and immutable approval gates are still pending; no production activation
or Telegram message occurred during this verification.
