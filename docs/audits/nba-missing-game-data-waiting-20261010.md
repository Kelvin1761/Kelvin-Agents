# NBA missing game data waiting — 2026-10-10

Fresh raw Sportsbet regular and preseason competition feeds contain seven of the eight ESPN games for Sydney October 11. DAL_HOU is scheduled at 21:00 Sydney. The only Dallas/Houston Sportsbet event is October 22; it is not a valid substitute. Raw evidence is retained in `/private/tmp/nba-missing-sportsbet-20261010`.

The full-day orchestrator still stops before analysis, compilation and snapshot publication when official games lack valid Sportsbet data. Missing-only coverage now emits an explicit `waiting_game_markets` / `sportsbet_game_data_missing` payload with the missing tags and exit 75. Unexpected games remain a hard failure. The scheduler records this as partial waiting and notifies which data is missing, instead of hiding the cause behind `orchestrator_exit_1:all`. Source/network/parser failures without a verified waiting payload retain normal failure handling. No odds, reports or official prediction snapshots are fabricated.

Tests cover the full-day orchestration stop, scheduler propagation, partial rather than success/failure records, actionable notification, and rejection of invalid waiting payloads. Final gate and activation results are retained by the immutable release workflow; successful full-day pregame and postgame evidence still requires all source data.
