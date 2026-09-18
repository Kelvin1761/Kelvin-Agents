# Wong Choi Stage 5 D-NBA producer engineering checkpoint — 2026-09-13

## Decision

The metadata-only D-NBA feature producer and settlement-chain selector are
locally implemented and tested, but they are **not connected to NBA production
automation**. No prediction, scoring, report, archive, evidence record,
scheduler, Dashboard, Telegram or model state changed. Production integration
remains a separate production-adapter release before the next NBA season.

## Scope implemented

- `nba_research_evidence.build_feature_projection` reads the exact Sportsbet
  odds and NBA game-data files for an explicit game-tag set, observes their
  bytes at one aware cutoff, and returns deterministic central-contract v1
  feature-evidence bytes. It performs no file or database write.
- The producer maps five families: market from non-empty `game_lines` and/or
  `player_props`; player form from non-empty `players`; team context from
  non-empty `team_stats` and/or `team_dvp`; schedule context from complete
  `meta`; and injury context from `injuries`, with the last family explicitly
  unavailable when the optional source is absent or empty.
- Required families fail closed when an artifact is missing, the event or
  Sportsbet source identity does not match, or the family contains no actual
  data. The producer never treats a present-but-empty team object as evidence.
- `settlement_artifacts` returns only the canonical reflector summary, US-date
  results brief and props-verification files after validating their names,
  event linkage, versions, counts and every hit/miss/void leg. It neither
  creates results nor changes settlement state.
- Neither helper can grant source completeness, a monitoring sample or model
  promotion. They are building blocks for future append-only evidence capture.

## TDD and contract evidence

The first RED run failed during collection because the producer module did not
exist. After implementation, nine producer tests passed. The generated feature
bytes are fed directly into the existing central NBA `_projection` verifier;
the complete five-family fixture verifies, while missing odds, empty market,
empty players, empty team context, wrong event and unapproved source identity
fail closed. The settlement selector output is fed to the existing central
`_result_chain` verifier, and a mutated verification artifact is rejected.

The full current NBA test set passed 48 tests. No NBA model, feature value,
weight, season classifier or prediction code was changed.

## Read-only historical feasibility scan

The Google Drive NBA archive was scanned read-only. Twenty-six standard archive
folders contained Sportsbet files, covering 123 game tags. None could produce a
complete Stage 5 feature projection from the historical bytes:

- 13 folders used an older odds identity/event schema that cannot establish the
  current feature contract;
- four folders had empty `team_stats` and `team_dvp`, including the latest
  `2026-06-11` SAS_NYK archive;
- nine folders referenced one or more missing `nba_game_data_<TAG>.json` files.

All 30 standard historical archive folders lacked the canonical
`Reflector_Run_Summary_<analysis-date>.json`, so none had the exact three-file
settlement chain required for a hash-verifiable Stage 5 label.

This is an availability inventory only. Old reports and current reconstructed
state are not point-in-time feature evidence and must not be used to qualify a
research sample or support model promotion.

## Production gaps found

- Current `create_prediction_snapshot` emits the older NBA-specific manifest
  (`schema_version: 1`, `sport`, `target_date`, mapping-style `files`) rather
  than the canonical append-only prediction manifest expected by the central
  Stage 5 verifier.
- The snapshot does not contain `NBA_Feature_Evidence_<date>.json`; presence of
  odds/game files alone does not prove which family was available or used.
- Required team context can be structurally present but empty. Production must
  block Stage 5 research qualification for that game instead of reporting a
  verified family.
- Postgame currently submits every archive JSON as settlement evidence. Future
  integration should select the exact validated three-file result chain and
  fail when any leg remains unverified.
- Existing historical archives cannot be upgraded by reconstructing metadata
  now. Only future runs observed before publication can establish source cutoff.

## Explicitly not done

- no import or call from `nba_daily_schedule.py`, the orchestrator, extractor,
  reflector or archive script;
- no production snapshot, settlement record, archive repair or historical
  backfill;
- no change to NBA lifecycle classification, recommendation, scoring, feature,
  odds, bankroll, release policy or evaluation ruler;
- no commit, push, merge, activation, installer change, Dashboard deployment or
  Telegram notification.

## Required production integration

A separate explicitly approved scope must run the feature producer against the
exact in-memory game-tag set before publication, include its bytes in a new
canonical create-only snapshot, and publish prediction evidence only after the
manifest and source digests verify. Postgame must use the validated three-file
selector before settlement evidence is recorded. Any missing or empty required
family must block Stage 5 research qualification without blocking the ordinary
NBA report unless the existing operational policy independently requires it.
