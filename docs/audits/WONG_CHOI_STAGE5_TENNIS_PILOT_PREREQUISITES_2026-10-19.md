# Stage 5 Tennis pilot prerequisites — 2026-10-19

## Decision

Task 8 remains **not ready**. The current evidence inventory is not a completed
Tennis research loop, and no evidence/model/promotion gate has been relaxed.
This audit changes the next action from assuming that stored predictions are
usable pilot samples to checking native forecast provenance first.

This is an operational metadata/status diagnosis, **not** a full-history corpus
audit, historical feature replay, PIT qualification, model evaluation, power
approval, or proof of a production defect. No database, immutable artifact,
ledger, model, ruler, scheduler or release policy was modified.

## Inspected state

- Fetched main at inspection: `f3675bc5c02692f31983f258cfda45565b2de68b`.
- Central state: `/Users/imac/WongChoiData/WongChoiControl`.
- Evidence root: `evidence/records`; all JSON files were parsed for a metadata
  inventory. Tennis has one model-release record, 99 prediction records, 99
  decision records and **no settlement records** at this observation.
- Configured `research-registry` and `research-queue` directories exist but
  contain zero JSON records. Their existence does not establish a real pilot.
- Installed four-domain script roots resolve to
  `/Users/imac/wongchoi-scheduler`. The Central research-review launchd plist
  is missing; baseline domain schedulers and Central durability are loaded.
- Independent power applicability inventory still verifies **0/4** profiles:
  AU, HKJC, Tennis and NBA each report `power_profile_missing`.
- Live Tennis DB schema was inspected with SQLite URI `mode=ro`,
  `PRAGMA query_only=ON`, bounded primary-key queries and a three-second SQL
  progress deadline. Observed DB size: 1,757,339,648 bytes. No integrity check,
  snapshot, full DB scan or live pricing/feature rerun was performed.

## Status-artifact evidence

Of the 99 prediction records, 81 have no research-status reference (legacy
metadata; this does not prove that their forecasts are qualified or lost).
The other 18 reference one bounded status artifact each. Every one of those
18 artifacts passed its recorded SHA256 and event/clock identity comparison;
there were no missing, ambiguous, mismatched or oversized status artifacts.
This verification covers **status bytes only**, not their complete bundles.

| Status reason | Records | Interpretation |
| --- | ---: | --- |
| `Tennis research observation coverage incomplete` | 7 | All seven parent prediction records contain zero recommendations. An empty card is not evidence of a broken nonempty capture. |
| `active Tennis component has unresolved warnings` | 6 | Existing strict native-component provenance boundary rejected capture. Do not erase the warnings or reclassify an effectful component as neutral. |
| `incomplete Tennis component set` | 5 | Capture failed its component-completeness/usable-active-component boundary. The exact per-row native cause still needs isolation; the generic message alone does not establish missing component names. |

The latest empty record (`2026-10-19`, cutoff
`2026-10-18T07:26:51.242027+00:00`) falls into the first category, not proof of
an observation-ID mismatch on a nonempty card.

Two actual nonempty references were checked directly:

- Event `2026-10-17`, cutoff `2026-10-16T22:17:24.637378+00:00`, 48
  recommendations: status SHA256
  `586923d4f8af5191c3abbd30f19d64c5c54ca273ef4b213dc1d08d98dc192399`,
  `active Tennis component has unresolved warnings`.
- Event `2026-10-18`, cutoff `2026-10-17T22:50:53.854528+00:00`, 56
  recommendations: status SHA256
  `26373bd52fd3daf00981a32f266b88f0c59a13d56cb3f3c6eca127270a1e4453`,
  `incomplete Tennis component set`.

Primary-key inspection of persisted pricing for the latter 56 IDs found the
same 11 component names, not a renamed/extra component set. None had zero
raw `active` flags. This does **not** replay their exact in-memory inputs:
`_components` can project a warned neutral non-Elo component inactive, and its
final rejection also covers a set with no usable projected active component.
Do not infer the original first failing row or change that boundary from this
metadata alone.

A subsequent bounded inspection isolated a reproducible current-persisted
condition: 23 of those 56 rows have only `head_to_head_edge` raw-active, at
neutral probability with a warning, so the unchanged projection leaves no
usable active component. Another 18 rows have a warned effectful/backbone
component. Neither count is a qualified sample count; the remaining rows were
not granted qualification.

For prediction ID `15153`, the exact stored `pricing_json` SHA256 was
`6b6066e652ac9e188ebb3f4723f48ac48e539e2172b79f24bf744f9b3d37007f`.
Calling the unchanged `_components({}, stored_pricing, available_by=stored_prediction_clock)`
reproduced `ValueError: incomplete Tennis component set`. The deliberately
empty snapshot suffices because this row reaches no active input-path read.
This is a **minimal component-boundary reproduction**, not its original memory
snapshot, full forecast replay, retrospective source repair or PIT evidence.
It supports keeping the rejection, not weakening it or declaring all historical
captures explained.

