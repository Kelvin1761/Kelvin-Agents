# EXP-20260902-10 — HKJC dated Race Shape components

## Pre-registration (before candidate measurement)

Scope: local HKJC only; improve component evidence, not a new outer-weight fit.
The seven production weights, draw prior, debut routing, SIP and evaluation
contract remain locked. No deployment, archive overwrite, commit or push.

Precondition: repair PIT raw-source omissions and missing distance metadata in
memory, with exact horse/date identity and source manifest. Replay baseline and
candidates with that same repaired source. Do not compare their absolute numbers
with EXP-08's incomplete-prior baseline as if that were a model gain.

Dataset: the same 264 races / 3,318 runners as EXP-08. Fixed cutoff 2026-06-13:
180 dev / 84 terminal. Terminal was previously examined; it is not pristine.
Read current target results only for evaluation. Candidate signals use dated
historical Facts rows, exact horse-name alignment, date strictly before target,
same venue/surface and distance within 20%, at most 365 days old. No odds,
speed-map, predicted pace, leader count, current race result or current incident.
Class from historical rows is retained for audit but not assumed comparable to
an unreliable current Facts class header. Missing/ambiguous source is neutral.

Bounded hypotheses; parameters below are fixed without outcome-based selection:

- A (fit): rebuild inner/outer comparison from dated, context-matched rows using
  beaten margin (not raw finish position). Recency weight 2^(-age/90). Compare
  weighted means capped at 10 lengths; retain original 1-length preference
  threshold and original match/mismatch/slot magnitudes. Attenuate by
  min(inner effective count, outer effective count)/(that count + 3).
  Existing PI contribution stays unchanged. Missing one group => no fit delta.
- B (trip): replace unconditional low-consumption reward/high-consumption penalty
  with limited evidence of *competitive performance despite wide travel* and
  *weak performance despite economical travel*. For up to three most recent
  matched runs: `wide=clip((mean_XW-2)/2,0,1)`,
  `close=clip((3-margin)/3,0,1)`, `easy=clip(2-mean_XW,0,1)`,
  `weak=clip((margin-3)/6,0,1)`, delta=`8*wide*close-6*easy*weak`.
  Weighted sum using the same 90-day decay divided by (sum weights + 1).
  This is a hypothesis, not a claim that every wide run deserves an excuse.
- A+B: only predeclared interaction; evaluate A, B and A+B separately. Sha Tin
  uses unchanged 55/25/20 component weights. Happy Valley preserves its existing
  context contributions except the corresponding fit/trip terms (new trip delta
  scaled by 0.1 to preserve its small adjustment role).

Evaluation order: baseline replica exactness; pre-candidate neutral-component
power; leaf within-race AUC; dev and five chronological folds. A candidate with
dev Gold or Good regression is rejected before terminal confirmation. Do not
search further parameters to rescue it. A dev survivor must have primary gain
or at least two predeclared ranking gains; if multiple survive, prefer a single
component, then A before B. Only that one gets terminal confirmation.
The fold screen is at least 3/5 chronological validation blocks with neither
primary regressing (fixed before the replay completed; no candidates measured).
Historical surface not explicitly present in Facts must be confirmed against
that horse's dated result-table Track; otherwise omit that historical row. The
target uses the engine's grass-default convention where AWT is not specified.

Metrics: canonical Gold (all actual Top3 in model Top4), Good positional (both
Top2 place), Top2 place captures, zero/one-hit, capture@5, mean Top3 model rank,
competitive recall@5, NDCG@5. Paired race bootstrap 2,000, seed 7. Report venue,
field-size, sparse-schema and weak-race cohorts; Rank3-to-Top2 gains AND displaced
successful Top2 horses. Power limitation does not excuse primary regression.

Deployment requires the existing Stage4v2 gate and a satisfactory provenance
audit; retrospective dated rows are not proof of immutable pre-race capture.

## Results

