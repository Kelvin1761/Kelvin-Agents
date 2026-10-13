# Optional AU/HKJC drift diagnostics

Evidently 0.7.23 runs in its own Python 3.12 environment. No dependencies are
added to the scoring interpreters. Install on macOS/Linux with:

```bash
bash .agents/skills/shared_racing/monitoring/install.sh
```

The AU and HKJC full orchestrators invoke the advisory after their existing
health/compliance checks. It reads stored pre-race feature scores and the prior
28 calendar days; no outcomes, odds, scores or ranks are changed. No upload is
performed and telemetry is disabled. Run directly with:

```bash
.agents/skills/shared_racing/monitoring/.venv/bin/python \
  .agents/skills/shared_racing/monitoring/drift_monitor.py \
  --platform au --meeting '/path/to/YYYY-MM-DD Venue Race 1-8' \
  --out scratch/drift-manual
```

Automatic reports are saved to `scratch/wongchoi-drift/<platform>/<meeting>/<run>/`:
`drift.json`, `pooled_exploratory.html` when sufficient data exists, `run.log`
and `status.json`. History includes native and catalog-verified WARM corpus
through the existing `corpus_paths` reader. Read failures produce a failed
advisory, never a success based on a silently smaller sample.

Matched cohorts use venue × distance band × going family × field-size bucket.
At least 100 reference and 50 current non-null horses are required per feature.
Many individual meetings will therefore have no evaluable cohort. Unknown or
undersized cohorts explicitly report `insufficient_data`; the pooled plot is
exploratory only. Historical score versions are not exact engine hashes, so
even matched drift may reflect a model revision. Drift is not proof of a
scraper failure, model degradation or a reason to retrain.

The normalized Wasserstein threshold is fixed at 0.1 for this diagnostic.
Drift excludes nulls: missing rates are printed separately; the existing
health and data-contract checks remain authoritative. Advisory errors and a
60-second timeout cannot fail scoring/publication. Set
`WC_DISABLE_DRIFT_MONITOR=1` to disable, or remove the isolated `.venv`.
Direct auto-engine re-scoring paths do not run this advisory.

Experiment evidence: `docs/experiments/EXP-20261014-01-evidently-drift-monitor.md`.
The experiment showed extra detection for artificial +4-point and 25% spread
compression faults. It did not establish a real-world false-positive rate or
improve predictive performance. NBA and Tennis have not been evaluated.
