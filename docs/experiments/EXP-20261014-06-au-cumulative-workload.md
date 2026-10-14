# EXP-20261014-06 — AU cumulative-workload

- Status: COMPLETED — ranking REJECT_DEV; diagnostic findings below.
- Hypothesis: Recent accumulated racing exposure adds information beyond current form.
- Prior work searched: EXP-20261013-11 pace-score candidates REJECT; EXP-20260902-09 preparation score candidates REJECT; EXP-20260928-07 constrained reranker; source review docs/audits/2026-10-14-horse-analyst-borrowing-review.md.
- Definition: Prior 45 days, formal starts only: cumulative metres, count and minimum gap. Complete-window evidence: oldest known prior formal run <= boundary OR complete career count represented; otherwise missing. Independent arms negative total metres and negative starts, each tested separately; no copied 4800m veto. Workload metrics diagnose exposure, never physiological lactate.

Baseline: freshly rescore current engine; no production mutations. Main eligibility: date >= 2026-08-05 and complete actual position set 1..N, unique runner identifiers; whole-date canonical terminal fraction 0.15 and five development time folds. Filter fixed for snapshot integrity before candidate outcomes. Previous terminal dates have been exposed in other experiments: these are retrospective tests, never automatic promotion. Primary Gold/Good non-regression, canonical au_eval Stage 4 v2; dev eligibility Gold/Good >= baseline, top5 AUC > baseline and at least 3/5 nonnegative Gold/Good folds. Select median eligible k, not argmax. k grid {0.5,1,1.5,2,3}; no terminal if dev fails. Diagnostic labels strictly separate; no odds feature. No combining candidates. Missing feature z=0. Cohorts: field-size <=8/9-10/11-12/13+, venue, going, maiden vs other, career <=4 vs other, baseline favourite SP buckets for evaluation only. Bootstrap seed7, 2000 paired race replicates.

Research output: scratch/horse-analyst-tests-20261014. Results and reproducible commands will be appended. No model code commit/push authorized by this experiment.


## 作戰量結果

Final dated-window coverage: **22302/24857 = 89.72%**. Coverage requires an observed formal event on/before the 45-day boundary. This is a boundary check, not proof the provider omitted no intervening race. Complete-career metadata was removed as a coverage certificate after an invariance audit found it could depend on refreshed/future information. Both initial results are preserved in `pre-correctness-results`; final results below use the stricter date-only rule. No parameter tuning, date split change or outcome-based threshold change.

### Negative accumulated metres (less exposure gets higher score)

| k | dev Gold Δpp | dev Good Δpp | top5 AUC Δ | primary nonnegative folds |
|---:|---:|---:|---:|---:|
| 0.5 | -0.2304 | +0.3687 | -0.001429 | 1/5 |
| 1 | -0.6912 | -0.1382 | -0.003997 | 0/5 |
| 1.5 | -1.1982 | -0.3687 | -0.009137 | 0/5 |
| 2 | -1.3364 | -0.8295 | -0.013551 | 0/5 |
| 3 | -1.8894 | -2.1659 | -0.021488 | 0/5 |

### Negative accumulated starts, separate ablation

| k | dev Gold Δpp | dev Good Δpp | top5 AUC Δ | primary nonnegative folds |
|---:|---:|---:|---:|---:|
| 0.5 | -0.2765 | +0.1382 | -0.001320 | 1/5 |
| 1 | -0.6912 | -0.2304 | -0.004626 | 1/5 |
| 1.5 | -1.1521 | -0.5069 | -0.009245 | 0/5 |
| 2 | -1.3825 | -1.1060 | -0.012612 | 0/5 |
| 3 | -2.2581 | -2.3041 | -0.021771 | 0/5 |

**Both REJECT_DEV; terminal ranking not opened.** Simple low-load bonuses sacrifice Gold even when Good sometimes rises. Raw exposure mixes fitness, race distance and campaign type; these results reject the two pre-registered encodings, not all possible workload hypotheses. No 4,800m exclusion rule, fitness probability or physiological claim was introduced. Minimum recovery gap is descriptive only, not another tuned ranking arm.


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
