# Tennis Wong Choi Stage 1-7 Plan

## Scope

Build only the API-driven foundation, raw response audit trail, database schema, mock provider, provenance validation, and context feature builders.

Stage 7 now covers ledger, CLV, settlement, and MVP backtesting.

## Decisions

- Database: SQLite through stdlib `sqlite3` for a local MVP.
- Tennis data: mock provider by default; `bsd_tennis` adapter is included for a free token-based JSON API candidate.
- Odds: mock provider by default; `sportsbet` adapter targets structured Sportsbet odds APIs/aggregators, with an explicit scrape fallback only when enabled.
- LLM stats: forbidden. Numeric datapoints must carry provenance or validation fails.
- Pricing: deterministic weighted model only; no LLM judgement.
- Agents: deterministic JSON reviewers only; no external memory and no generated stats.

## Acceptance Checks

- Provider healthcheck runs.
- Mock ingestion stores raw API responses.
- Ranking history and tournament metadata are persisted.
- Feature snapshot contains opponent rank buckets, Elo buckets, tournament level stats, round stats, big match stats, and BO format stats.
- Provenance validation fails on missing provenance, stale odds, or `source_provider = "llm"`.
- Pricing output includes model probability, fair odds, no-vig market probability, edge, minimum acceptable odds, decision, confidence, risk, and stake.
- Agent output includes data quality, form, surface, opponent quality, tournament context, round pressure, serve/return, fatigue/injury, market, and final decision reviews.
- Reporting output reads stored predictions and does not rerun analysis.
- Ledger records bets from stored predictions; settlement requires stored match results and never guesses winners.
