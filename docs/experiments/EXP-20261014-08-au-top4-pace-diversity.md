# EXP-20261014-08 — AU top4-pace-diversity

- Status: COMPLETED — REJECT, ranking evidence too weak.
- Hypothesis: A competitive fourth selection with opposite pace profile can improve Top4 capture.
- Prior work searched: EXP-20261013-11 pace-score candidates REJECT; EXP-20260902-09 preparation score candidates REJECT; EXP-20260928-07 constrained reranker; source review docs/audits/2026-10-14-horse-analyst-borrowing-review.md.
- Definition: One fixed arm: lock baseline top3, inspect baseline 4th/5th. When top4 all have valid same-half f800 (<0.5 vs >=0.5), fifth has opposite style and within 2 baseline score points of fourth, swap fourth/fifth. Missing pace means unchanged. Gate prerequisite pace-confidence diagnostic dev rho(confidence, absolute error)<0 at pooled and >=3/5 date folds; still measure fixed arm diagnostically if prerequisite fails, never promote. No new thresholds or widening pool after outcomes.

Baseline: freshly rescore current engine; no production mutations. Main eligibility: date >= 2026-08-05 and complete actual position set 1..N, unique runner identifiers; whole-date canonical terminal fraction 0.15 and five development time folds. Filter fixed for snapshot integrity before candidate outcomes. Previous terminal dates have been exposed in other experiments: these are retrospective tests, never automatic promotion. Primary Gold/Good non-regression, canonical au_eval Stage 4 v2; dev eligibility Gold/Good >= baseline, top5 AUC > baseline and at least 3/5 nonnegative Gold/Good folds. Select median eligible k, not argmax. k grid {0.5,1,1.5,2,3}; no terminal if dev fails. Diagnostic labels strictly separate; no odds feature. No combining candidates. Missing feature z=0. Cohorts: field-size <=8/9-10/11-12/13+, venue, going, maiden vs other, career <=4 vs other, baseline favourite SP buckets for evaluation only. Bootstrap seed7, 2000 paired race replicates.

Research output: scratch/horse-analyst-tests-20261014. Results and reproducible commands will be appended. No model code commit/push authorized by this experiment.


## Top4 分散結果

Fixed fourth/fifth swap triggered in **89/2,591 races**. The top three choices stay fixed, so Good and Gold-strict cannot improve from this rule. Pace-confidence diagnostic prerequisite passed on dev (all five folds negative error correlation).

- dev Gold **+0.0000pp**, Good **+0.0000pp**, top5 AUC **+0.00002787**, primary nonnegative **3/5** folds.
- One terminal ranking evaluation: Gold **19.0024% → 19.2399% (+0.2375pp)**, one additional race; Good **25.6532% unchanged**.
- top5 AUC **0.6890647 → 0.6893525**, delta **+0.0002878**, paired 95% CI **[-0.0004387, +0.0011411]**.
- Canonical Stage4 v2: **REJECT / ranking_evidence_too_weak**. NDCG and AUC point estimates positive, no ranking CI supported. No threshold/pool expansion after terminal. Cohort details saved in results.json, including field, venue, going, class, top-pick career and SP labels.

A small positive point estimate is not a proven benefit. The initial implementation accidentally required strictly positive dev Gold, contrary to the pre-registered non-regression + AUC rule; this was corrected before its first terminal evaluation. No new eligibility rule was invented to rescue the arm. Section6 component-budget power was not separately pre-measured; do not retrospectively relabel this REJECT as UNRESOLVABLE. It remains rejected for adoption.


## 完成結果與共同證據

- Baseline freshly rescored 3,461 races. Fixed main eligibility retained **2,591 races / 24,857 runners**; 803 pre-2026-08-05 races and 67 incomplete/deadheat position sets excluded before candidate outcomes. No fuzzy outcome repair.
- Whole-date split: **dev 2,170 races, 2026-08-05–10-02; terminal 421 races, 2026-10-03–13**. Five dev date folds; canonical au_eval. Terminal had prior exposure in other projects: retrospective evidence, not a pristine promotion set.
- Current scoring replica max absolute error **0.000050**, consistent with exported rounding. Baseline dev Gold **21.3825%**, Good **25.6221%**, top5 AUC **0.691806**; terminal Gold **19.0024%**, Good **25.6532%**, top5 AUC **0.689065**.
- New pace/workload inputs use dated formal history strictly before target date. Trial/current/future runs excluded. Later form supplies diagnostic positioning labels only; 179 ambiguous horse/date label instances excluded. Betting odds never enter candidate inputs.
- Five research invariant tests passed. Full repository check passed all suites, goldens, explanation freshness and data contracts, with the existing isolated HKJC test-log env override. Production scoring and golden snapshots unchanged; no commit, push or deployment.
- Whole-baseline point-in-time provenance is not independently certified by this experiment: current-engine retrospective replay may contain reconstructed/global prior artifacts. Going aggregates used for sensitivity are not independently timestamp-certified. Do not turn diagnostics into deployed confidence or claim a candidate promotion.

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out scratch/horse-analyst-tests-20261014/leaves_baseline.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 docs/experiments/patches/horse_analyst_tests.py build --data scratch/horse-analyst-tests-20261014/leaves_baseline.json --out scratch/horse-analyst-tests-20261014/research_dataset.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 docs/experiments/patches/horse_analyst_tests.py test --data scratch/horse-analyst-tests-20261014/research_dataset.json --out scratch/horse-analyst-tests-20261014/results.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 docs/experiments/patches/horse_analyst_tests.py supplement --data scratch/horse-analyst-tests-20261014/research_dataset.json --out scratch/horse-analyst-tests-20261014/supplement.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 -m pytest docs/experiments/patches/test_horse_analyst_tests.py -q -p no:cacheprovider
```

Raw artifacts stay in the named scratch directory (<100MB), not copied into the experiment index. `manifest.json` records code SHA, script/artifact hashes and source-dataset fingerprints. Source hashes stored in `research_dataset.json` protect against concurrent AU engine changes. Re-running on a changed corpus/engine is a new experiment, not a reproduction of these numeric results.
