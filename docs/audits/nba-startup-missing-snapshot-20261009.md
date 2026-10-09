# NBA startup missing snapshot — 2026-10-08

Investigated on 2026-10-09 (Australia/Sydney).

## Evidence and cause

- Installed launchd jobs run `/Users/imac/wongchoi-scheduler`, not the current
  `/Users/imac/Antigravity-repo` workspace. Installed checkout HEAD:
  `60c951acd672a811515a2ff0e66112c53b919946`; workspace HEAD:
  `0116c740330db7f02f9d04d2884e211b1d494517`.
- `run-20261007-210006-pregame.json` and the 2026-10-08 00:30 / 06:30
  pregame logs show five official games, `PRESEASON`, and zero discovered
  Sportsbet events. The orchestrator exits 1 without producing analysis.
- Odds discovery checked only competition `6927` in the installed checkout.
  Read-only public API verification confirmed `6927 = NBA` and
  `3079 = NBA Preseason Matches`. The workspace already contained an uncommitted
  change adding competition 3079 and its discovery regression test; both were
  preserved.
- The collector's failure branches returned `None`, so its CLI exited 0 and the
  scheduler logged odds refresh as successful despite zero odds files.
- Pregame creates the analysis directory before discovery. The 2026-10-08 live
  directory contained zero entries. Postgame nevertheless treated its existence
  as a completed analysis requiring a prediction snapshot, causing
  `live_analysis_has_no_prediction_snapshot` on every postgame/startup attempt.

## Repair

- Collector failure paths now return exit 75, including zero extracted games
  and write failures; the CLI propagates that status. Success returns 0 after
  writing files. This enables the scheduler's existing restore-on-failure path.
- Postgame records `dormant: no_prediction_artifacts` for an empty directory.
  Any nonempty analysis directory without a snapshot still fails the existing
  safety gate. No historical prediction snapshot is synthesized.
- Removed only the confirmed-empty installed `2026-10-08 NBA Analysis` directory.
  Reran the installed scheduler with `--mode postgame --date 2026-10-08`, Telegram
  disabled: exit 0, `status=dormant`. Historical failure logs remain intact.
- Permanent source changes are in the workspace; the production checkout has
  not been activated. AGENTS.md requires `/approve SHA` before code activation.

## Validation

- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest
  .agents/skills/nba/nba_daily_auto/tests -q -p no:cacheprovider`: 35 passed.
  Includes a subprocess CLI exit-code test, empty-folder startup/postgame,
  partial/complete missing-snapshot guards, and odds rollback on exit 75.
- Read-only corrected discovery for 2026-10-09: five date-matched preseason
  games (`PHI_BKN`, `WAS_NYK`, `NOP_MIA`, `ATL_SAS`, `SAC_LAL`).
  2026-10-10 returned zero matches at verification time; tomorrow's markets
  were absent from both competition responses then.
- `./檢查.sh --quick`: passed. Existing AU data-contract warnings report a
  stale baseline and an uncovered `preparation_score` field.
- NBA suite in `./檢查.sh`: 51 passed. The standalone
  `python3 .agents/skills/nba/nba_wong_choi/tests/test_nba_pipeline.py` runner
  also passed all 79 checks, including regular/preseason discovery assertions.
- Initial `./檢查.sh`: 13 Python suites passed; HKJC daily auto had 12
  sandbox `PermissionError` failures writing its default log path. Node was
  absent from PATH, so JavaScript tests were skipped. Re-running with
  `WC_HKJC_SCHED_LOG_DIR=/tmp/nba-startup-hkjc-test-logs` and the bundled
  Node directory appended to PATH resolved the HKJC failures (70 passed).
  All 14 Python suites then passed. The Node harness falsely reported failure
  because its `grep '^# (pass|fail)'` expects TAP output and bundled Node uses
  another default reporter. Both Node suites passed when explicitly run with
  `--test-reporter=tap`: 16 Cloudflare tests and 61 static-template tests.
- Final whole-gate run with `WC_HKJC_SCHED_LOG_DIR` redirected, bundled Node
  appended to PATH, and `NODE_OPTIONS=--test-reporter=tap`: exit 0, all 15 suites
  passed. No test harness or unrelated HKJC code was changed. Command output:
  `/tmp/nba-startup-check-final.log`.

2026-10-08 has no saved pregame analysis or prediction to evaluate. It cannot
be truthfully marked as a completed prediction review or training observation.

## Release preparation

Prepared in an isolated worktree on fresh `origin/main`
`60c951acd672a811515a2ff0e66112c53b919946`, applying only the seven NBA/audit
file changes. The current workspace branch has unrelated AU history and is not
used as the release base. Main's UTF-8 replacement decoding in NBA `_run` is
preserved. The Central release dry run classifies this as `automation`, requires
a full gate, and selects only NBA for production synchronization. Automatic merge
and activation are disabled pending immutable-SHA approval.
