# Tennis Wong Choi

Prices Sportsbet tennis player props from a match model, picks up to 10 精選
a day (one per match), and tracks them as a pre-registered paper forward test
(EXP-20261105-10). No real money until that test passes.

Rebuilt 2026-11-06 (`docs/plans/2026-11-06-tennis-rebuild-log.md`): one
ledger, seven priced families, prices proven identical to the old engine by
replay (`docs/experiments/patches/tennis_rebuild/`).

## Layout (`src/tennis_wc/`)

| Package | Does |
|---|---|
| `ingestion/`, `providers/`, `identity/` | Sportsbet / ESPN / TennisMyLife / TennisExplorer / rankings → SQLite, with event-id, pre-match and identity guards |
| `features/`, `modelling/` | per-player feature snapshots and the match-win model (Elo backbone + nudges) |
| `model/` | serve/hold, simulator, set table, market blend, as-of history reads |
| `pricing/` | prop quotes → ledger rows (`props.price_date`) |
| `select/featured.py` | 精選: one per match, edge → EV → odds, ≤10 a day, frozen at first price |
| `store/` | ledger writes, pricing evidence, result consensus, predictions, manual live bets |
| `settle/` | results fetch and prop settlement |
| `publish/` | report file, Telegram, weekly timing check, dashboard deploy |
| `run.py` | the daily pipeline: `price_day`, `review_day`, `settle_backlog`, `readiness` |

## Commands

```bash
cd tennis-wong-choi
PYTHONPATH=src .venv/bin/python -m tennis_wc.cli --help      # init-db, price, review, featured, record-live-prop-bet
PYTHONPATH=src .venv/bin/python -m pytest -q
```

## Schedule (Sydney, `scripts/tennis_daily_schedule.py`, launchd in `launchd/`)

| When | Job | Telegram |
|---|---|---|
| 21:00 | price tomorrow, record 精選 | main card to Kelvin + Heison (always, 0–10 picks) |
| 23:00 | re-price tomorrow | 補充精選, only if new picks |
| 09:00 | re-price today | 補充精選, only if new picks |
| 18:00 | settle yesterday, ROI board, archive, warm tomorrow; Sundays the timing check | ROI board row (if settled picks); weekly check to Kelvin |
| 10:30, 12:30 | recovery of a failed 09:00 run | failures only |
| every 30 min | near-start price capture for 精選 matches | none |

Install: `WC_TENNIS_RUNTIME_ROOT=<live checkout>/tennis-wong-choi scripts/install_macos_launchd.sh`.

## Provider Notes

- Tennis stats: `bsd_tennis` adapter targets BSD Tennis API (`https://tennis.bzzoiro.com/api`) because its docs currently list free JSON endpoints for tournaments, players, matches, live scores, predictions, and ATP/WTA rankings.
- Historical backbone: `bootstrap-sackmann-history` imports Jeff Sackmann ATP/WTA CSV snapshots into local `player_match_history`, `rankings_history`, and tournament metadata tables. This is the preferred stable source for historical rank-bucket, tournament-level, round, serve/return, and sample-size features.
- **Sackmann backbone is frozen (2026-10-14).** `JeffSackmann/tennis_atp` and `tennis_wta` both return 404 on GitHub; the last imported rows are ATP 2026-05-17 / WTA 2026-05-18 (tourney dates). ATP tour-level history stays fresh through TennisMyLife (`ATP_MAIN`, with serve stats), but **TML carries no WTA**, so **WTA history since ~2026-05 has no serve stats at all** — only tennisexplorer / composite (ESPN) results. Measured read-only on the live DB (distinct WTA matches with `ace_count` and `first_serve_points_won_pct` non-null / all WTA matches): 2026-01 524/778 (67.4%), 02 504/1452 (34.7%), 03 536/934 (57.4%), 04 354/1106 (32.0%), 05 306/876 (34.9%), 06 0/1394, 07 0/2319, 08 0/927, 09 0/2169, 10 0/510 (0.0%). Any WTA serve/return feature or serve-based prop is therefore running on history ≥5 months old. 404s are now stored as `raw_api_responses` rows (`entity_type='match_history_not_found'`, status 404) and surface in run-daily `source_warnings` and the daily health line (`來源錯誤 N · 降級 M`) instead of being dropped.
- **WTA serve stats source:** official WTA match statistics are collected separately. The direct fresh-history candidate was **rejected** in [EXP-20261026-04](../docs/experiments/EXP-20261026-04-tennis-wta-fresh-history.md); collecting more rows does not authorize wiring them into pricing. Legacy serve dates remain a coverage risk. Retain the current source until a separately registered same-corpus evaluation qualifies a replacement. `ingest-wta-stats` collects source observations; it does not promote a model.