Initial run (2026-09-03 00:15, `/private/tmp/hkjc-dated-shape-20260903`) rejected
all three candidates on dev; terminal candidate metrics were not evaluated.
Further replay audit found **10 Sha Tin races with literal `venue="Unknown"`**:
`setdefault` failed to replace the sentinel and the old engine routed those
races through the non-Sha-Tin equation. This is an independent identity bug,
not a reason to tune the candidate. The replay adapter now resolves only
missing/unrecognized venue from the dated meeting directory, preserves AWT,
and rejects contradictory known venues. Same 264 races, same split and same
A/B equations are rerun against the corrected baseline. The first output is
retained; its development results are superseded, not presented as valid gains.

### Final verdict — REJECT_DEV, no production model replacement

Final run: `/private/tmp/hkjc-dated-shape-venuefixed-20260903`.
All 3,318 ability scores reproduce production exactly; component reconstruction
also reproduces all scores and orders, including matrix rounding and SIP.
The three predeclared candidates fail the development primary guardrail. No
candidate terminal metrics were computed or used to choose another formula.
The 84-race terminal **baseline** and neutral-component power were measured,
as predeclared; this is not a new untouched holdout.

| Dev, 180 races | Baseline | A: contextual fit | B: trip quality | A+B |
|---|---:|---:|---:|---:|
| Gold (all Top3 in model Top4) | 24 | 24 | 26 | 25 |
| Good (both Top2 place) | 49 | 47 | 48 | 44 |
| At least 2 hits in Top3 | 87 | 84 | 88 | 84 |
| 0-hit races | 28 | 26 | 29 | 25 |
| 1-hit races | 65 | 70 | 63 | 71 |
| Placed horses captured by Top2 / 360 picks | 182 | 179 | 182 | 177 |
| Actual Top3 capture@5 | 66.48% | 66.30% | 66.67% | 66.67% |
| Actual Top3 mean model rank (lower better) | 4.6463 | 4.6407 | 4.6167 | 4.6019 |
| Competitive recall@5 | 60.46% | 60.41% | 60.35% | 60.55% |
| NDCG@5 | .55626 | .55304 | .55573 | .55309 |

This is not rejection merely because of one unlucky race. B redistributes
successful selections rather than producing a net Top2 gain: **7 placed horses
enter Top2 (6 from old Rank3), while 7 previously successful Top2 horses leave**.
A gains 5/drops 8; A+B gains 7/drops 12. None meets the overall ranking objective.

### Weak races and collateral losses

The fixed baseline has **93 development races with 0 or 1 hit**. A rescues 3 to
2+ hits but loses 6 previously passing races; B rescues 4 but loses 3; A+B
rescues 5 but loses 8. A+B rescues 6 zero-hit races but creates 3 new zero-hit
races: the headline 28→25 conceals worsening Top2 capture and 1-hit counts.
Every changed weak race, affected horse, pre-race history and score evidence is
preserved in the companion JSON; no outcome-specific overrides were added.

Illustrative B outcomes (explanations use past evidence, not current results as inputs):

- 2026-05-31 Sha Tin R2: #3 一舖掂晒 had an economical prior run but lost by
  18 lengths. Old trip score 70 rewarded low consumption regardless of outcome;
  B gives 58.66. #8 嘉應耀昇 moves Rank3→2 and wins. Its own new trip evidence
  is neutral: this is removal of a competitor's excessive bonus, not a discovered
  positive signal for the winner.
- 2026-06-07 Sha Tin R3: #4 天天更好 moves Rank3→2 and places. An earlier
  win averaging 2.5W supports a small positive, recency-shrunk trip score
  60.74 instead of the old 50. This supports investigating qualified wide-trip
  evidence rather than an unconditional high-consumption penalty.
- 2026-05-03 Sha Tin R9: #4 盈好威楓 moves Rank2→3 despite placing;
  #7 發財先鋒 moves into Top2 but finishes 11th. Past histories span different
  classes/distances. Small trip differences cannot safely resolve their ability
  difference; the new formula has not established conditional value beyond form.
- 2026-05-20 Happy Valley R1: placed #1 英雄豪邁 drops Rank2→3, while
  #11 太行美景 moves up and finishes sixth. Historical rows for the former
  include Class4 and for the latter Class5. This highlights why class context
  and neutral-score relief must be separated before treating trip score as ability.

