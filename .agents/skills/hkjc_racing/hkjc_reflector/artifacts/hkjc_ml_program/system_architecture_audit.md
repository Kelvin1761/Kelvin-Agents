# Existing HKJC Wong Choi System Audit

## End-to-end flow

1. HKJC local racecard/result material is extracted by `hkjc_race_extractor` into meeting folders.
2. `.agents/scripts/run_prerace_pipeline.py` builds point-in-time `Facts.md` inputs.
3. `hkjc_wong_choi/scripts/hkjc_orchestrator.py` creates `Race_X_Logic.json`.
4. `hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py` invokes the deterministic racing engine.
5. `racing_engine/scoring.py` computes 12 feature scores, maps them to the frozen seven-dimension Rating Matrix, ranks runners, assigns display grades and pick status, and renders Markdown/CSV output.
6. `hkjc_reflector` joins official results, reviews weak races and builds chronological research datasets.
7. The dashboard consumes generated meeting artifacts; deployment is downstream and is not part of model training.

## Data/logic classification

| Layer | Examples | Classification |
|---|---|---|
| Raw/pre-race | racecard, runner, barrier, weight, form, trackwork, sectionals available before the race | raw racing data |
| Engineered | recent-form summaries, relative-to-field values, course/distance evidence, normalized sectionals | deterministic engineered features |
| Rating Matrix | 12 score rules, seven mapped dimensions, official weights, grades and pick gates | manually designed scoring/weights |
| Historical tuning | archived weight/threshold experiments and reflector diagnostics | parameter optimisation, not ML |
| This program | fold-local Logistic, LightGBM, XGBoost probability models | genuine supervised ML |

## Identity and result handling

- Race identity uses date, authoritative meeting name/venue and race number.
- Runner identity uses race key plus horse number; canonical horse ID is retained where present.
- Jockey/trainer names exist, but canonical IDs and effective-dated rename registries do not.
- Actual matched starters drive field size and Place cutoff.
- Incomplete or non-contiguous result joins are excluded, not repaired with hindsight assumptions.
- Complete timestamped scratching/reserve, abandoned-race, DQ/dead-heat and settlement ledgers are not present; these remain documented limitations.

## Production/betting boundary

Production validation rejects odds/market/value/edge scoring fields. The current engine has advisory output language but no archive-complete executable odds/ROI/staking backtest. This ML program therefore evaluates racing analysis first and reports the betting layer as N/A until fixed-time Win/Place snapshots and settlement metadata exist.
