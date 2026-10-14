# EXP-20261014-07 — AU ranking-sensitivity

- Status: COMPLETED — diagnostic association; NEEDS_MORE_TESTING, no ranking intervention.
- Hypothesis: Selection fragility to declared going and lineup changes identifies less reliable races.
- Prior work searched: EXP-20261013-11 pace-score candidates REJECT; EXP-20260902-09 preparation score candidates REJECT; EXP-20260928-07 constrained reranker; source review docs/audits/2026-10-14-horse-analyst-borrowing-review.md.
- Definition: Overlay-only current engine wet_form_feature on Good4/Soft6/Heavy8 from captured going_stats_line; hold all other leaves fixed, explicitly partial sensitivity not a full going rescore. Track top4 membership/top1 stability; leader stress removes at most one other runner with lowest historical mean f800 where >=70% field has pace histories. Removal is hypothetical, not fabricated scratching or calibrated likelihood. Diagnostic Gold/Good by stability. No automatic ranking arm from these partial scenarios.

Baseline: freshly rescore current engine; no production mutations. Main eligibility: date >= 2026-08-05 and complete actual position set 1..N, unique runner identifiers; whole-date canonical terminal fraction 0.15 and five development time folds. Filter fixed for snapshot integrity before candidate outcomes. Previous terminal dates have been exposed in other experiments: these are retrospective tests, never automatic promotion. Primary Gold/Good non-regression, canonical au_eval Stage 4 v2; dev eligibility Gold/Good >= baseline, top5 AUC > baseline and at least 3/5 nonnegative Gold/Good folds. Select median eligible k, not argmax. k grid {0.5,1,1.5,2,3}; no terminal if dev fails. Diagnostic labels strictly separate; no odds feature. No combining candidates. Missing feature z=0. Cohorts: field-size <=8/9-10/11-12/13+, venue, going, maiden vs other, career <=4 vs other, baseline favourite SP buckets for evaluation only. Bootstrap seed7, 2000 paired race replicates.

Research output: scratch/horse-analyst-tests-20261014. Results and reproducible commands will be appended. No model code commit/push authorized by this experiment.


## 排名敏感度結果

Only races with prior wet-start evidence for >=70% of actual starters enter the wet-sensitivity comparison: **1,846 dev / 343 terminal**. Unknown wet records cannot be labelled robust merely because their neutral overlay stays zero. This missing-evidence correction affects only diagnostics, not scoring candidates.

Overlay-only Top4 stability: dev **1,277 stable / 569 changing**, Gold **23.26% / 14.06%**, Good **26.47% / 21.62%**. Terminal **240 stable / 103 changing**, Gold **20.42% / 13.59%**, Good **27.08% / 16.50%**. These groups are observational, not paired baseline/candidate models.

After standardizing the four field-size buckets:

| split | stable−changing Gold Δpp | diagnostic 95% CI | Good Δpp | diagnostic 95% CI |
|---|---:|---|---:|---|
| dev | +6.79 | [2.871228739738901, 10.584500492978211] | +1.89 | [-2.563213907150044, 6.3217861910808315] |
| terminal | +3.95 | [-5.277376201572549, 12.622230079012125] | +7.61 | [-2.786546555101204, 17.807462252728257] |

Terminal intervals cross zero; the 13+ bucket also has negative dev Gold association. Field adjustment does not remove all going/venue/history-quality confounding. **No claim of an independent calibrated confidence feature or improved ranking.**

### Full-engine mechanical cross-check

An outcome-blind hash sample of **16** race identities was additionally replayed using the current full RacingEngine under Good4/Soft6/Heavy8, and with one hypothetical other fast-history horse removed. **5/16** changed Top4 membership under going alternatives. **4/16** reordered remaining horses after removal beyond simply deleting that runner. No results used to choose this sample or scenarios; this is a wiring/stress check, not a performance test.

The full-engine removal rebuilds field summaries and filters pace-map member lists. It does not estimate the probability of a scratching or refit a new speed forecast. Large-corpus wet comparison is still **overlay-only**, not equivalent to full going replay. Its captured historical going aggregates are not independently timestamp-certified, so retrospective sensitivity is FLAG for deployment until forward snapshots exist.

**Decision: retain diagnostic evidence, NEEDS_MORE_TESTING.** No production monitor, betting rule, scheduler or ranking penalty added.


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
