# Evidently drift diagnostics — 2026-10-14

## Decision

**ADOPT_ADVISORY for AU and HKJC.** There is controlled evidence of additional
fault detection beyond `data_contract.py`. There is no evidence of better
prediction performance, no confirmed natural incident and no measured real-world
false-positive rate. Keep existing publication gates and scoring unchanged.
NBA and Tennis were not evaluated.

The reference/candidate data-contract comparison used a fresh experiment-only
baseline learned from the identical stored files before fault injection. The
production calibration files were not changed. Source bytes remained unchanged
for every manifest entry. Outcome and odds fields were not used.

## Frozen protocol and corpus

Protocol was written before the first experiment to
`scratch/evidently-20261014/protocol.json`; its complete contents are preserved
in [machine evidence](evidence/evidently-20261014.json), together with file
SHA-256 digests, current checkout commit and hashes of the probe, monitor and
existing comparator. The initial probe used a working tree with concurrent uncommitted model changes.
The preserved evidence is the repeat on fresh `origin/main` in an isolated
worktree; only the monitor changes were present. Comparator code hashes and
input score hashes identify the experiment bytes.

Reference: 2026-10-01–07. Current: 2026-10-08–13. Existing `corpus_paths` discovery
was used, including native/verified WARM files, with no silent read exclusions.
This is a dated diagnostic sample, not a full-history model evaluation.

| Platform | Reference races / horses | Current races / horses | Injected sample |
|---|---:|---:|---:|
| AU | 311 / 3,002 | 230 / 2,343 | 30 races / 293 horses |
| HKJC | 31 / 395 | 11 / 136 | 11 races / 136 horses |

Method: Evidently 0.7.23 normalized Wasserstein distance, fixed threshold 0.1.
Fault field: `trainer_score`. No thresholds were retuned after the results.
Controls: identical data and deterministic row shuffle. Fault arms were copied
and removed sequentially; no large corpus duplicates were retained.

## Paired fault results

Both platforms produced the same qualitative results:

| Case | Existing data contract | Evidently drift |
|---|---|---|
| Identical input | No findings | Stable |
| Row shuffle | No findings | Stable |
| All trainer values = 60 | Dead-field findings | Detected |
| Add 4 to every trainer value | No findings | Detected |
| Compress differences from 60 by 25% | No findings | Detected |
| Remove trainer values from every third horse | No findings | Stable after dropping nulls |
| Remove trainer field from every horse | Presence failure | Insufficient data |

Extra faults detected: **2 per platform**. This does not establish broad fault
coverage: only one feature and five constructed failures were tested. Evidently
does not replace missing-value checks. The monitor explicitly reports missing
rates and insufficient non-null samples rather than treating untestable fields
as stable. Dependency versions are pinned in `monitoring/requirements.lock`.

## Natural drift and limits

Pooled AU alerts: `pace_map_score` (0.254), `track_score` (0.159).
Pooled HKJC alerts: `form_score` (0.150), `jockey_score` (0.357),
`trainer_score` (0.540). These are **unverified distribution shifts**, not
diagnosed incidents. Stored scores span different model revisions, and changes
in meeting composition can produce the same pattern.

Exact cohorts were fixed as venue × distance band × going family × field size.
None met the 100 reference / 50 current horse minimum in the natural comparison.
No pooled alarm was promoted to a cohort-confirmed fault. No leakage/holdout
performance claim is made: this experiment never joins outcomes, retrains,
changes ranking, or changes the evaluation contract.

## Integration and verification

The local AU/HKJC full orchestrators run the optional advisory after existing
health/compliance gates. Evidently is installed in a separate Python 3.12 venv;
scoring dependencies are unchanged. Telemetry is disabled. Reports include input
hashes, sparse cohort statuses and a clearly labelled exploratory pooled plot.
Missing installation, read errors and a 60-second timeout do not fail scoring.
`WC_DISABLE_DRIFT_MONITOR=1` disables the integration. Direct auto-engine-only
refreshes do not run the advisory.

Actual post-scoring hook smoke tests completed on the stored 2026-10-14 Rosehill
and Happy Valley meetings; both reported zero sufficiently sampled cohorts.
Four focused tests cover source preservation, duplicate identity, sparse/unknown
cohorts, synthetic shifts, wholly missing features and timeout/disable isolation.
The standalone fault replay was repeated with the installed environment and
produced the same adoption decisions.

The production AU/HKJC wrappers explicitly use `/usr/bin/python3` (Python 3.9).
A diagnostic full gate under the workstation's Python 3.14 hit the pre-existing
AU `test_json_weight_order_does_not_change_production_rounding` assertion
(`60.1234` vs `60.1235`). All six projection tests pass under the production
interpreter. Release gates use `PYTHON_BIN=/usr/bin/python3`; no scoring code or
test expectation was modified to address that separate compatibility issue.

The local venv and hooks are installed and tested. The production scheduler
checkout is `/Users/imac/wongchoi-scheduler`; production publication/activation
is a separate release action. The user explicitly authorized that release on
2026-10-14; deployment proceeds only through the existing full gate and immutable
SHA recheck. A production checkout must install the isolated environment after
receiving these files; the venv is deliberately excluded from Git.

## Reproduction

```bash
bash .agents/skills/shared_racing/monitoring/install.sh
PYTHONDONTWRITEBYTECODE=1 .agents/skills/shared_racing/monitoring/.venv/bin/python \
  docs/experiments/patches/evidently_probe.py
PYTHONDONTWRITEBYTECODE=1 .agents/skills/shared_racing/monitoring/.venv/bin/python \
  -m unittest discover -s .agents/skills/shared_racing/monitoring -p 'test_*.py'
./檢查.sh --quick
./檢查.sh
```

Official API references:
[data drift](https://docs.evidentlyai.com/metrics/preset_data_drift),
[fixed method/threshold](https://docs.evidentlyai.com/metrics/customize_data_drift).
The API documentation explicitly says drift drops nulls.
