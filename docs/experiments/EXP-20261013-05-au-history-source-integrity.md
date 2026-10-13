# EXP-20261013-05 AU history source integrity

## Registered design

Baseline: clean origin/main c9620bd0f37381a7b3634e3b8d2e2f8b5247c6f1.
Mode: fixed_rule under the current main v3 evaluation contract; no fitted constants.
Dataset: the existing EXP-02 eligible 1,762 development plus 771 terminal races,
2026-08-05 through 2026-10-12. The exposed Tamworth meeting stays excluded.
No new split, no odds inputs, no outcome-conditioned eligibility.
Same fresh Logic/Facts/Formguide and resource paths for both arms; full pre-race
fields determine feature normalization, aligned result runners determine metrics.

Arms: baseline; A = explicit decoded form format, non-standard result transport,
PF provenance/atomic refresh; A+B = shrink L600 score deviation from 60 by
min(1, evidence count/3). Three is the existing scoring threshold for sufficient
field evidence, not a fitted parameter. Counts use the actual selected L600 basis.
No age threshold or hand-picked Tamworth penalty. B is exploratory model policy,
not automatically releasable as a correctness fix. Do not search alternate counts.
Primary Gold/Good; paired day bootstrap 2,000 seed7; six contiguous date blocks;
field-size four cohorts and baseline first-pick SP five cohorts. SP joins after scoring.
A is independently provable correctness; no claim of measured improvement without
passing evidence. B needs v3 promotion evidence and forward confirmation.

## Root cause and correction of premise

The cached Sportsbet source contains `Finished -3/7`, Inverell R2 2025-11-22.
The unsigned Finished regex silently drops the entire formal start. Racing NSW
confirms third past the post, disqualified AR240(1) on 2026-03-10, before the
2026-10-12 target race. Last10 `0` does not prove tenth place or a heavy defeat.
https://mdata.racingnsw.com.au/FreeFields/Results.aspx?Key=2025Nov22%2CNSW%2CInverell

Transport negative/zero provider results as NON_STANDARD, retain original raw
finish, formal start/date/class/field, leave valid placing and beaten margin unknown.
Never reconstruct a podium from results or Last10 for this row. Unknown status must
not contribute to margin quality or PF; known all-non-standard history must not be
penalized as an invented tenth place. Avoid making a general claim that every
negative provider code has the same legal disqualification reason.

Latest main already tested blanket trial removal in EXP-20261012-31 and rejected
it. Preserve that result. Trials remain a declared speed-context input, now with
trial/formal counts and source dates in the engine detail and explanation.
Case reconstruction uses only the dated historical row from raw cache, never the
same-day result or updated career/odds; retrospective status availability is known
for the case but unverified for any wider archive backfill, which is not performed.

## Harness issue (discarded run)

Loading baseline source from its rollback directory also changed resource lookup
paths, making track geometry unavailable and moving preparation scores. That run
was interrupted and is invalid. Corrected harness binds both modules to identical
main resource paths before any scoring. The repair is mechanical, not a candidate
or KPI change. Report only the rerun.

## Results and release decision

Corrected same-resource run: 2,533 races, source fix zero ability/rank changes on
existing archived formguide inputs; Gold/Good/Pass and six time blocks/cohorts all
zero delta. These archives do not acquire a previously dropped row merely by
re-scoring Logic: future extraction/re-extraction must use the repaired parser.
The recovered raw-source case and synthetic negative-result fixtures verify that
transport chain independently. **This is not a proven predictive improvement.**

Weak-PF count shrink changed 2,129 pre-race runners. Gold 0pp (day-bootstrap CI
[-0.3000,+0.2783]pp), Good -0.1184pp (-3 races; CI [-0.3997,+0.1583]pp),
Pass -0.3948pp (-10 races). Good nonnegative in only 3/6 time blocks.
V3 decision: REJECT primary_regression. No shrink rule, age penalty, blanket trial
exclusion, coefficient or 60/40 blend change enters production.

Case reconstruction (exposed; excluded from evaluation): current-main baseline
62.2027 rank3/8; restored formal non-standard row 63.5011 rank3/8; rejected research
shrink 61.6738 rank3/8. Original published 64.8516/rank2 is a different version.
Source correction can increase a score: removing an invented tenth-place penalty
is not evidence of getting worse. The true row has unknown valid placing/margin,
not a made-up heavy defeat. Current retained trial-context score remains 84.075151;
report now explicitly shows one trial, zero formal PF runs, date2025-11-04 and thin
evidence. Trial context is an intentional existing input, not a formal speed record.

Commands: `PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python
 docs/experiments/patches/au_history_source_evaluation.py` with
`AU_INTEGRITY_WORKTREE` pointing to the isolated candidate. Baseline source copies
under `scratch/au_history_source_fix_20261013/release_baseline` come from immutable
c9620bd0, same resource paths are explicitly bound in the harness. Frozen runtime
SHA db0ffe220069c1c8e3b40275a5e497355c95ed977b3505d2e578a541c12f9519;
paired inputs/metrics stored in evaluation.json and paired_abilities.json.
Summary, six blocks, cohorts and case: docs/audits/au-race-weight-oracle-20261013/HISTORY_SOURCE_EVIDENCE.json.

Golden --record was run and inspected; it selected different horses from the now
expanded corpus, while the combination formula itself is unchanged. Preserve the
original committed golden fixture set, verify it unchanged, retain the re-recorded
sample and old snapshot separately in scratch. AU contract calibrated2000 races /
19781 runners; AU model explanations generated, HKJC generated output removed from
release scope because its source was not changed.

A pre-existing rounding-boundary test fails with Python3.14's changed float sum
but passes unmodified with AU production /usr/bin/python3 (3.9.6). An attempted
test adjustment was rejected by automatic approval and was never applied. Full
release gates use the production interpreter; no test is relaxed or skipped.
