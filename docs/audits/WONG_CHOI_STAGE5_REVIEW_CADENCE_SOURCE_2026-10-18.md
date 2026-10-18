# Stage 5 Task 7 review cadence — source-only preparation

## Finding

The uninstalled research-review launchd template wakes daily at Sydney 07:10 only. The unchanged frozen research clock makes weekly reviews due Monday 09:00 and monthly reviews due the first Monday 09:00. With no other scheduled wake, Monday's 07:10 pass is too early; the next daily pass is Tuesday 07:10, 22 hours 10 minutes after the intended slot.

This is a source-template readiness defect, not an assertion that a production research-review job was running late: the installed research-review label was previously observed missing. No production scheduler was installed or changed for this investigation.

## Isolated candidate

Base: `2c7dfe7a328eeec1e7d283163db19cd4d3b5f9a3`; branch `codex-stage5-review-cadence-20261018`; worktree `/private/tmp/wc-stage5-review-cadence-20261018`.

Exact source/test delta:

1. `central_wong_choi/launchd/com.antigravity.central-wong-choi.research-review.plist.template`: preserve daily 07:10 and add Monday 09:00 in `StartCalendarInterval`.
2. `central_wong_choi/install_research_review.sh`: describe both slots in its success message; installation, snapshot, first-pass acceptance, concurrency checks and rollback logic unchanged.
3. `central_wong_choi/tests/test_daily_maintenance.py`: preserve fixed runtime paths/no RunAtLoad assertions; verify both calendar slots, actual frozen clock alignment across Sydney DST boundaries, no early review, weekly/monthly due times, acknowledgement deduplication and no promotion authority.

All three paths are under `.agents/skills/`. This audit is the fourth preservation path. No scoring, model, evaluation ruler/contract, holdout, release policy, production adapter, credential, Dashboard, ledger or bankroll change is included.

## RED / GREEN evidence

- RED (`wc-run-22fdoo9o`): three new/updated cadence checks failed, six existing tests passed. The template had no wake at either frozen Monday 09:00 DST fixture.
- GREEN (`wc-run-tdocojv5`): **80 passed** in 15.50 seconds across all Central tests, existing fake-installer success/rollback/concurrent-write cases and the shared research clock suite.
- Repo quick gate (`wc-run-qaj2vnno`): passed; AU/HKJC goldens unchanged, both actual 60-meeting corpus checks ran. Existing AU neutral track/trial coverage and uncalibrated trial-speed warnings were preserved, not hidden by recalibration.
- Installer tests use temporary fake launchctl/plist destinations; no actual LaunchAgents or loaded job was changed. DST dates are calendar fixtures, not real research pilots or model evidence.

## Authority and remaining acceptance

This is **WIP preservation only**, not a release, deployment or Task 7 acceptance. Scheduler/installer changes are outside the narrow Stage 5 engineering standing-approval scope, so this branch must not be automatically merged or activated under that authority. It is separate from the currently gated 36-path reader release.

Before production use: align with current approved main, run the complete required gate and immutable-scope checks, obtain an explicit scheduler/installer release and activation decision, run the existing first-pass receipt/status checks with all four actual production locks and WARM available, and verify installed plist bytes plus loaded state. Real authorized Telegram and Dashboard acceptance remain separate. A 09:00 wake requests review at the intended time; production preemption/offline guards can still defer it, and completion time is not guaranteed by launchd.

Task 6 power readiness, real Tennis/racing pilots, NBA forward evidence and Stage 5 exit remain open. No full gate or production timing success is claimed for this WIP branch.
