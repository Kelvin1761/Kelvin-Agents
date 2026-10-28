# Unified tennis research execution

Offline work for [the execution plan](../../tennis-research-execution-plan-20261028.md).
Nothing in this directory is imported by production pricing. An accurate
mathematical oracle, green tests or a coherent database is not model performance
evidence. Candidate development and qualification status are recorded separately
in the progress audit and EXP-20261029-03; no candidate is promoted here.

## Reproduction

Use the Python interpreter recorded in `runtime/runtime_manifest.json`, and set
`PYTHONDONTWRITEBYTECODE=1`. Run from the repository root. Each output path is
create-only; use a new directory for a replay and retain previous results.

```bash
python -m pytest research/tennis_unified -q
python -m research.tennis_unified.warehouse capture --source "$TENNIS_LIVE_DB" --output "$NEW_EXTERNAL_RUN"
python -m research.tennis_unified.runtime --models-json "$MODEL_INVENTORY" --output "$NEW_EXTERNAL_RUN/runtime"
python -m research.tennis_unified.warehouse inventory --db "$NEW_EXTERNAL_RUN/warehouse.db" --output "$NEW_EXTERNAL_RUN/warehouse_inventory.json"
python -m research.tennis_unified.baseline --db "$NEW_EXTERNAL_RUN/warehouse.db" --output "$NEW_EXTERNAL_RUN/baseline"
python -m research.tennis_unified.sources download --spec "$FROZEN_SOURCE_SPEC" --output "$NEW_EXTERNAL_RUN/sources-f01"
python -m research.tennis_unified.sources audit --manifest "$NEW_EXTERNAL_RUN/sources-f01/source_manifest.json" --output "$NEW_EXTERNAL_RUN/sources-f01/qualification.json"
python -m research.tennis_unified.kernel_audit --protocol research/tennis_unified/protocol_f02.json --output "$NEW_EXTERNAL_RUN/kernel-f02"
```

Before full-history research, the Central `corpus-audit --domain tennis
--active-sqlite "$TENNIS_LIVE_DB" --json` must pass against the actual live DB.
An archive or research snapshot must not be supplied as `--active-sqlite`.
Use the research snapshot for offline model/warehouse audits instead.

## Corpus and result qualification

- Snapshot captures every table and row in a pinned SQLite read transaction,
  including uncheckpointed WAL contents, and verifies counts/integrity. It does
  not create an empty DB when a source is missing or overwrite previous evidence.
- Baseline uses the existing agreed-outcome/first-forecast consumer, strengthens
  quote receipt checks, and separately records timing, replay and frozen fixture
  status. These different subsets must not be compared as an improvement.
- Every baseline row remains `SEEN_DEV`. Full source provenance is deliberately
  unverified until checked against canonical immutable prediction bundles.
- Source transfer verifies expected bytes and Git blob SHA. The recorded source
  scope is full MCP metadata/Overview plus one complete US Open paired sample,
  not all PBP data. Malformed rows are held with raw values and reasons.
- The kernel audit fixes the case list before simulation and uses 22 simultaneous
  exact binomial intervals. Legacy simulator parity uses its own simplified
  tie-break law. A separate iid point oracle implements 1-2-2 and 7/10 targets;
  neither result establishes historical tournament/year eligibility or accuracy.

Raw captures, output, source copies and method locks are outside Git at the
external archive path recorded in the progress audit. EXP-20261029-03/04 record
the completed F04/05/06/08 and fixed-feature head comparisons. All failed the
preregistered development conditions. Market experiments, historical source joins,
joint props and new forward evidence remain subject to their applicable gates.
Rejected old model arms are not rerun here. EXP-20261029-05 subsequently completed
the reserved market/de-vig comparisons; all four new candidates also failed.

## Source-isolated feature development

`history.py` reads twelve fixed season responses from the verified snapshot;
it retains every target with missing box scores, holds conflicting event facts,
and records source URLs/body hashes, calendar boundaries and all exclusions.
`features.py` releases results strictly after tournament-start+21 days, retains
cold starts, and stores historical pre-match opponent/H2H expectations. That
availability rule is a synthetic **SEEN_DEV** approximation, not verified PIT.

```bash
python -m research.tennis_unified.history --db "$SNAPSHOT" --output "$NEW_COHORT_JSON"
python -m research.tennis_unified.study prepare --cohort "$NEW_COHORT_JSON" --output "$NEW_FEATURES_JSON"
python -m pytest research/tennis_unified -q -p no:cacheprovider
python -m research.tennis_unified.study lock --cohort "$NEW_COHORT_JSON" --features "$NEW_FEATURES_JSON" --test-log "$PASSING_TEST_LOG" --output "$NEW_LOCK_JSON"
OPENBLAS_NUM_THREADS=1 python -m research.tennis_unified.study run --lock "$NEW_LOCK_JSON" --output "$NEW_RESULTS_DIRECTORY"
```

The lock records exact data, method and prerequisite-test hashes before fitting.
The runner checks the population/labels again, uses all five preregistered time
folds and saves every arm. All 38 comparisons and both metrics share one Holm
family; missing/deferred arms retain their 76-test slots. Feature gains must be
attributed against their direct matched controls. Live/market comparisons and
ROI are explicitly unavailable in this isolated cohort; this runner cannot
justify activation. Original output is lossless JSONL. The completed batches
also have exact round-trip-verified Parquet and CSV/JSON report exports under
the external `f03-f09/report-export/` directory. A pinned isolated PyArrow18.1.0
formatter is kept on the archive; the shared model runtime was not changed.
The earlier `parquet-export/` formatter attempt is retained for audit: its
per-stage manifest incorrectly included its own empty digest. `report-export/`
has independently verified non-self-referencing manifests and identical
prediction bytes; original model-result manifests were not affected.