- **Sportsbet market restructure (2026-08-23, fixed 2026-10-15, EXP-20261015-05).** Three silent breaks at once, all "empty output, no error": (1) the event page stopped server-rendering every market tab except *Top Markets* — measured 2026-10-15, a WTA 1000 fixture advertised `numMarkets` 52 and rendered 4; weekly stored/advertised fell from 62–73% to 27–38%. `fetch_event_odds` now also reads each tab's `httpLink` (`/apigw/sportsbook-sports/...MarketGroupings/<id>/Markets`, skipping *Top Markets* and the single-game micro tabs), dedupes by market id, and writes `market_coverage` (advertised / page / added / failed tabs) into the stored raw response; live probe on 15 singles: 29% → 90% stored. Opt out with `TENNIS_SPORTSBET_MARKET_GROUPS=0`. (2) Handicap selections lost their brackets (`Name -3.5`, was `Name (-3.5)`), so no game / set / first-set handicap matched a player; `_spread_odds` now reads both, and for the unbracketed Alternative markets (both orientations of every line) keeps one pair per |line| — main market first, then the most balanced pair. (3) `<Player> Total Games 12.5` became `<Player> Total Games`; the registry required the trailing number, so player totals fell into `match_total_games` **and were priced there as match totals at a ~12.5 line** (125 such rows 08-23..10-15, 119 settled, never staked — legacy generic contracts without a saved feed market name are now reported as unverified and excluded by the versioned evidence contract; the original records remain intact). Bracketed / old-key rows keep their old meaning (08-15 re-price is identical). *To win/lose 1st set and win match* is withdrawn by Sportsbet (no tab has it) — `player_first_set_match` is listed in `family_health.WITHDRAWN_FAMILIES`. run-daily now also emits `prop_family_absent` (a family with history that has written nothing inside the 28-day window — the silent check alone loses a family once it has been dead longer than its baseline) and `sportsbet_market_coverage` (< 60% of advertised markets stored, or most events with a failed tab). Bets: nothing about staking changed; the restored families go through the same gates as before.
- Odds: `sportsbet` adapter prefers a licensed/approved structured API. A scrape fallback exists only when explicitly enabled with `SPORTSBET_SOURCE_MODE=scrape` and `SPORTSBET_ALLOWED_SCRAPE_FALLBACK=true`; raw payloads are still stored and invalid/missing odds block betting output.
- NBA Wong Choi reference applied: Python-first extraction, schema-normalised JSON, odds provenance, fake-data firewall, and deterministic math outside the LLM.

## Real Data Setup

Create `.env` from `.env.example`, then set:

```bash
TENNIS_PROVIDER=bsd_tennis
TENNIS_API_KEY=...
TENNIS_API_BASE_URL=https://tennis.bzzoiro.com/api

ODDS_PROVIDER=sportsbet
SPORTSBET_SOURCE_MODE=api
SPORTSBET_API_KEY=...
SPORTSBET_API_BASE_URL=https://wagerwise-odds.com
```

For the explicit Sportsbet scrape exception:

```bash
ODDS_PROVIDER=sportsbet
SPORTSBET_SOURCE_MODE=scrape
SPORTSBET_ALLOWED_SCRAPE_FALLBACK=true
python -m tennis_wc.cli sportsbet-urls --date 2026-05-10
python -m tennis_wc.cli fetch-odds --date 2026-05-10
```

Before real daily analysis, bootstrap the stable historical backbone:


Safety guard: if core Elo inputs are missing, the bet filter forces `NO_BET`.

## Stage Gates

- Stage 1-3: data foundation and feature snapshots.
- Stage 4: deterministic pricing engine and bet filter.
- Stage 5: data-grounded agent reviews that only read feature snapshots and pricing JSON.
- Stage 6: reports and Streamlit dashboard.
- Stage 7: settlement, CLV, backtesting.

## Design Notes

Real provider adapters intentionally contain placeholders. Do not map Sportradar, Stats Perform, Odds API, Betfair, or news endpoints until credentials and exact endpoint contracts are confirmed.
