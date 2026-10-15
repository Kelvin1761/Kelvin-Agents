# EXP-20261015-01 — AU trial performance cutoff at six career starts

- Date: 2026-10-15; platform: AU.
- Request: investigate false trial signals in experienced horses. User confirmed
  stopping trial **performance** scoring at six or more career starts while
  retaining trial fitness/preparation context.
- Baseline: `b4373427` (fresh origin/main worktree).
- Prior research: EXP-20261012-31 (blanket PF trial removal regressed),
  EXP-20260903-03 (trial leaf transmission), EXP-20260904-01 (reallocation),
  EXP-20261009-03 (debut/first-up), model-evaluation-contract v3.

## Preregistered design (before candidate results)

One fixed cutoff, **career_race_starts >= 6**, specified by the user, no search
over cutoffs. Missing/non-numeric career totals retain baseline behaviour.

- Baseline: freshly dump current engine on the archive, read-only.
- A: trial_score neutral 60 for eligible horses, using production matrix mapping.
- B: remove tagged trial PF runs for eligible horses, rebuild PF aggregates and
  **whole-field** statistics before scoring through the current engine.
- AB: both A and B. No preparation, fitness or rider-continuity bonus removed.
- Coverage amendment **before B/AB results**: raw input census found trial time
  populated for 5,125 / 37,621 archived runner records (no missing career totals).
  The recent source-dead finding does not apply to the full archive. Add C:
  disable only the maiden trial-time form proxy for eligible horses, through
  the production form scorer; add ABC as the full requested candidate. Keep AB
  as the originally registered diagnostic. No extra cutoff or weight search.
  Verify C changes only form_score, B only pace_figure_score, and both retain
  preparation_score and jockey_horse_fit_score before composing ABC.
- No model weights, gains, overlays or evaluation rules changed.
- Verify saved baseline features replay the engine ability at four decimals.
- Use canonical AU metric extraction and Stage 4 v3 fixed_rule, 2,000 paired
  meeting-day bootstrap samples, seed 7, six chronological date blocks. Primary:
  Gold (actual first three inside model first four), Good positional. Ranking:
  top3_capture_at5, ndcg_at5, top5_pairwise_auc. Holm-adjust the amended five-arm
  family across all tested primary/ranking endpoints.
- Report field-size, going, venue, baseline favourite SP, first-up and career
  experience strata, plus within-race trial leaf AUC excluding neutral 60.
- Historical full record is retrospective evidence; separately report the clean
  capture era (2026-08-05 onward). Historical PIT/source integrity limitations
  remain; a statistical win alone does not authorize live activation. A winning
  fixed rule needs an untouched forward confirmation.
- No archive copies or live artifact writes. Dumps remain in /private/tmp and
  well below 1 GB. Main checkout unchanged.

## Results

**Decision: REJECT for activation; no demonstrated benefit. Production unchanged.**

Full paired record: **3,297 races / 32,572 runners / 138 race dates**, 2025-08-02
through 2026-10-14. Two dumped races excluded for incomplete podium/winner labels.
22,677 runner records have six or more starts. These are appearances, not unique
horses. August 5 onward capture-era subset: 2,496 races / 71 dates. No parameters
were fitted and no terminal tail was used to select a cutoff. No fresh forward
holdout was opened or claimed.

| Arm | Gold | Good positional | Pass | Ordered Top4 changed | Statistical diagnostic |
|---|---:|---:|---:|---:|---|
| Baseline | 627 (19.017%) | 825 (25.023%) | 1,578 (47.862%) | — | — |
| A: trial leaf neutral | 628 (19.048%) | 825 | 1,574 | 90 | ranking_evidence_too_weak |
| B: formal-only PF | 624 (18.926%) | 825 | 1,572 | 423 | primary_regression |
| AB | 623 (18.896%) | 825 | 1,568 | 488 | primary_regression |
| C: remove maiden time proxy | 627 (19.017%) | 825 | 1,578 | 5 | ranking_evidence_too_weak |
| **ABC: requested full cutoff** | **623 (18.896%)** | **825** | **1,568 (47.558%)** | **491** | **primary_regression** |

ABC vs baseline, percentage-point deltas, **unadjusted** day-bootstrap intervals:

| Metric | Delta | 95% interval |
|---|---:|---|
| Gold | -0.121pp | [-0.397, +0.160] |
| Good positional | 0.000pp | [-0.315, +0.297] |
| Top3 capture at5 | -0.063pp | [-0.221, +0.082] |
| NDCG at5 | -0.032pp | [-0.155, +0.088] |
| Top5 pairwise AUC | -0.083pp | [-0.180, +0.013] |

No overall interval excludes zero; the deterioration is a point estimate, not
proof of overall harm. All ABC endpoint Holm-adjusted p-values are 1.0 across
the five arms and five registered endpoints. Gold six block differences:
0, 0, 0, -0.376, -0.364, +0.247pp. Baseline-vs-baseline A/A is correctly rejected
as ranking_evidence_too_weak. The fixed-rule primary gate rejects ABC because
its full-record Gold point estimate is negative.

Capture-era subset independently reports the same direction: Gold **514→510**
(20.593%→20.433%, -0.160pp; CI [-0.515,+0.199]), Good **650→651**
(+0.040pp), Pass -9 races (-0.361pp). C has zero Top4 changes in this subset.
This subset is a historical capture-era check, **not** independent certification
of every input's point-in-time availability.

