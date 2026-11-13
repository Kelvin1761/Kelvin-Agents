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
- [x] Preserve exact five-path source/test/plan WIP; after the live Tennis and
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


## November 13 resumed integration: explicit Central notification pass

The user's deleted Codex automations remain deleted. This checkpoint connects
Central's real entry point to the existing supervised notification catch-up
workflow; it does not install or enable any scheduler or route.

`central_research_review.py --notify-catch-up` is mutually exclusive with review
initialization/status and is separate from ordinary review execution. It consumes
only the existing `WC_RESEARCH_NOTIFY_*` worker route environment when explicitly
selected. No recipient or token is accepted from review records or CLI switches.
The route remains disabled by default; existing deployment configuration and
recipient authorization are still required. No credentials/configuration are
created or changed. Existing HOT outbox and WARM/registry roots are required.

One invocation visits each configured domain once, scanning at most 10 records
per domain by default (explicit bound 1..50). Each page uses the actual existing
ResearchNotificationRunner/supervisor, production locks, resource checks, durable
outbox and single-attempt Telegram helper. A shared total time budget caps later
pages; no domain is automatically retried. Uncertain existing/new sends remain
reconcile-required, including in the overall CLI result, and never become
independently confirmed delivery. One domain exception cannot erase the other
outcomes; only its exception class is reported to avoid leaking transport text.

Isolated RED tests reproduced the absent entry (6 failures) and the initial
aggregate-success/reconciliation mismatch (1 failure). Integration tests exercise
real supervisor/worker/outbox using a local fake helper and verify that a second
pass does not send the same receipt again or rewrite review receipts. Other
checks cover disabled-before-allocation, mixed CLI modes, route environment
consumption, credential-free output, per-domain failures and total budget.

This is additional source-only WIP on the existing notification branch, requiring
reconciliation with the forward branch's newer runtime guards before release.
The original cadence sequencing, full source/clean immutable approval gates,
exact-scope release requirements and live notification acceptance remain open.
No live Telegram, installer, job/configuration, model/data/history, release,
merge or activation is authorized by this checkpoint's test results.

The same previously authorized read-only reviewer found that a timeout/preemption
after durable intent creation could be hidden behind aggregate deferred/partial
status. A real supervised helper-hang reproduced it (1 failed, 8.56s). The entry
now marks every attempted non-success phase and exception as reconciliation
required, retaining the original per-domain status/disposition. Proven
pre-allocation deferrals and unattempted budget exhaustion remain distinct. The
actual interrupted pass followed by a normal pass preserves one helper attempt
and reports reconciliation instead of confirmed delivery. The same reviewer
confirmed this correction by source inspection only; no independent tests or
installation authorization were provided. Final focused entry selection passed
14 cases in12.62s. Quick/golden checks passed. Full affected regression evidence
is recorded below after the final source run; the earlier167-pass run predates
this correction and is not final-source evidence.

Final same-source Central entry, supervised runtime, catch-up, durable outbox and
shared-helper regression selection: **168 passed in127.44s**. Log:
`/private/tmp/stage5-notification-entry-final-reviewed.log`; retained external
scratch was selected by the standard external-run wrapper. Final quick check:
`/private/tmp/stage5-notification-entry-quick.log`; diff check passed and scoring
goldens unchanged. No full repository/source or clean immutable release gate was
run for this unmerged checkpoint. The exact additional scope is Central review
entry, its tests, and this existing plan; previous five-path transport WIP remains
included in the branch history. Same authorized reviewer was reclosed. No deleted
Codex automation was recreated.
