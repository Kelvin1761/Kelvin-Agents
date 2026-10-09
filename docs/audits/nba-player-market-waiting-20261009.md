# NBA player-market waiting and warmup retry — 2026-10-09

Production 21:00 warmup on revision `07a49d4224ee6e0dbdc02fc1ffcb27c6e07c1960`
returned `orchestrator_exit_75:all`. The user received a generic temporary-failure
alert, even though the child had verified `player_markets_not_open`.

The next attempt at 21:00:12 reused the first attempt's moneyline-only JSON and
never crawled again. An incomplete warmup therefore could not observe markets
opening between attempts.

Raw Sportsbet event 11028997 at 21:04 contained four markets: Handicap Betting,
Match Betting, Big Win Little Win, and Total Points. No player markets existed
in the source. Raw state and source metadata are preserved under
`/private/tmp/nba-waiting-market-audit-20261009`. Its SHA256 is
`96606ed4181d3202e88c2df024e792b49720f5d00248971b8e0139a68b254b01`.

This patch:

- emits a structured child result only when every failed game is waiting for
  player markets;
- preserves exit 75 and a partial control-plane state, with an explicit waiting
  reason, waiting-game list, and deduplicated waiting notification;
- keeps real extraction/analysis failures on the original failure path;
- refreshes the source on every incomplete warmup attempt, preserving the
  existing snapshot idempotency and started-game protection;
- recognizes the exact full-game `Handicap Betting` market name, using the
  actual away team's display handicap. Quarter and alternate contracts remain
  excluded.

No weights, model artifacts, betting rules, or publication coverage gates were
changed. Waiting creates no analysis or snapshot and is not success. Preseason
remains shadow NO BET. Full-day live evidence remains pending source markets
and future results. This is a new exact-scope release requiring its own immutable
SHA approval before activation.
