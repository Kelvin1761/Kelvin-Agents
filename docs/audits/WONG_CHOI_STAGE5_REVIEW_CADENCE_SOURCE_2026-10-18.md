# Stage 5 review cadence — refreshed 2026-10-22

Restores the isolated engineering payload preserved in `244ac67a` onto main
`18392e05`. The frozen review clock already makes weekly reviews due Monday
09:00 Sydney and monthly reviews due the first Monday at that time. A sole
daily 07:10 wake is too early; the next daily wake is 22h10m late.

Exact scope: the launchd template, its installer's success message, matching
daily-maintenance tests, and this audit. Keep daily 07:10, add Monday 09:00;
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
