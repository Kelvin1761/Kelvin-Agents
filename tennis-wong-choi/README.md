# Tennis Wong Choi

API-only tennis pricing engine for ATP/WTA match-winner analysis.

This MVP implements Stage 1-5:

- Provider interfaces and mock providers
- Raw API response storage
- SQLite schema and entity mapping
- Rankings history and tournament metadata
- Data provenance validation
- Opponent rank bucket, tournament level, round, big-match, BO format, and Elo bucket feature builders
- Feature snapshot builder
- Weighted probability pricing
- Fair odds, no-vig market probability, edge, minimum acceptable odds
- Bet filter and stake sizing
- Data-grounded deterministic agent reviews
- CLI and unit tests

The system refuses LLM-generated statistics. Numeric features must be backed by provenance from an API response or stored API snapshot.

## Quick Start

```bash
cd tennis-wong-choi
python -m tennis_wc.cli init-db
python -m tennis_wc.cli config-check
python -m tennis_wc.cli provider-smoke --provider tennis --date 2026-05-08 --tour ATP
python -m tennis_wc.cli provider-smoke --provider odds --date 2026-05-08
python -m tennis_wc.cli run-daily --date 2026-05-08
python -m tennis_wc.cli predict-daily --date 2026-05-08
python -m tennis_wc.cli run-agents --date 2026-05-08
python -m tennis_wc.cli generate-report --date 2026-05-08
python -m tennis_wc.cli performance-report
python -m tennis_wc.cli record-bet --prediction-id 1 --odds 2.08 --stake 0.5
python -m tennis_wc.cli fetch-closing-odds --date 2026-05-08
python -m tennis_wc.cli settle-bets --date 2026-05-08
python -m tennis_wc.cli backtest --start 2026-05-08 --end 2026-05-08
python -m tennis_wc.cli fetch-event-odds --event-id SPORTSBET_URL_OR_EVENT_ID --match-id 1
python -m pytest
```

The default provider is `mock`, so no paid API keys are required.

## Provider Notes

- Tennis stats: `bsd_tennis` adapter targets BSD Tennis API (`https://tennis.bzzoiro.com/api`) because its docs currently list free JSON endpoints for tournaments, players, matches, live scores, predictions, and ATP/WTA rankings.
- Historical backbone: `bootstrap-sackmann-history` imports Jeff Sackmann ATP/WTA CSV snapshots into local `player_match_history`, `rankings_history`, and tournament metadata tables. This is the preferred stable source for historical rank-bucket, tournament-level, round, serve/return, and sample-size features.
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

```bash
python -m tennis_wc.cli bootstrap-sackmann-history --start-year 2025 --end-year 2026
python -m tennis_wc.cli build-sackmann-elo
python -m tennis_wc.cli calibrate-sackmann-elo --start 2025-01-01 --end 2026-04-30
python -m tennis_wc.cli fetch-upcoming-matches --date 2026-05-10
python -m tennis_wc.cli fetch-odds --date 2026-05-10
python -m tennis_wc.cli build-features --date 2026-05-10
```

Safety guard: if core Elo inputs are missing, the bet filter forces `NO_BET`.

## Stage Gates

- Stage 1-3: data foundation and feature snapshots.
- Stage 4: deterministic pricing engine and bet filter.
- Stage 5: data-grounded agent reviews that only read feature snapshots and pricing JSON.
- Stage 6: reports and Streamlit dashboard.
- Stage 7: settlement, CLV, backtesting.

## Design Notes

Real provider adapters intentionally contain placeholders. Do not map Sportradar, Stats Perform, Odds API, Betfair, or news endpoints until credentials and exact endpoint contracts are confirmed.
