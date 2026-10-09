# Happy Valley feedback audit — 2026-10-08

## Status and scope

> 2026-10-09: the "First priority: data correctness" items are fixed and shipped as a
> §7 correctness fix (EXP-20261008-07). They do not change the 10-07 feedback ranks
> materially. The structural hypotheses below remain untested.

Diagnostic, not a validated model improvement. No scoring changes or production
rankings are made by this audit. User preference: pure 7D, no complete-strength
overlay, pre-race evidence, whole-field evaluation rather than horse-specific fixes.

## Provenance warning

Meeting: `/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/2026-10-07_HappyValley`.
The user-matching root scores match `Prediction_Snapshots/20261008T000539+1100`
(21:05 Hong Kong on October 7), not the morning immutable snapshot. Therefore
these scores cannot be described as a frozen pre-meeting prediction for every race.
The morning and intermediate snapshots give different R3 rankings. Establish
which version was actually displayed at each race's pre-off cutoff before
publishing performance statistics.

Replay checkout: `/private/tmp/wc-dashboard-all-scores-20261008`,
commit `60c951acd672a811515a2ff0e66112c53b919946`.
Replay output: `/tmp/hkjc-hv-feedback.j5VUdJ`, isolated copies of root Logic JSON.
Command (from checkout):

```sh
WONGCHOI_HK_DATA_ROOT='/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing' PYTHONDONTWRITEBYTECODE=1 WC_DISABLE_POST_SUCCESS_DEPLOY=1 python3 .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py /tmp/hkjc-hv-feedback.j5VUdJ
```

All nine race scoring runs completed. This is a retrospective replay of supplied
inputs, not a leakage-cleared backtest. The explicit data root matters: an initial
replay without it lacked rail history and misleadingly moved R3 #4 to second.
With rail history restored, #4 remains third. Distance suitability V2 remains
shadow in this contract; changes must not be attributed to its activation.

## User-matching ranks and latest-code replay

Each row lists actual first, second and third, with model rank old → replay.

| Race | Actual top three and model ranks |
|---|---|
| R1 | #9 連連好運 4→4; #4 竣誠駒 9→10; #8 寶成智星 11→11 |
| R2 | #7 新力 4→4; #5 環球英雄 3→3; #9 駿馬之光 12→12 |
| R3 | #4 卓越蒨鋒 3→3; #6 有情有義 2→2; #3 大文豪 10→10 |
| R4 | #8 超開心 5→4; #2 深心星 6→6; #10 準希望 2→2 |
| R5 | #8 佐治傳奇 3→3; #10 鋼鐵安防 4→4; #2 長勝金剛 12→11 |
| R6 | #10 頑童 5→5; #4 銳不可當 11→10; #5 加州勇勝 2→2 |
| R7 | #9 朗日自強 3→3; #5 觀眾之力 1→1; #10 天馬行雲 6→6 |
| R8 | #9 大千雄心 8→8; #8 金滙千帥 9→9; #3 盈好威楓 6→7 |

R1–R8 Gold and Good remain zero; top-three capture@5 remains 13/24.
Latest code alone does not resolve this feedback.

## First priority: data correctness

1. **Invalid zero ranks enter recent form.** R3 #2 has `0-6-7-3-1-8`, while
   `recent_6_detail` and the six rich formguide rows show `6-7-3-1-8-2`.
   `_merge_profile_history_for_stats` admits profile placing 0, and `compute_stats`
   uses the merged first six rows and first row's date before its later positive
   placing filter. `FormScorer` maps 0 through `rank <= 5` to 60 and counts it
   through `rank <= 3` in its top-three narrative. Other recovery/consistency
   consumers require review too. Do not simply discard every non-finisher:
   distinguish withdrawals, DNF and missing results using original status.
2. **Historical rich-row alignment is inconsistent.** In R3 #2 Facts, the
   2026-03-04 row says finish 3 but running positions end 7; 2026-01-28 says finish
   1 but positions end 3; 2025-12-23 says finish 8 but positions end 1. These
   conflicts are independently observable, but which source is correct is not
   established here. Audit horse/date/race-ID joins before trusting sectionals,
   margins or trip descriptions. Do not force the final position to equal the
   placing: official amendments can legitimately differ.
3. **Surface reliability metadata parser.** The target-surface score is selected,
   but an `今場=.*?有效樣本` regex can take the first listed surface's sample size
   rather than the target surface's. This explains target local-history scores
   paired with zero sample metadata; it is not evidence of a scoring gain.

## Structural hypotheses, not validated fixes

- **Draw prior dominates rail correction.** Inner/middle/outer prior is roughly
  75/65/49.06; rail-context v2 only adjusts ±4. HV shape feeds 27.37% of the matrix.
  R3 #2 shape 66.13 versus #4 53.46 contributes about 3.47 raw composite points
  before whole-field capping. Test a historical, reliability-shrunk base draw
  effect by venue/surface/distance/rail, rather than simply increasing the rail
  cap. Draw is useful in historical diagnostics; removing it is not supported.
- **Horse evidence versus rider/trainer priors.** R5 #4 versus #8 has JT 82.75
  versus 65.5 and shape 77.87 versus 67.11, despite similar stability. R6 #9 has
  JT 79.45 versus winner #10's 62.2, while its sectional score is lower. Test
  reliability and incremental contribution, not a manual demotion of these horses.
- **Opponent strength is not own demonstrated performance.** R3 #2 form-line 96
  versus #4's 82, and R7 #3's 91 versus #9's 78, can materially influence tight
  ranks. Verify point-in-time opponent histories and whether a poor run inherits
  too much credit merely for facing good opponents; ablate separately.
- **Sparse evidence and course transfer.** R6 #4 has two weak finishing results
  but strong sectional evidence; R8 includes a lightly evidenced course-distance
  winner and a first-1650 runner. Test uncertainty-aware shrinkage and validated
  distance/surface components; do not award a blanket bonus for one prior win.

Pre-race favourites may be an external comparator, but odds must not enter as a
hidden feature. Post-race incidents are explanatory outcomes, not pre-race inputs.
R6 後無來者's report describes a heart problem; calling this simply human error
is not established. An outside draw does not establish an outside-lane track bias.

## Next implementation/evaluation sequence

1. Lock the actual pre-off artifacts and reconcile invalid-status rows plus
   horse/date joins; add fixtures covering withdrawals, DNF, duplicate sources,
   same-date conflicts and race-date cutoffs.
2. Run the correctness-only replay against identical frozen inputs, separately
   from any model refit. Report rank changes and unresolved source conflicts.
3. On cleaned historical development data, separately ablate contextual base
   draw, rider/trainer reliability and own-performance-conditioned form-line.
   Preserve 7D and refit only supported components, with regularisation.
4. Keep the canonical split and evaluation contract unchanged. Do not use this
   meeting or repeated terminal evaluation to select weights. Report Good,
   Capture@5, Gold, NDCG, paired uncertainty and both venue cohorts. Earlier
   ad-hoc HV-only split calculations are exploratory and not promotion evidence.

No performance improvement is claimed, and no new model release is authorised
by the Dashboard SHA approval.
