# Unified tennis research execution

Offline work for [the execution plan](../../tennis-research-execution-plan-20261028.md).
Nothing in this directory is imported by production pricing. An accurate
mathematical oracle, green tests or a coherent database is not model performance
evidence. No candidate has been fitted or promoted at this checkpoint.

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
external archive path recorded in the progress audit. F03–F10 model experiments,
historical joins and new forward evidence remain to be executed after the
applicable data/evidence gates. Rejected old model arms are not rerun here.
