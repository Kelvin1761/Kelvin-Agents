# NBA live pipeline test — 2026-10-09

Result: **FAILED at player data extraction (exit 1)**. The deployed startup/snapshot fix does not establish that the complete NBA pipeline is healthy.

## Test scope

- Approved/deployed revision: `1c77d21f6ab0786500e0ad6d689b7d5ca4cd838d`.
- Isolated checkout: `/private/tmp/nba-full-run-test-20261009-p4bn034y/checkout`.
- Actual upcoming preseason game: HOU–DAL, 2026-10-09 23:10 Australia/Sydney.
- Command: `python3 .agents/skills/nba/nba_orchestrator.py --date 2026-10-09 --game HOU_DAL --auto --skip-cloudflare-deploy`.
- Telegram/deployment disabled; archive/control roots redirected to the temporary test directory. No production prediction snapshot, dashboard publication, or external settlement was created.
- This tested one game's live pipeline, not whole-day schedule coverage or postgame settlement.

## Observed stages

| Stage | Result |
| --- | --- |
| Sportsbet extraction | Passed; three target-date odds files written |
| Selected HOU–DAL player extraction | Failed; every selected player's L10 gamelog empty |
| Analysis and validator | Not reached |
| SGM and Banker | Not reached |
| Immutable prediction snapshot | Not reached |

The extractor was rerun with its complete diagnostic output captured. It again exited 1 at the explicit all-players-missing-L10 quality guard. That guard correctly prevented publication.

## Confirmed causes and limits

The roster API was reachable: live current-season requests returned 18 Houston players and 20 Dallas players. `nba_api` was installed and available. The detailed extractor log also showed zero current-season team, player advanced, and defender statistics.

`fetch_player_gamelog` requests regular-season and playoff logs without an explicit season; the installed API defaults to `2026-27`. A bounded live check for Kevin Durant (player ID 201142) returned zero regular-season games for `2026-27` and 78 for `2025-26`, latest dated April 10, 2026. This demonstrates a preseason/history-selection gap, rather than proving an API outage. The extractor does not currently carry previous-season history into L10 extraction. No historical data was substituted during this test.

The chosen game's Sportsbet data contained moneyline prices 1.72/2.10 and empty points, rebounds, assists, and threes categories. Player props were unavailable at collection time (13:08:52 Sydney). This is an additional prerequisite for completing a player-prop analysis; fixing the history-selection gap alone cannot manufacture those markets.

No scoring parameters or data-selection code were changed as part of this test. NBA remains **not fully verified**. A subsequent fix needs explicit historical-data provenance, preseason NO BET behavior, and another live run after player markets are available.

## Raw evidence

- Orchestrator: `/private/tmp/nba-full-run-test-20261009-p4bn034y/full-run.log`
- Complete extractor diagnostic: `/private/tmp/nba-full-run-test-20261009-p4bn034y/extractor-detail.log`
- Machine-readable outcome: `/private/tmp/nba-full-run-test-20261009-p4bn034y/RESULT.json`
- Test isolation metadata: `/private/tmp/nba-full-run-test-20261009-p4bn034y/TEST_RUN.json`

The temporary evidence files should be retained if further debugging is needed. This report is uncommitted.
