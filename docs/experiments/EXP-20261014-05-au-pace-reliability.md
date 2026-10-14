# EXP-20261014-05 — AU pace-reliability

- Status: COMPLETED — ranking REJECT_DEV; diagnostic findings below.
- Hypothesis: Repeated early-position stability predicts lower next-race positioning errors and may add selection information.
- Prior work searched: EXP-20261013-11 pace-score candidates REJECT; EXP-20260902-09 preparation score candidates REJECT; EXP-20260928-07 constrained reranker; source review docs/audits/2026-10-14-horse-analyst-borrowing-review.md.
- Definition: Confidence = n/(n+4) * (1 - min(1, sd(f800)/0.5)), last up to six strictly prior unique formal runs with valid f800, min2. Diagnostic error is absolute next-race f800 minus historical mean, labelled only from later form; ambiguous same-horse/day labels excluded. Ranking arm +k*z(confidence).

Baseline: freshly rescore current engine; no production mutations. Main eligibility: date >= 2026-08-05 and complete actual position set 1..N, unique runner identifiers; whole-date canonical terminal fraction 0.15 and five development time folds. Filter fixed for snapshot integrity before candidate outcomes. Previous terminal dates have been exposed in other experiments: these are retrospective tests, never automatic promotion. Primary Gold/Good non-regression, canonical au_eval Stage 4 v2; dev eligibility Gold/Good >= baseline, top5 AUC > baseline and at least 3/5 nonnegative Gold/Good folds. Select median eligible k, not argmax. k grid {0.5,1,1.5,2,3}; no terminal if dev fails. Diagnostic labels strictly separate; no odds feature. No combining candidates. Missing feature z=0. Cohorts: field-size <=8/9-10/11-12/13+, venue, going, maiden vs other, career <=4 vs other, baseline favourite SP buckets for evaluation only. Bootstrap seed7, 2000 paired race replicates.

Research output: scratch/horse-analyst-tests-20261014. Results and reproducible commands will be appended. No model code commit/push authorized by this experiment.


## 步速可信程度結果

Coverage: **21,799 / 24,857 = 87.70%** runners have at least two valid prior checkpoints. Historical pace mean coverage 23,294 (93.71%). On **11,601** labelled dev runners, confidence versus absolute normalized positioning error has rho **−0.1641**, negative in all five folds. Using the dev median confidence threshold 0.318958, high-confidence mean error **0.2182** versus low **0.2535**; paired-race-cluster sampling of these diagnostic groups gives difference CI **[-0.0415, -0.0293]**. This is positioning accuracy, not winning probability.

Terminal labels cover only **53 runners / 42 races** (horses that subsequently appear in available form). Error 0.1950 versus 0.2325, difference CI **[-0.1263, +0.0498]** crosses zero. Labels are delayed/non-random because most recent races have not yet appeared in later form. Forward reliability validation remains insufficient.

| k | dev Gold Δpp | dev Good Δpp | top5 AUC Δ | primary nonnegative folds |
|---:|---:|---:|---:|---:|
| 0.5 | -0.2765 | -0.0922 | -0.001633 | 1/5 |
| 1 | -0.3226 | -0.7373 | -0.003248 | 0/5 |
| 1.5 | -0.6912 | -0.9217 | -0.005414 | 0/5 |
| 2 | -1.1060 | -1.1982 | -0.006853 | 0/5 |
| 3 | -1.7051 | -2.0737 | -0.011312 | 0/5 |

**Ranking: REJECT_DEV**, no terminal ranking test opened for this arm. A horse can be predictable without being competitive; adding confidence alone favours regular running styles and does not add enough outcome discrimination. **Diagnostic: promising on dev, NEEDS_MORE_FORWARD_LABELS**, no deployed confidence tag.


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
