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
Rejected old model arms are not rerun here.

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