Cohorts: B's Top2 placed-count delta is +1 in Sha Tin turf, −1 in Happy Valley,
0 in AWT; −2 in 11–12 runner races and +2 in 13+ races; −1 sparse-schema and
+1 rich-schema. A/A+B losses concentrate in Sha Tin. These are descriptive
development cohorts, not post-hoc exceptions or venue-specific tuning rules.

### Data work retained, candidate logic remains research-only

- PIT source: 20,454→**21,107** rows; 171→176 dates. Added 653 rows from
  2026-05-20, 06-21, 07-01, 07-08 and 07-12. Filled **2,155** missing
  distances/class metadata using date/race/horse-number **and name** joins.
  Distance now available for 20,988 rows; 119 remain missing rather than invented.
  Duplicate outcome copies are verified; conflicting identities fail closed.
- The local supplement is in memory only. No source CSV, Logic, Facts, result
  file or prediction ledger was rewritten; current results still enter aggregate
  priors only on later dates via strict `< meeting_date`.
- IDs are retained in cross-date horse grouping. Source has one display name
  associated with two IDs (齋月 K309/K911); do not silently merge these.
- Historical candidate rows have dates, identity deduplication, surface/distance
  matching and 90-day recency shrinkage. 2,495/3,318 runners have usable matched
  history; 1,515 have both inner/outer support. 1,523 historical rows lack a
  confirmable surface and are omitted; 6,748 fail context matching.
- Parser rejects future/current dates; missing history produces a neutral
  candidate term. Archive capture immutability remains **FLAG**; this work does
  not claim that the entire archived model is leakage-free. Existing trackwork
  identity and current Facts class-header inconsistencies are outside this
  component experiment and must not be assumed solved.

Within-race dev discrimination of **nonneutral** candidate leaves is AUC .5283
for fit (918 pairs) and .6279 for trip (3,018 pairs). These use different coverage
and are not a causal before/after improvement claim. Trip has a plausible signal,
but its addition to the full matrix has not improved total Top2 capture.

Pre-candidate neutral-component budget is below terminal CI half-width for all
four registered ranking metrics. Ranking-only evidence is underpowered here;
that does **not** override the observed development primary regressions.

### Next bounded hypothesis

Retain B as a research direction, not a deployed model. Next isolate the extra
information in wide-trip evidence **after accounting for existing form/stability
and class/distance context**, and distinguish positive evidence from simply
removing an old penalty. Repair/verify current class metadata before using it.
Do not turn these four examples into horse-specific bonuses, force Rank3 swaps,
increase Race Shape weight, or tune on the terminal data. A's inner/outer
preference is weak; no reason to expand its complexity or influence now.

### Reproduction / checks

```bash
PYTHONDONTWRITEBYTECODE=1 WC_DISABLE_POST_SUCCESS_DEPLOY=1 python3 scratch/hkjc_dated_shape_20260902.py --out /private/tmp/hkjc-dated-shape-venuefixed-20260903
PYTHONDONTWRITEBYTECODE=1 python3 scratch/hkjc_dated_shape_review_20260903.py /private/tmp/hkjc-dated-shape-venuefixed-20260903 --out docs/experiments/EXP-20260902-10-hkjc-dated-shape-evidence.json
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest scratch/test_hkjc_dated_shape_20260902.py .agents/skills/hkjc_racing/hkjc_reflector/tests -q
./檢查.sh
```

- HEAD during final run: `165f923a1aa43a34f9ae0c1e2a1df0e328b6090e` (shared dirty
  checkout; exact source hashes recorded, not a clean-commit reproducibility claim).
- Race/source sample SHA: `dc8a79318d558286c3f65e3aa6baab2cb33723cd0cc17e78ead656e6dbe708a9`.
- Corrected raw-table SHA: `8d5edf509d37fe888e979aefa159c021408d17c80379013ec7b7446f6068a2f5`.
- 39 focused tests passed. Full `檢查.sh`: all 10 suites passed; HKJC 56 passed;
  HKJC golden 120 horses unchanged; data contract and generated documentation
  freshness pass. No production scoring/golden change, deployment or push.
- Evidence: [machine-readable results](EXP-20260902-10-hkjc-dated-shape-evidence.json).
