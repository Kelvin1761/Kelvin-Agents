# NBA preseason pipeline recovery — 2026-10-09

The approved startup fix `1c77d21f6ab0786500e0ad6d689b7d5ca4cd838d` addressed
empty postgame folders and preseason competition discovery. A subsequent live
full-pipeline test exposed separate data-selection, market-selection, identity,
and runtime-model issues. This candidate fixes those issues without changing
model weights, probability formulas, or trained model artifacts.

## Reproduced failures and fixes

1. Current NBA API season `2026-27` had zero RS/playoff gamelogs during preseason.
   The current roster is retained while preseason statistics explicitly refer
   to `2025-26`. Actual row dates determine L10 ordering; the event's entire US game day
   and future rows are excluded, even when UTC/Sydney dates are one day ahead.
   Unknown official games fail closed rather than inventing synthetic dates. Source season/cutoff metadata is recorded. Early regular-season
   L10 includes completed previous-season games until current L10 is complete;
   current API failures cannot masquerade as an empty season.
2. Sportsbet quarter/half moneylines overwrote full-game prices; `Pick Your Own
   Line` supplied a bogus main spread of +36.5. Only named full-game markets now
   supply game context, using the away team's handicap. Missing main spread is
   omitted. Actual Sportsbet fields take precedence over secondary-book fields.
3. `Luka Doncic` did not match NBA's `Luka Dončić`. Full-name normalization now
   matches accents without surname fallback or Jr./Sr. collisions. Ambiguity is
   rejected. Injuries use the same identity normalization.
4. The player firewall counted surname mentions in injury/news text as actual
   analysis. It now requires full-name player-card headings. Preseason shadow
   coverage is checked against every priced player with verified historical
   data, requires NO BET, and blocks empty history. Production keeps the
   existing minimum of three real player analyses. Unavailable markets are
   disclosed rather than filled with fake data.
5. Preseason outputs lacked conspicuous NO BET banners. All game/master reports
   now mark their shadow status. The existing scheduler still skips preseason
   betting-card publication and settlement behavior is unchanged.
6. The existing v3 ML model was a Google Drive placeholder; reading it stalled.
   The unchanged artifacts were fetched via the connected Drive plugin and
   verified against the eventually completed filesystem copy. Scheduled runs
   can use a verified hydrated local cache through `NBA_WC_MODEL_DIR`.
7. Moneyline-only games now return an explicit retryable `player_markets_not_open`
   outcome (exit 75), producing no analysis/snapshot. Failed runs no longer print
   a successful completion banner. Child stdout failures are retained so the
   underlying diagnosis is visible.

## Live verification

Isolated test root: `/private/tmp/nba-preseason-candidate-ixoq6zcg`.
Base revision: `1c77d21f6ab0786500e0ad6d689b7d5ca4cd838d`; candidate source hashes
are recorded separately. No official dashboard publication, Telegram message,
external settlement, or production prediction snapshot was created by these tests.

- Original HOU–DAL full attempt: failed correctly at all-players-missing L10.
- SAC–LAL real extraction: 13 Sacramento and 16 Lakers players with history.
- Strict extractor/Sportsbet schema: no errors or warnings.
- Corrected real report: passed all firewall checks.
- Master SGM and Banker generation: passed.
- Exact existing v3 model: Hybrid report generation and validation passed.
- Snapshot functional test: file hashes and append-only behavior passed; shadow
  metadata verified. These snapshots were created after tipoff and are **test
  evidence only, not official pregame predictions**.
- HOU–DAL moneyline-only test: no extractor/report was fabricated. Exit 75 and
  no completion claim are also covered by the CLI regression test.
- Regular-season opener live API check: Kevin Durant returned ten real
  historical games from `2025-26` despite an empty `2026-27` query, with explicit
  source-season metadata. This was a data test, not a future betting report.

Existing v3 model hashes:

- `model.pkl`: `459803dd73799293a4771a4d1e299238c199ce5519ef1b87461f7be4712a0265`
- `feature_names.json`: `9fba3c085c9762c8eb9a9a1843ac6257b861b5bdc5c4009e5eaf61124c7a5a27`

Verified local cache: `/Users/imac/WongChoiData/NBA_ML_Dataset/models/v3`.

## Scope and remaining operational limits

This is pipeline correctness evidence, not a claim of better betting performance.
No model parameters were tuned and no historical result was used to rescue a
candidate. Regular-season advanced statistics remain current-season inputs;
new-season data may naturally be sparse and must not be represented as complete.

The live test covered one game's full pipeline, not all games on the official
schedule. The scheduler's exact full-day coverage guard remains unchanged. It
must still wait if any required player markets are unavailable. Missing original
2026-10-08/09 pregame evidence cannot be honestly reconstructed after the fact.
This candidate requires a new immutable SHA approval before production activation.