Marginals: adding A to B loses one additional Gold / four Pass; adding C to AB
leaves Gold/Good/Pass totals unchanged. A and B together are not additive because
changes interact around the ranking cutoffs. No arm meets the activation rule.

### Cohorts and signal strength

ABC vs baseline, descriptive deltas (not used to tune the candidate):

| Cohort | Races | Gold delta | Good delta |
|---|---:|---:|---:|
| Field <=8 | 963 | -0.623pp | +0.208pp |
| Field 9–10 | 1,083 | +0.092pp | -0.369pp |
| Field 11–12 | 829 | 0.000pp | +0.241pp |
| Field 13+ | 422 | +0.237pp | 0.000pp |
| Baseline top pick SP $1–3 | 1,106 | -0.542pp | -0.362pp |
| Baseline top pick SP $3–6 | 1,315 | 0.000pp | +0.456pp |
| Baseline top pick SP $6–11 | 574 | +0.174pp | -0.348pp |
| Baseline top pick SP $11–21 | 250 | +0.400pp | 0.000pp |
| Baseline top pick SP $21+ | 50 | 0.000pp | 0.000pp |
| Baseline top pick first-up | 568 | +0.176pp | -0.176pp |
| Baseline top pick second-up | 425 | -0.706pp | -0.235pp |
| Baseline top pick 6+ starts | 2,154 | -0.139pp | +0.093pp |

Small-field Gold CI [-1.140,-0.202]pp; short-priced-pick Gold CI
[-0.978,-0.179]pp, both **unadjusted descriptive** cohort findings. With many
cohorts examined they are warnings, not independently confirmed significance.
Going and venue/meeting-layout label diagnostics are in the local result JSON;
the latter retains the archive's race-range suffix and is not a pooled venue
analysis. Sparse venue groups must not support a general claim. SP is a
post-score diagnostic label only, not a scoring input or betting-price backtest.

Trial leaf within-race AUC, comparing placed/unplaced horses **within the same
experience cohort**, excluding neutral 60:

| Experience | Non-neutral runner records | Comparable pairs | AUC |
|---|---:|---:|---:|
| 0–5 starts | 8,801 | 11,749 | 0.5953 |
| 6+ starts | 15,679 | 21,336 | 0.5473 |

The signal is weaker in experienced horses but this is descriptive discrimination,
not its incremental contribution to final selections. The ablation did not
demonstrate that deleting it improves selection. Overall ranking intervals also
span zero; do not turn limited power into a claim that trials are useless.

### Scope verification and safety

- All baseline and candidate saved feature vectors replay engine ability exactly
  to four decimal places: max error **0.0**.
- B removes **13,107 trial PF rows across 6,412 archive horse appearances** before
  field summary construction. Of evaluable runners, **14,220 pace_figure_score**
  values change (including other horses through field normalization).
- C changes **67 form_score** values and no other leaves.
- Preparation and jockey-horse-fit scores are exactly unchanged for B and C;
  wet/class overlays unchanged. A changes only trial_score. The full combined
  vector uses disjoint form/PF/trial leaves through the production mapper.
- Trial leaf enters a special debut bonus only at zero starts, so that branch
  cannot fire in the six-start target cohort. Trial preparation/continuity
  bonuses and narrative context remain available.
- Leakage audit: career totals and trial inputs are recorded prerace fields;
  PF refresh filters run dates to strictly before race date; outcomes join only
  as evaluation labels and are never passed to the scorer. **Inherited FLAG**:
  source/capture availability of historical inputs is not independently certified,
  especially before 2026-08-05. The script passes `leakage_audit_passed=True`
  **only to expose the statistical diagnostic**, explicitly records the FLAG and
  prohibits treating that result as a promotion verdict. No safety PASS claimed.
- No production engine edits, golden snapshot updates, baseline calibration or
  live artifact writes. Golden/data-contract/model-description checks unchanged.
- `./檢查.sh --quick`, full `./檢查.sh`, and scoped ruff: **PASS**.

## Reproduction and preservation

Research script: `scratch/au_trial_six_start_20261015.py`. All raw artifacts are
under `/private/tmp/au-trial-experience-*`, about 26 MB per dump, no corpus copies.
Data root: `/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing`.
Results CSV: `AU_Historical_Raw_Race_Results.csv` under that root. Archive inputs
may evolve; the following hashes identify this run's exact derived inputs.

| Input | SHA256 |
|---|---|
| baseline.json | `9612b5e6f28dcba181fc03e7655fa4100002a62753b246760af2d0a9ad5edb54` |
| pf.json | `95c03ec167ad5b8eb3ea4b6f1ce0400cf9b5683c9a2da0ce9761d937d2be7394` |
| form.json | `9d978adf3271b1b6b649dd1db3ba10744eb1af51845da6ec08f56cc12ca09978` |

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py \
  --out /private/tmp/au-trial-experience-baseline.json
python3 scratch/au_trial_six_start_20261015.py dump-pf \
  --out /private/tmp/au-trial-experience-pf.json
python3 scratch/au_trial_six_start_20261015.py dump-form \
  --out /private/tmp/au-trial-experience-form.json
python3 scratch/au_trial_six_start_20261015.py evaluate \
  --baseline /private/tmp/au-trial-experience-baseline.json \
  --pf /private/tmp/au-trial-experience-pf.json \
  --form /private/tmp/au-trial-experience-form.json \
  --out /private/tmp/au-trial-experience-results.json
```

Preservation: research-only branch `codex-au-trial-experience-20261015`; no release,
production model change, merge, activation or claim of improved performance.
