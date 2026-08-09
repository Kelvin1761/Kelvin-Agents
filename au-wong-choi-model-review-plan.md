# AU Wong Choi Model Review and Improvement Plan

> **Status 2026-07-17 — review executed; this draft is superseded.**
> Results live in: `2026-07-17 AU vs HKJC Canonical Gap Report.md`,
> `2026-07-17 AU Failure Cohorts and Attribution.md`,
> `2026-07-17 AU Phase5 Candidate Shadow Tests.md`.
> Key outcomes: (1) on one ruler the AU/HKJC positional-Good gap is ~3.4pp
> (17.6% vs 21.0%), 95% CI includes zero — the believed ~10pp gap was a
> definition/sample artifact (HKJC's 26.4% came from an early 91-race sample);
> (2) canonical metrics module shipped at `.agents/skills/shared_racing/eval_metrics.py`
> and wired into AU + HKJC evaluators; (3) pre-score going refresh shipped in
> `au_auto_orchestrator.py --going`; (4) all nine Phase-5 candidates failed the
> OOS promotion gate — current model retained; misses are evidence-driven
> (zero-hit winners lose on every matrix dimension), so future work should
> target data enrichment, the field-12+ cohort, and Soft/Heavy coverage.

## Goal

Establish an apples-to-apples AU/HKJC benchmark, then improve AU out-of-sample ranking from the current comparable Good rate of about 17.9% without sacrificing Gold, Pass, winner coverage, or zero-hit control.

## Starting position

- AU: 710-race cached matrix reconstruction, Good 17.9%, Pass 40.8%, winner in Top 3 49.9%.
- HKJC: the current calibration document reports 24 Good from 91 races (26.4%), not a 710-race equivalent benchmark; the apparent 8.5pp gap must be validated before it becomes a target.
- Static 7D, wet-form suitability, measured pace figure, and the July 7D cleanup have already passed historical tests and are live. Global reweighting is therefore a lower-priority hypothesis than metric drift, data coverage, and conditional calibration.

## Tasks

- [ ] **1. Create one canonical AU/HKJC evaluator.** Report both exclusive reflector labels and cumulative model KPIs, plus engine commit, date range, race count, meeting count, and sample hash. → **Verify:** the same stored race receives identical labels in AU/HKJC reports and historical totals reconcile exactly.
- [ ] **2. Freeze a clean current-engine benchmark.** Re-score every matched AU race from local immutable inputs, remove duplicate races, record missing fields, and stop depending on on-demand Google Drive hydration. → **Verify:** every benchmark row has prediction-before-result ordering, one result match, and a reproducible dataset manifest.
- [ ] **3. Measure the real AU/HKJC gap.** Run the canonical evaluator on full, common-date, and recent holdout windows; publish paired/bootstrap confidence intervals and field-size/quality context. → **Verify:** the comparison states whether the gap remains after metric and sample alignment, rather than treating 17.9% versus 26.4% as automatically equivalent.
- [ ] **4. Localize AU failure cohorts.** Slice Good/Pass/zero-hit, winner rank, and Top-3 precision by month, venue, going, distance, class, field size, feature coverage, pace concentration, and score gap; apply the REF-DA01 outcome/process/generalizability audit to the worst segments. → **Verify:** produce a ranked issue table using only cohorts with at least 30 races or explicitly mark smaller findings as underpowered.
- [ ] **5. Attribute errors before tuning weights.** Run leave-one-dimension-out and ±10%/±20% perturbation tests for the seven matrix dimensions, then inspect winner-versus-Top-2 feature deltas in zero-hit races. → **Verify:** identify whether each excess miss comes from bad/missing raw evidence, matrix mapping, or final weights; reject changes that only improve the full in-sample total.
- [ ] **6. Test isolated improvement candidates.** In priority order: pre-score going refresh, missing/stale-feature reliability shrinkage, pace × going × venue controls, class normalization, and trial/debut recency handling. Keep each candidate separate before testing a bundle. → **Verify:** every candidate has a causal trigger, affected-race count, segment results, and unchanged-race proof.
- [ ] **7. Apply a temporal promotion gate.** Use meeting-grouped expanding walk-forward folds and an untouched recent holdout. Require a material Good lift (target +1.5pp or better), Pass and zero-hit non-regression, no more than 0.5pp loss in Gold/Top-1/winner-in-Top-3, and improvement stability across at least 4 of 5 folds. → **Verify:** rerun the winning candidate from raw Logic files through the live engine, not cached rounded scores.
- [ ] **8. Shadow, promote, and monitor.** Shadow the approved candidate beside production for at least five meetings or 50 races, then promote behind a versioned flag with automatic rollback thresholds. → **Verify:** tests pass, the Warwick Farm replay improves or remains neutral, archive gates remain green, and the live dashboard shows definition/version/sample metadata.

## Done when

- [ ] We can explain the AU/HKJC gap with comparable statistics and named failure cohorts.
- [ ] At least one candidate passes full archive, temporal holdout, meeting replay, and live shadow gates—or the evidence clearly supports retaining the current model.
- [ ] Production metrics are reproducible and no longer mix exclusive Good with cumulative Good.
