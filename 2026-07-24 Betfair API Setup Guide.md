# Betfair API Setup — What Kelvin Does, What I Do (2026-07-24)

Goal: a day-before per-runner exchange snapshot (price + traded volume) for AU
win markets, feeding the money-flow feature and take-SP betting. **I never
handle your credentials** — the client reads them from environment variables.

## Your steps (one-time, ~15 min)

1. **Betfair account** (you likely have one). Must be AU (`.com.au`).
2. **Application Key** — the read-only API key:
   - Log in at https://developer.betfair.com.au/ (Vendor/Developer program), or
   - Use the API-NG Accounts "createDeveloperAppKeys" once. You get a
     **Delayed** key (free, ~1-60s delayed data — fine for day-before) and a
     **Live** key (real-time, may need activation). Start with the Delayed key.
3. Put the three values in your shell (NOT in any file that gets committed):
   ```bash
   export BF_USER='your_betfair_username'
   export BF_PASS='your_betfair_password'
   export BF_APP_KEY='your_delayed_app_key'
   ```

## Then we run (I built it: `scratch/betfair_client.py`)

```bash
python3 scratch/betfair_client.py --selftest    # confirms env, no network
python3 scratch/betfair_client.py --snapshot --hours 30   # → scratch/betfair_snapshot.json
```

Output per AU win market: venue, race start, and per runner
`{name, last_price, best_back, traded_vol}`. That gives the day-before
**market rank** (by price) and **money-flow** (traded_vol) our analysis needs.

## What I wire next (once your snapshot works)

1. Join the snapshot to the day's `Race_X_Logic.json` by (venue, horse) →
   attach `market_rank` + `vol_rank` to each runner.
2. **Union/rescue view**: shortlist = model top-2 ∪ market top-3 (Round 15 —
   keeps Savagery Vibe, adds the market fancies we miss).
3. **Money-flow feature**: vol-rank + model-vs-market gap → standard
   walk-forward gate before it touches ranking.
4. **Take-SP paper-trade log**: record model overlays + BSP result forward to
   tighten the +36% edge CI.

## Security notes

- The client only calls Betfair's own login + read endpoints; credentials go
  nowhere else and are never printed or committed.
- It does **not** place bets. Bet placement stays manual/yours.
- Prefer the **Delayed** app key for research — no reason to use live-data
  keys for day-before analysis.