`head.py` implements the single preregistered fixed-feature histogram-boosting
comparison in its reserved test slot. It first proves refitted logistic parity
against the original saved control, mirrors training rows with half weights,
and enforces probability swap symmetry. Its lock and results are create-only;
locally generated pickle artifacts are hashed and are never loaded from an
external model source. EXP-20261029-04 records its rejection.

## Historical market development

`prices.py` joins all twelve pinned original-publisher workbooks to source event
identities before checking outcomes/scores. Ambiguities and conflicting facts are
held. `market_cohort.py` removes the 26 disputed events from targets **and** every
historical feature input, using the unchanged frozen feature algorithm. Original
failed feature/head outputs remain immutable and are not refitted.

`protocol_market.json` fills five already reserved comparisons in the same
38-comparison/76-test family. `market_study.py` fits a fixed proportional-market
logit offset plus the original seven tennis features, compares it against both
market and matched tennis-only controls, and tests power/Shin/causal inner
de-vig selection. Per-book losses are averaged within matches before paired
inference; each training match has total book weight one. The existing worktree
de-vig source is hash-locked. Set `PYTHONPATH=tennis-wong-choi/src:.` to ensure
that exact source is loaded.

```bash
PYTHONPATH=tennis-wong-choi/src:. python -m research.tennis_unified.market_study lock --base-lock "$BASE_LOCK" --price-cohort "$CLEAN/price-cohort.json" --clean-directory "$CLEAN" --prior-summary "$HEAD_RESULTS/summary.json" --test-log "$PASSING_TEST_LOG" --output "$NEW_MARKET_LOCK"
PYTHONPATH=tennis-wong-choi/src:. OPENBLAS_NUM_THREADS=1 python -m research.tennis_unified.market_study run --lock "$NEW_MARKET_LOCK" --output "$NEW_MARKET_RESULTS"
```

The completed phase covers 11,725 unique development matches/23,393 book
observations. All candidates are rejected; winning against the weaker tennis-only
control does not establish incremental value over the market. Quote capture
clocks/types remain unverified, so ROI is hypothetical and cannot authorize
promotion. The frozen final probability clipping can create spurious extreme
price edges; these are counted explicitly rather than changing policy after
results. Full identity-universe audit, independent feature/probability/bootstrap
replay and exact-round-trip Parquet/CSV exports are preserved under the external
`market-phase/` evidence directory. No research runner is wired into production.

## MCP and full Slam source qualification

`mcp_qualification.py` reconciles every captured MCP metadata/Overview row
against the complete raw identity universe before checking two-player Total
point counts and source box scores. It retains unknown surfaces as potential
ambiguities, holds all duplicate canonical charts, and reports population
coverage by tour/surface/level/round. Per-set Overview rows never duplicate Total.

`slam_capture.py` transfers the fixed 49-event/98-file singles roster, with
size/Git-blob/SHA256 verification, per-file resumable receipts and reuse of the
two original US Open captures. `slam_points.py` reconstructs legal point/game/
set/match states and service order under the explicit 2011-24 event rules in
`slam_rules.json`. Unknown event/year/draw rules have no modern fallback.
`slam_qualification.py` checks the complete captured population, metadata and
independent canonical outcomes. IBM/Infosys schema variants are explicit by
event/year; blank scoreboard fields remain missing, and full scoreboard
verification is separate from legal point replay. Initial markers never add
points; gaps or contradictions are not interpolated.

```bash
python -m research.tennis_unified.mcp_qualification --manifest "$INITIAL_SOURCE_MANIFEST" --cohort "$CLEAN/cohort.json" --database "$SNAPSHOT" --output "$NEW_MCP_AUDIT"
python -m research.tennis_unified.slam_capture --spec "$PINNED_98_FILE_SPEC" --previous-manifest "$INITIAL_SOURCE_MANIFEST" --output "$NEW_CAPTURE_OR_INCOMPLETE_RESUME"
python -m research.tennis_unified.slam_qualification --manifest "$FULL_CAPTURE/source_manifest.json" --cohort "$CLEAN/cohort.json" --database "$SNAPSHOT" --output "$NEW_CREATE_ONLY_AUDIT"
```

EXP-20261029-06 records 3,902 MCP and 1,872 Slam matches whose identities/points
agree with the source, with 424 overlapping canonical keys. Full point replay
passed for 7,596 Slam matches, including 6,101 with complete supplied scoreboard
verification. All 10,513 metadata and 1,922,136 point rows are accounted for.
Independent physical-source and grouped-game replays passed. Training eligibility
remains zero because publication clocks are unverified; the missing P05 encoded
schema remains stopped. C14 workload is separately stopped: positive minutes
exist, but actual end clocks and the original-context recent-14d availability do
not. These source audits do not refit candidates or demonstrate accuracy gains.
External `f01-full/slam-audit-v4/` is the final trusted audit; three earlier
diagnostic parser versions are preserved for forensic comparison only.
