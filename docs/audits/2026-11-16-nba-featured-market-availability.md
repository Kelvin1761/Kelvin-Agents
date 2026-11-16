# NBA featured O/U availability guard

Base: `7e31a500bfd7187a58bfa61880b6c5e88986d7f3`.

On 2026-11-16 the user could not find Herbert Jones or Toumani Camara assists
O/U bets for the following Sydney day's games. The scheduler's 21:00 files
recorded Jones Under 1.5 @1.96 (event 11171052) and Camara Under 1.5 @1.80
(11171058). Both were absent from the public site's expanded Player Assists
Markets at approximately 23:36 AEDT. The Assists shortcut displayed milestone
ladders, which are a different interface from the All / Player Assists Markets
accordion.

The stored formatted odds do not preserve the market/selection availability
flags at 21:00. Therefore this evidence cannot distinguish subsequent withdrawal
from initial extraction of a hidden/suspended market. Do not describe either
historical price as proven executable, alter the frozen picks retrospectively,
or infer a performance improvement from this repair.

The live public Redux entities expose boolean `active` and `displayed` flags.
The extractor previously ignored both. It now excludes a market or outcome
when either flag is explicitly false, in both price parsing and SGM ID capture.
Historical fixture payloads without flags retain their previous behavior.
A two-way pair cannot survive if either side is excluded. Featured card text
now explains the publication snapshot and where the O/U accordion is located;
users should skip an unavailable original market rather than substitute a line.

This guard checks availability at extraction time. It does not guarantee a
market stays open after publication. No scoring coefficients, featured rule,
frozen records, or settlement rules were changed.

Validation: 58 targeted tests passed, covering hidden/suspended markets and
individual outcomes, valid pairs, SGM IDs, existing ledger behavior, player
market waiting behavior, featured selection and card wording. Repo quick and
full checks are required before delivery.

Commands (from the isolated worktree):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  .agents/skills/nba/nba_daily_auto/tests/test_sportsbet_extraction_failures.py \
  .agents/skills/nba/nba_daily_auto/tests/test_nba_featured_card.py \
  .agents/skills/nba/nba_daily_auto/tests/test_nba_market_ledger.py \
  .agents/skills/nba/nba_daily_auto/tests/test_nba_player_market_waiting.py \
  .agents/skills/nba/nba_engine/tests/test_featured.py
./檢查.sh --quick
./檢查.sh
```
