# Codex pending-work resolution — 2026-10-14

This release consolidates the eligible changes recovered from older Codex worktrees onto origin/main f10e221d after refreshing the initial 63c2e138 base. It includes the previously pushed 2ed4feac candidate, with the following additional repairs:

- Dashboard builds and uploads share a machine-wide lock; a zero Wrangler exit alone does not count as a successful deployment. The current Stage 5 research view preserves existing navigation and validates evidence receipts.
- Quiet-hour jobs retain their logical date, slot, attempts and cooldown across deferral. The transactional installer updates the AU evening job and deferred jobs; runtime verification checks installed triggers, NBA roles and the host timezone.
- Tennis result ingestion retains decoded provider responses and binds their raw IDs into current settlement evidence. Conflicting native winners fail closed. Existing current prediction and settlement integrations remain authoritative.
- The Stage 5 history reader uses bounded pages and a phase-local verified evidence snapshot. Its original 1,300-record, 5,000-plus-reference tests and 600-second child limits remain intact.
- Both initial release gates and immutable rechecks retain stdout and stderr outside their disposable checkout, including the exact SHA and exit code.

## Evidence and limits

The earlier immutable recheck failure for 2ed4feac was not reproduced: a new checkout without local data-root markers passed all 15 suites. The original cause remains unknown; log retention makes any subsequent failure inspectable. This is not a claim that an unidentified source bug was fixed.

Before integration, the Dashboard worker passed 255 Python and 82 Node checks, the scheduling worker passed 57 shared/scheduler, 9 installer and 204 domain checks, and the Tennis worker passed 88 checks. The integrated quick gate and 17 release approval/automation checks passed. Final release gates and activation are recorded separately in the immutable release manifest and append-only events.

No model weights, scoring formulas, evaluation thresholds or rejected model experiments are promoted by this consolidation. Old Tennis prediction-v2 and settlement-v1 worktree prototypes were superseded by current implementations and were not restored. Fixture history-reader coverage does not complete the remaining Stage 5 live native-corpus work or model pilots. Tennis raw evidence is the stored decoded response, not a byte-identical HTTP transport capture; unresolved provider identity aliases remain unverified.

## Recovery

The original primary checkout is retained at local preserve/main-checkout-20261014 (adcfef7863f11479aa98e577e871e6d5b92b682c), with an independently verified Git bundle. Dirty patches and loose files from the older worktrees are preserved under /Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-worktree-cleanup-20261014/. Rejected experiments and private runtime artifacts stay in recovery storage.

An integrated initial full gate subsequently returned failure before staging. Its output was lost by the original prepare-release path; that path now uses the same tested log retention as immutable rechecks. A diagnostic rerun of all 14 non-shared suites passed. Final full gates remain mandatory, including the large native corpus cases.

The latest main refresh also preserves the concurrent Tennis T0 closing-price corrections and HKJC result-backed jockey/trainer reconciliation. The focused shared diagnostic passed 1,626 checks (six large cases deferred to the full gate).
