# Health check triage — 2026-11-02

Reviewed against origin/main `2f262c0c5` and local operational evidence around
09:10–09:25 Australia/Sydney. No scoring, evaluation rules or historical run
manifests were changed.

## Confirmed fixes

- Fast-forwarded the clean primary checkout from `f0c7f36d` to `2f262c0c5`.
  Production was already at `2f262c0c`; its two modified files are generated
  `hkjc_draw_stats.json` and `sb_archive_meeting_ids.json`, not this session's work.
- Added suite-wide AU scheduler log isolation, preserving the existing
  publication-lock isolation. The 2026-11-01 15:52:49 `Randwick: parser exploded`
  error is a simulated exception from `test_meeting_priority_and_alerts.py`.
  Adjacent production-log entries reproduce that test's fake 2026-11-07 venues,
  followed by its `x/y/z` alert tests. Individual test files isolated logging,
  but the shared fixture did not. A regression test verifies that the default
  production log destination is never created by a simulated failure.
  Existing operational logs were retained, including the contaminated entries.

## Outstanding operational work

| Item | Finding and next action |
| --- | --- |
| Drive mirror | The supplied report shows AU 4 stale files and HKJC 98. Both a check and `mirror_consistency.py --backfill` were attempted from the new worktree. macOS returned `PermissionError: [Errno 1] Operation not permitted` for both CloudStorage roots, including outside the sandbox. No files were copied. Restore this application's macOS access to Google Drive, then rerun `python3 .agents/scripts/mirror_consistency.py --backfill` and `--check`. |
| COLD coverage | 34/35 catalog artifacts have verified second copies. The missing artifact is `wc-artifact:2ad4a78e0bff222ab80ce88e`, an 86,016-byte NBA reflector recovery database archived on 2026-10-22 at `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/nba/reflector-runtime-recovery/9bad595328f6/nba_reflector.db`. Complete its second-copy verification when Drive access works. Do not remove its original. |
| Internal disk | 21–22 GiB free during inspection, below the 30 GiB operating floor. Latest main already contains nightly APFS compression and old test-temp cleanup (`23380430`). A read-only compression scan found only 743 eligible files / 0.24 GiB allocated, so rerunning compression alone cannot bridge the gap. No archives, databases or other sessions' worktrees were deleted. A separate concurrent release, `1c9d5d4d`, adds settled AU snapshot offload; assess its operational result separately. |
| AU dashboard size | Genuine operational warning: on 2026-10-31, a 24.9 MiB snapshot exceeded the 24 MiB conservative threshold and had no past AU meetings eligible for removal. `shrink_to_fit()` still has this limitation. A future busy meeting day can reproduce it; reduce or partition the dashboard payload while retaining every current/future race. Distinguish the 24 MiB warning margin from the documented 25 MiB upload ceiling when assessing run errors. |
| Unsaved work | The weekly-review, NBA injury and NBA layer-A worktrees belong to other sessions. Their changes were not staged, committed, reverted or removed. The production dirty files are generated data; their long-term tracked/untracked policy needs separate review. |
| AU contract baseline | Quick gate additionally reports an existing stale AU baseline (`a5b543bb29dd` versus engine `7a45f8f592bc`). This session did not recalibrate against unrelated scoring changes; the owner of those changes should validate and recalibrate the intended baseline. |

## Warnings that do not justify a model change

- NBA startup's latest recorded run is **2026-10-28**, exit 75 for
  `player_markets_not_open`. Today's 08:30 pregame run succeeded at
  `2026-11-01T21:36:40.942405+00:00`. The startup warning is historical.
- AU trial neutral/fallback growth predominantly reflects explicit
  `disabled_neutral`, as the report itself states. No extraction failure was
  established from this warning.
- The 30-day SLO really remains below target: AU 73/97, Tennis 52/58,
  NBA 670/880 at the time of inspection; HKJC 2247/2305 passes. These are
  historical slots, not a claim that every pipeline is currently down.
  Recent unsuccessful slots include NBA lock contention and earlier extraction /
  compile failures, Tennis `analysis_board_missing`, and AU partial runs.
  Keep this evidence intact; investigate recurrence rather than resetting it.
- Latest AU run succeeded; latest HKJC recovery was dormant; Tennis card was
  running within its two-hour timeout; NBA's latest postgame was dormant and
  its latest pregame succeeded. Registered model stages remain AU/HKJC
  production and Tennis/NBA shadow.
- Dashboard/D1 backup status was `ok`, with verified local restore and WARM
  copy, about six hours old. No ledger write or dashboard deployment was made.

## Validation

- Targeted log-isolation and meeting-priority tests: **9 passed**.
- `./檢查.sh --quick`: passed, with the pre-existing AU baseline/neutral warnings.
- Full `./檢查.sh`: **passed**, all 16 suites, on base `1c9d5d4d` plus
  this session's test changes. Log: `/private/tmp/wc-health-full-unrestricted.log`.
  The initial sandboxed full run encountered four NBA relocation failures
  (`ps` denied) and one APFS compression failure. The same 17 related cases
  passed outside the sandbox, followed by the complete successful rerun.

All code changes in this review are confined to AU test fixtures and the
regression test. Release is docs/tests only; no runtime activation is required.
