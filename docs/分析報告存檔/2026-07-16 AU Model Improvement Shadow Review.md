# AU Wong Choi Model Improvement — Shadow Review

> Research-only. No live ranking weights or production Logic files were changed by this run.

## Evaluation frame

- Full labelled archive: **710 races / 7530 horses**.
- OOS validation window: **363 races**, expanding-date folds over the latter half of available dates.
- Promotion requires no loss in Top3 precision, winner-in-Top3, or Miss count, plus fold stability.

## Already-promoted large-sample improvements

| Feature | Prior validation evidence | Production status |
|---|---|---|
| Pure static 7D | 336 races: Good 17.6%→18.2%, Pass 38.1%→38.7%, 0-hit 46→43 | **Implemented** |
| Wet-form suitability | Expanding walk-forward: Soft box-trifecta 14.4%→16.6%; robust scale plateau 6–12 | **Implemented** |
| Measured PF pace | 687-race archive: Gold 33→37, Pass 285→298, Champion +0.9pp, W-in-T3 +2.0pp | **Implemented** |
| 7D bug-fix / de-dup review | 702-race dual-window A/B: aggregate GGP 444→478 with no metric regression | **Implemented** |

These are not new promotion candidates. The current run is only a regression check and cannot overturn a larger recompute-based walk-forward with a smaller stored-snapshot subset.

## 1. Existing wet-form feature regression check

| Wet overlay scale | OOS result |
|---:|---|
| production ability | 363 races; 21 Gold / 135 Good / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6% |
| reconstructed 0.00 | 363 races; 22 Gold / 137 Good / 300 Pass / 63 Miss; Top3 42.1%; W-in-T3 47.7%; Top1 18.7% |
| reconstructed 0.25 | 363 races; 22 Gold / 137 Good / 301 Pass / 62 Miss; Top3 42.2%; W-in-T3 47.7%; Top1 18.7% |
| reconstructed 0.50 | 363 races; 22 Gold / 136 Good / 300 Pass / 63 Miss; Top3 42.1%; W-in-T3 47.4%; Top1 18.7% |
| reconstructed 0.75 | 363 races; 22 Gold / 136 Good / 300 Pass / 63 Miss; Top3 42.1%; W-in-T3 47.7%; Top1 18.2% |
| reconstructed 1.00 | 363 races; 22 Gold / 136 Good / 299 Pass / 64 Miss; Top3 42.0%; W-in-T3 47.4%; Top1 17.9% |

- Non-zero wet overlay support: **48 races across 4 dates**.
- The reconstructed 1.00 row is diagnostic only; historical CSV rounding means production `ability_score` is the actual baseline.
- Rollback gate: **NOT TRIGGERED**.
- Decision: **KEEP the already-baked wet-form feature**. This short snapshot is underpowered relative to its original expanding walk-forward.

## 2. Fresh-trial / stale-official pace recency gate

- Trigger: last official run ≥60 days, trial ≤30 days, trial score ≥75, pace figure <60.
- Action: shrink half the stale pace deficit toward neutral, capped at +3.0 ability points.
- Affected OOS sample: **0 horses in 0 races**.
- Available trial-high / pace-low proxy rows: **11**; the strict dated trigger has insufficient support.
- Baseline: 363 races; 21 Gold / 135 Good / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6%
- Candidate: 363 races; 21 Gold / 135 Good / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6%
- Decision: **FAIL / HOLD**.

## 3. Pace-concentrated Top1 confidence gate

Fixed rule: abstain from a Top1 endorsement when pace figure ≥90 and pace supplies ≥50% of the Top1's positive matrix lift over the field median.

- Baseline Top1 win: **17.6%**.
- Flagged: **1 races**; flagged Top1 win **100.0%**.
- Retained coverage: **99.7%**; retained Top1 win **17.4%**.
- Decision: **FAIL / HOLD**.

## 4. Going refresh audit

- Recent Logic scan since 2026-05-01: **251 races**; comparable going present in **123**.
- Comparable archive mismatches: **0**.
- Warwick Farm 2026-07-15: **4/7 mismatches** (R4-R7 changed Soft 5 → Good 4).
- This is a data-correctness gate: the orchestrator should refresh going immediately before scoring when mismatches are material.

## Bake decision

**Keep all previously promoted improvements. No additional scoring candidate cleared the new promotion gate.**
