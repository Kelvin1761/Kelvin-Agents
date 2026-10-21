# Stage 5 review cadence — refreshed 2026-10-22

Restores the isolated engineering payload preserved in `244ac67a` onto main
`18392e05`. The frozen review clock already makes weekly reviews due Monday
09:00 Sydney and monthly reviews due the first Monday at that time. A sole
daily 07:10 wake is too early; the next daily wake is 22h10m late.

Initial four-path scope: the launchd template, its installer's success message,
matching daily-maintenance tests, and this audit. Keep daily 07:10, add Monday 09:00;
do not add RunAtLoad, change rulers or auto-unfreeze incidents. Production
preemption may still defer completion; a launchd wake is not a timing SLA.

Fresh RED on unchanged source: three schedule/DST tests failed (six other tests
deselected). The tests compare the actual frozen clock across both Sydney DST
boundaries, refuse early reviews, require weekly/monthly due-time identity,
and preserve acknowledgement deduplication and false promotion authority.
Historical old-base 80-test/quick results are not reused as current gate evidence.

Kelvin authorized completed session engineering releases, including scheduling
and installers, on 2026-10-22. A separate full gate, immutable recheck, existing
allowlisted installer snapshot/rollback and actual loaded-plist verification
are still required. Do not edit installed LaunchAgents directly or deploy in
parallel with the currently running Tennis release controller. No live DB,
ledger, historical evidence, model, ruler or bankroll change is included.

Fresh GREEN: all Central tests plus the shared frozen-clock suite passed
83 tests in 1.24 seconds. Fresh quick gate passed with unchanged AU/HKJC
goldens and real 60-meeting data-contract checks; sparse/new-field AU and stale
HKJC calibration warnings remain visible. External quick scratch:
`wc-run-d4wxxyoe`. Installer tests use fake destinations/launchctl, not live
LaunchAgents. Full gate, release and live installed schedule acceptance remain
pending. Preserve this as a non-main WIP until the existing Tennis controller
is terminal and a separate current-main release is fully verified.

## Installed-calendar postcondition

Read-only inspection confirms the live job still has only daily 07:10. The
existing policy syncs the initial template delta without selecting an installer;
source merge alone therefore cannot prove Task 7 timing acceptance.

Scope is extended to eight paths with the existing allowlisted
`install_production_runtime.sh`, a standalone standard-library read-only
`scripts/verify_research_calendar.py`, its Central tests, and matching shared
`test_runtime_installer.py` fixtures. This is not a policy/allowlist edit or
a no-op installer change: after installation the unified installer now checks
the actual installed calendar against its source before setting COMPLETED.
Mismatch exits into the existing transactional rollback; generic path/loaded
verification still runs afterward. Keep all production preflights and backups.

The verifier rejects missing/extra/wrong/duplicate slots, invalid values,
unexpected labels/RunAtLoad, symlinked files, oversized/nonregular files and
mutation during bounded reads. It normalizes slot ordering and dictionary vs
single-entry array syntax. It cannot itself prove launchd fired on Monday or
that a review finished on time; loaded-state and native-receipt checks remain.

Fresh verifier RED was a missing module before implementation. Central/clock
tests then passed 99 cases. Calendar plus real transactional-installer fixtures
passed 26 cases after exercising missing-wake rollback. The first unprivileged
installer invocation had three failures/23 passes because sandbox permissions
blocked candidate-worktree log directories, not because real launchd failed.
The identical isolated-HOME/fake-launchctl suite passed 26 after permission was
granted; no assertion, deadline or fixture size was relaxed. A read-only check
against the actual installed daily-only plist correctly returned blocked/exit 1.
No production installer was invoked for these checks. Fresh full gate and
eight-path release dry-run are still required before activation.

Latest combined verification passed 109 Central/clock/isolated-installer tests
in 31.86 seconds. Quick gate passed (`wc-run-qckclzzs`). Dry-run then proved
exactly the eight-path union, risk automation/full gate, all four runtime
targets, the existing unified installer, no Dashboard deploy and no manual
reason. Policy files are unchanged. These are pre-release checks: full gate,
immutable approval recheck, installer snapshot/install/rollback and actual
loaded calendar/native-receipt acceptance remain open.
