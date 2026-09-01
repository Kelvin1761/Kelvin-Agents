# Tennis Wong Choi

Python tennis pricing engine for ATP/WTA match and player-prop analysis.

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
- Extensible player-prop registry and settlement for player aces, double
  faults, player games won, player to win at least one set, first-set winner,
  full-match game handicap, set handicap, and BO3 exact set score
- Per-family model-vs-market scorecards and evidence-gated recommendations
- Data-grounded deterministic agent reviews
- CLI and unit tests

The system refuses LLM-generated statistics. Numeric features must be backed by provenance from an API response or stored API snapshot.

## Active Betting Strategy

The active report uses a two-stage main card plus research:

- `EARLY_MAIN_SINGLE` / `EARLY_MAIN_2_LEG`
- `VALIDATED_SINGLE`
- `VALIDATED_2_LEG`
- `RESEARCH_ONLY`

The old Banker / Value / High-Odds categories are retired. Edge and expected
value remain numeric requirements, not bet categories. New player-prop families
are priced and paper-settled first. In this early product stage, a family may
enter the reversible `EARLY_MAIN` card after 50 raw scorecard outcomes and 3
eligible paper bets when its model Brier is at least 0.005 better than the
de-vigged market and its eligible-profile ROI is positive. `EARLY_MAIN` is an
early trend, not full validation: every single or two-leg combo is capped at
0.5u and automatically drops back to `RESEARCH_ONLY` if ROI or the model's
market advantage turns non-positive. Full `VALIDATED` status still requires
120 scorecard outcomes and 50 eligible settled paper bets under the same skill
and ROI tests. A formal combo is exactly two qualified player props from
different matches with positive joint EV; there is no arbitrary requirement
for total odds to exceed 2.00.

Prop probabilities and formula confidence are deliberately separate:

- `hit_probability` is the calibrated estimate that the selected outcome wins.
  The raw model is shrunk toward the de-vigged market using only that family's
  earlier settled outcomes; a new or weak family therefore stays close to the
  market instead of manufacturing confidence.
- `confidence_score` (0-100) measures whether that probability is trustworthy.
  It combines source-specific data quality, family scorecard maturity, and the
  family's Brier-score advantage over the market.

Research value flags require at least 55% calibrated hit probability, odds from
1.30 to 2.25, at least four percentage points of edge, and positive expected
value. Formal recommendations are stricter: at least 58% hit probability,
70/100 formula confidence, and 65/100 source quality. For aces and double
faults, source quality comes from each player's available serve-count history;
for derived games/set markets it comes from the match feature snapshot. Props
outside these limits remain priced and settled for calibration, but cannot be
recommended.

Headline recommendations are player-level only. Match-total aces/games remain
on the research scorecard but cannot graduate into `VALIDATED_SINGLE` or a
formal combo. Paper ROI always uses flat 1u stakes so competing formulas remain
comparable. A family that eventually graduates uses a formula-confidence-
haircut tenth-Kelly stake, rounded to 0.5u and capped at 2u for a single or 1u
for a two-leg combo. The weekly Tennis Reflector reports every family's current
`EARLY_MAIN` / `VALIDATED` / `RESEARCH_ONLY` tier and the evidence behind it.

The embedded ace calibration curves are frozen on history strictly before
2026-05-10, the first available evaluation slate. Rebuild them with
`scripts/build_ace_calibration.py --before YYYY-MM-DD` whenever validating a
new historical window, so holdout results never leak into the probability
curve.

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
PYTHONPATH=src .venv/bin/python scripts/replay_prop_strategy.py --through 2026-08-01
python -m pytest
```

The default provider is `mock`, so no paid API keys are required.

## Scheduled Telegram Messages

macOS launchd可由任何approved code checkout安裝，而毋須外置launcher。安裝時用
`WC_TENNIS_RUNTIME_ROOT`指向現有live data checkout；生成嘅plist會由approved checkout
執行versioned scripts，但`DATABASE_URL`、`TENNIS_PYTHON_BIN`（現有`.venv`）、logs同
`TENNIS_ANALYSIS_OUTPUT_ROOT`仍留喺指定runtime／Google Drive位置。Installer只改scheduler
設定，唔搬或刪除SQLite、venv同data。

The 09:00 Sydney same-day card sends two separate messages after a successful
analysis:

- the operational health/completion message goes to
  `WC_NOTIFY_TELEGRAM_CHAT` only;
- the formal "what to bet today" card goes to the primary chat and every
  comma- or semicolon-separated chat in `WC_NOTIFY_TELEGRAM_EXTRA`.

The betting message is built from the final report's `今日落注建議` section.
It includes only formal `EARLY_MAIN` / `VALIDATED` recommendations and their
listed odds, stake, calibrated hit probability and confidence. Watchlists,
research-only rows and match-winner reference rows are never promoted into the
message. A valid no-bet day sends an explicit no-bet conclusion to both
recipients. Failed or incomplete analysis sends no betting card.

The launchd card job enables this with `TENNIS_NOTIFY_BETS=1`; guarded recovery
does the same when it successfully rebuilds a missing card. Run
`scripts/tennis_daily_schedule.py --notify-self-test` to validate the bot and
all configured content recipients without sending a message.

The 18:00 review job separately enables `TENNIS_NOTIFY_PERFORMANCE=1`. After
yesterday's settlement it sends a Hong Kong Chinese performance card with
daily and cumulative formal paper ROI, every player-prop family's fixed recent
window, model-vs-market Brier, stale pending count and the current evidence
gate. Paper recommendations and manually recorded live bets are always shown
as separate ledgers; when no live bet has been recorded the message says so.

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
