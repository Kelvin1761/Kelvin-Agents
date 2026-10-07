# EXP-20261007-01 — HKJC pre-race draw context v2

Status: **PROMOTED TO LIVE RANKING BY EXPLICIT USER APPROVAL**.

## Hypothesis

The fixed draw prior is too coarse. A rail configuration whose historical draw gradient is flatter than the venue/distance parent should reduce the fixed inner bonus and outer penalty. Only information dated before the target race is allowed.

## Locked candidate

- Turf only; AWT unchanged.
- Draw groups: 1–4, 5–8, 9+; distance bands: 1000–1200, 1400–1650, 1800+.
- Compare `venue × rail × distance band × draw group` with its `venue × distance band × draw group` parent.
- Shrink both excess-place rates with 60 pseudo-runners.
- Activate a cell only at 100 prior runners and 20 prior races; otherwise no change.
- Add the relative rail effect to the current draw score, capped at ±4 draw points.
- Convert to race-shape by the live formula: HV 100%, ST 55%; keep the live 27.37% outer weight.
- Debut runners unchanged. No same-day result or in-running position is used.

## Locked evaluation

Chronological final 15% dates are terminal. Five expanding development blocks must have aggregate Gold and Good non-negative, at least 3/5 blocks non-negative on both, and at least two of top-3 capture@5, competitive recall@5 and NDCG@5 positive. Terminal stays closed if the gate fails.

Decision: no live promotion from this experiment alone; a pass creates a prospective shadow candidate.

## Result

Corpus: 342 races / 4,259 runners / 34 meetings, 2026-04-12 to 2026-10-04. Development used 162 validation races; the final 60 races were opened only after the candidate passed the locked gate.

| Window | Gold delta | Good delta | Champion delta | Capture@5 delta | NDCG@5 delta |
|---|---:|---:|---:|---:|---:|
| Development | +0.62pp | +1.23pp | +0.62pp | +1.44pp | +0.78pp |
| Terminal | 0.00pp | 0.00pp | +3.33pp | 0.00pp | +0.71pp |

Development ranking gains had positive 95% paired intervals for capture@5, competitive recall@5 and NDCG@5. Terminal NDCG CI crossed zero; Gold and Good were exactly unchanged. Mean terminal ability movement was 0.234 points and maximum 1.095 points.

**Initial decision:** retain as a prospective shadow because the terminal ranking CI crossed zero. On 2026-10-07 the user explicitly approved promotion based on the passed development gate, exact terminal Gold/Good no-regression and the operational need for rail-aware ranking. The conservative cap and sample gates remain unchanged.

## Implementation

- Official scoring: `pre_race_draw_context_v2` now updates `draw_score`, race-shape, ability and rank.
- Rollback shadow: `pre_race_draw_context_v1_generic` reconstructs the prior generic draw ranking.
- Every immutable pre-race Logic snapshot now carries the candidate ability and full candidate ranking.
- Post-race automation refreshes `rail_draw_results.csv` before the next meeting.
- Historical V2 shadow snapshots remain settleable; the live model has a separate immutable V1 rollback comparator.
- 2026-10-07 Happy Valley C+3 dry run: eight of nine races had stable cells. The 1800m race stayed neutral because its 18–19 prior races did not meet the locked 20-race floor. Five races had a changed shadow Top 4; official rankings were untouched.
- Venue partition is mandatory: `venue` is part of both cell and parent keys. Sha Tin A and Happy Valley A are independently estimated and regression-tested.

## Activation run — 2026-10-07 Happy Valley

- Re-scored all 9 races / 108 runners with contract `HKJC_7D_CONTRACT_2026_10_07_PIT_RAIL_DRAW_V2`.
- Race QA: 0 errors, 0 warnings, 91.4% coverage.
- Immutable local prediction snapshot: `Prediction_Snapshots/20261007T025409+1100`.
- Against the V1 generic-draw rollback on the same recalculated model, official Top-4 order changed in R3 and R4; the Top-4 membership stayed the same.
- Real-data venue-separation check for A-rail 1650m outer group: Sha Tin `+0.9296`, Happy Valley `-2.1005`. Both cells were independently stable; no cross-venue pooling occurred.
- Dashboard deployment remained blocked pending the repository's immutable release-SHA approval flow; local official artifacts and snapshot were updated.

Implementation files:

- `.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/rail_draw_context.py`
- `.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/engine_core.py`
- `.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_shadow_monitor.py`
- `.agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py`
