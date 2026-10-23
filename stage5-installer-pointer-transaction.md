# Stage 5 installer pointer transaction

## Goal

Do not publish the Tennis DB pointer before all production cutover preflights;
restore its exact prior configuration on installer failure without overwriting
a detected concurrent change. Never move, rewrite or delete database contents.

## Context

Cadence `4ce065e9d381872b4a68aba684851f6541a7f3f5` passed source full/push and
immutable approval, then merged. Activation at 2026-10-22T22:19Z failed because
the installer detected an active HKJC/NBA/Tennis automation pattern. Existing
external/plist and Git rollback succeeded to c9. Later approved production has
advanced (observed `8f09e341`); never retry activation by downgrading to 4ce.
The installed calendar still differs from its approved source template.

Diagnosis found a real side effect: the unified installer writes the machine
DB pointer before the active-run/AU preflights and never includes that pointer
in its transactional snapshot/restore. A rejected cutover or later rollback
can therefore leave changed configuration even while launchd plists restore.
This source fix is a genuine installer change, not a no-op to force deployment.

## Tasks

- [x] RED: isolated full-cutover fixtures retain sentinel pointer bytes for
  active-run deferral, failed acceptance and calendar mismatch.
- [x] Publish only after all preflights and after the rollback trap is armed.
- [x] Snapshot/restore the small pointer configuration, bind its exact path,
  reject unsafe files and detected concurrent values; retain legacy snapshots.
- [x] Test success, absent/existing pointer, exact/idempotent rollback,
  concurrent mutation and all existing Central/installer/clock cases; quick gate.
- [ ] Preserve exact source/test/plan scope. Use existing full-gated scoped
  controller on latest approved main, with immutable checks, backups and locks.
- [ ] Verify actual four-domain alignment, installed weekly calendar and native
  receipt after activation; never infer Monday firing or Stage 5 completion.

No active-run guard, gate, deadline, ruler, model, release policy, historical
evidence, credential, external ledger or retention change is authorized here.
Do not stop production, replay old whole files or claim a missing approval as
the cause. Existing failure Telegram was already delivered; avoid duplicates.

## Evidence

RED: 3 failed, 1 passed, 8 deselected in 59.81 s (`wc-run-qj9hqdj4`). All
three failures were sentinel pointer changes despite deferred/failed cutover.
Initial installer GREEN: 13 passed in 85.79 s (`wc-run-soomgm4_`). Final
combined Central/installer/clock tests: 120 passed in 88.87 s
(`wc-run-ncpjd1ef`). Shell syntax and quick gate passed (`wc-run-_kbzbunx`),
scoring goldens unchanged; existing AU sparse/new-field and HKJC stale-baseline
warnings remain. Fixtures explicitly pin the pointer to temporary paths so
snapshot/restore never reads/writes the host pointer or real LaunchAgents.

Snapshot metadata is small, path-bound configuration; absent original pointer
is restored by removing only the candidate configuration introduced by this
transaction, never a DB file. Existing bytes/mode restore atomically when the
current value still matches the owned candidate. Detected concurrent value,
removal, symlink or path-binding mismatch blocks restoration before services
are touched. Legacy snapshots carry no pointer authority and leave it alone.
This is detected-change protection, not a claim of exactly-once filesystem
transactions or power-loss durability. No full release/activation is proven yet.

## Resumption checkpoint

Read-only process inspection confirmed the previously observed other-agent
release controller has ended; no release controller was running at this probe.
Fetched main `08ec7914086e5eea184aa26ce4692c4b90d69e99` has no overlap with
these three paths. Normal merge `9eb24b3708cd9717382b680ad7bb488ded6379bf`
preserves upstream work; the complete candidate delta remains exactly the
installer, its matching tests and this plan. Upstream NBA changes are observed
only, not authored or approved by this session.

Mounted external scratch has 816 GiB available and HOT has 16 GiB at this
checkpoint. Re-run the Central/installer/review-clock suites and quick gate,
then exact-scope preview before the existing full-gated release workflow.
An initial test invocation used the nonexistent `test_research_clock.py` and
exited 4 with no tests run; the corrected suite is
`test_research_review_clock.py`. This invocation error is not a passing gate.
No production install, model change or weekly-calendar acceptance is inferred.

Aligned verification: all Central tests plus runtime installer and review clock
passed **120 tests in 62.61 s** (`wc-run-pmvo32hb`). Repository quick gate passed
(`wc-run-zw6ujn6s`), both 120-horse scoring goldens unchanged; existing data
contract warnings remain visible. Full release and installed acceptance are
still outstanding; proceed only through the existing Central controller.