## Reproducible inspection boundaries

1. Parse the Central evidence JSON records; count Tennis `kind` values.
2. For each Tennis prediction, inspect only referenced
   `Tennis_Research_Status_*` artifacts; require one reference when present,
   a non-symlink regular file no larger than 65,536 bytes, matching SHA256,
   parent event ID and parent creation clock. Aggregate status/reason without
   filtering predictions by outcome or by whether capture succeeded.
3. Join coverage-error records to their parent recommendation count; all seven
   are empty. The full parent inventory is 99 records, including 28 empty and
   71 nonempty records; records are not distinct matches or settled samples.
4. For the explicitly identified 2026-10-18 parent, query only its persisted
   prediction primary keys and component metadata. Do not rebuild features,
   read labels, inspect terminal performance or rerun a model on the live DB.
5. Recompute `inspect_power_applicability()` against the current frozen
   resources. Do not create a profile or invent effect/variance assumptions.

Code boundaries inspected:

- `tennis-wong-choi/src/tennis_wc/cli.py`:
  `_capture_research_observation`, `_record_daily_evidence`, pricing callback.
- `tennis-wong-choi/src/tennis_wc/research_evidence.py`:
  `_components`, `build_prediction_artifacts`.
- `tennis-wong-choi/src/tennis_wc/research_adapter.py`:
  `load_forecast_context`, `record_research_settlement`.
- `.agents/skills/shared_wong_choi/research_tennis_source.py`: archived-input
  inventory explicitly cannot grant PIT-dataset or promotion readiness.

## Next actions and acceptance

1. Complete the separately scoped reader release and its immutable recheck;
   this audit does not change that release's 36 paths or claim it is merged.
2. Isolate an actual nonempty capture failure from its exact original memory
   inputs/raw references, using a bounded replay or prospective diagnostic
   capture. Persisted DB metadata is insufficient to repair historical evidence.
   Any proposed production-adapter change needs its own exact scope and tests.
3. Preserve all forecasts and explicit exclusions; never shrink the cohort to
   successful captures or fabricate/retro-date raw inputs. Empty-card status
   taxonomy may be clarified separately, without calling it a usable sample.
4. Establish one complete native prediction -> decision -> verified result
   chain before calling a Tennis sample qualified. Perform catalog/active-DB
   audits before any full-history pilot and respect production locks.
5. Preregister the frozen family-specific pilot, baseline/candidate commits,
   chronological splits and commands before evaluation. Obtain separately
   reviewed power applicability; missing profiles stay blocking. No terminal
   tuning, pooled-family rescue, market-proxy feature or auto-promotion.
6. Calendar installation, authorized Telegram delivery and private Dashboard
   acceptance remain separate Task 7 deliverables, not implied by snapshots
   or by source-only cadence tests.

## Follow-up: real corpus health audit completed

Recorded at `2026-10-18T22:45:00Z` (2026-10-19 Sydney), after the latest Tennis
card run succeeded. The unchanged, approved production CLI completed with exit
0 and `status: ok`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/wongchoi_external_run.py -- nice -n 10 python3 .agents/skills/central_wong_choi/scripts/central_wong_choi.py corpus-audit --domain tennis --active-sqlite /Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db --json
```

Working directory: `/Users/imac/wongchoi-scheduler`, approved main
`660b0952d952cf57ca9e35f55dd8a96f005a4c9e`. External scratch:
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-jbvqund0`.

The active DB and all four catalog-backed archive DBs passed `PRAGMA
quick_check`. Both relevant catalog artifacts resolved with verified copy
hashes (`catalog_status: ok`): `wc-artifact:5f6c9a118c80bfab16addb33`
(`migration-db-snapshots`, three DBs) and
`wc-artifact:bdcad6e5e530b9e857b170a5` (`db-snapshot`, one DB). All four archived
DBs were read from the mounted external archive, not substituted into runtime.

| Named table | Active rows observed | Maximum archived rows |
| --- | ---: | ---: |
| `matches` | 9,070 | 4,690 |
| `match_results` | 11,919 | 5,552 |
| `odds_snapshots` | 15,778 | 9,503 |

There was no regression against these three row watermarks, and
`runtime_snapshot_substitution_allowed` remained `false`. SQLite connections
used `mode=ro` and `PRAGMA query_only=ON`; no DB was restored, replaced,
backfilled or attached as the active source, and no ledger SQL was applied.

This closes this observation's **known catalog / SQLite quick-check / three
named row-watermark** preflight, not a foreign-key audit, full
`integrity_check`, all-market coverage proof, immutable pilot dataset,
historical feature derivation, earliest-price proof or model evaluation.
Catalog coverage does not establish the completeness of uncatalogued data.
These row counts are not distinct qualified outcomes or research samples.
The native prediction/settlement provenance and reviewed power gaps above
remain open; Task 8 and Stage 5 exit are not accepted.

No claim of improved prediction performance or Stage 5 completion is made.
