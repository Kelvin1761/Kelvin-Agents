# AU Wong Choi Phase-5 Candidate Shadow Tests (2026-07-17 Post-Adoption)

> Research-only. Cached 710-race archive, expanding-date OOS folds.
> Gate: Good(any-2) ≥ +1.5pp, losses ≤ 0.5pp (Gold/Top1/W-in-T3), Miss non-regression, Top3 stability ≥ 4/5 folds.

## reliability shrinkage λ=0.15 (all fields)

- Baseline:  363 races; 22 Gold / 149 Good-any2 (75 Good-pos) / 320 Pass / 43 Miss; Top3 45.1%; W-in-T3 52.9%; Top1 22.6%
- Candidate: 363 races; 22 Gold / 152 Good-any2 (75 Good-pos) / 320 Pass / 43 Miss; Top3 45.4%; W-in-T3 52.9%; Top1 22.6%
- Good(any-2) lift: **+0.83pp**; Good(positional) lift: +0.00pp; losses (pp): {'gold': 0.0, 'top1': 0.0, 'winner_in_top3': 0.0}; Miss Δ: +0
- Races with a changed Top3: 17 / 363; fold stability: 5/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.15 (12+ fields only)

- Baseline:  363 races; 22 Gold / 149 Good-any2 (75 Good-pos) / 320 Pass / 43 Miss; Top3 45.1%; W-in-T3 52.9%; Top1 22.6%
- Candidate: 363 races; 22 Gold / 150 Good-any2 (75 Good-pos) / 320 Pass / 43 Miss; Top3 45.2%; W-in-T3 52.6%; Top1 22.6%
- Good(any-2) lift: **+0.28pp**; Good(positional) lift: +0.00pp; losses (pp): {'gold': 0.0, 'top1': 0.0, 'winner_in_top3': 0.28}; Miss Δ: +0
- Races with a changed Top3: 12 / 363; fold stability: 5/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.30 (all fields)

- Baseline:  363 races; 22 Gold / 149 Good-any2 (75 Good-pos) / 320 Pass / 43 Miss; Top3 45.1%; W-in-T3 52.9%; Top1 22.6%
- Candidate: 363 races; 22 Gold / 152 Good-any2 (73 Good-pos) / 319 Pass / 44 Miss; Top3 45.3%; W-in-T3 53.2%; Top1 22.3%
- Good(any-2) lift: **+0.83pp**; Good(positional) lift: -0.55pp; losses (pp): {'gold': 0.0, 'top1': 0.28, 'winner_in_top3': -0.28}; Miss Δ: +1
- Races with a changed Top3: 32 / 363; fold stability: 5/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.30 (12+ fields only)

- Baseline:  363 races; 22 Gold / 149 Good-any2 (75 Good-pos) / 320 Pass / 43 Miss; Top3 45.1%; W-in-T3 52.9%; Top1 22.6%
- Candidate: 363 races; 22 Gold / 150 Good-any2 (74 Good-pos) / 320 Pass / 43 Miss; Top3 45.2%; W-in-T3 52.6%; Top1 22.6%
- Good(any-2) lift: **+0.28pp**; Good(positional) lift: -0.28pp; losses (pp): {'gold': 0.0, 'top1': 0.0, 'winner_in_top3': 0.28}; Miss Δ: +0
- Races with a changed Top3: 15 / 363; fold stability: 5/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.50 (all fields)

- Baseline:  363 races; 22 Gold / 149 Good-any2 (75 Good-pos) / 320 Pass / 43 Miss; Top3 45.1%; W-in-T3 52.9%; Top1 22.6%
- Candidate: 363 races; 22 Gold / 153 Good-any2 (72 Good-pos) / 319 Pass / 44 Miss; Top3 45.4%; W-in-T3 53.4%; Top1 22.3%
- Good(any-2) lift: **+1.10pp**; Good(positional) lift: -0.83pp; losses (pp): {'gold': 0.0, 'top1': 0.28, 'winner_in_top3': -0.55}; Miss Δ: +1
- Races with a changed Top3: 52 / 363; fold stability: 5/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.50 (12+ fields only)

- Baseline:  363 races; 22 Gold / 149 Good-any2 (75 Good-pos) / 320 Pass / 43 Miss; Top3 45.1%; W-in-T3 52.9%; Top1 22.6%
- Candidate: 363 races; 22 Gold / 151 Good-any2 (74 Good-pos) / 320 Pass / 43 Miss; Top3 45.3%; W-in-T3 52.9%; Top1 22.6%
- Good(any-2) lift: **+0.55pp**; Good(positional) lift: -0.28pp; losses (pp): {'gold': 0.0, 'top1': 0.0, 'winner_in_top3': 0.0}; Miss Δ: +0
- Races with a changed Top3: 22 / 363; fold stability: 5/5
- Decision: **FAIL / HOLD**

## weights: stability x0.8

- Baseline:  363 races; 22 Gold / 143 Good-any2 (78 Good-pos) / 321 Pass / 42 Miss; Top3 44.6%; W-in-T3 51.8%; Top1 23.4%
- Candidate: 363 races; 21 Gold / 140 Good-any2 (76 Good-pos) / 321 Pass / 42 Miss; Top3 44.3%; W-in-T3 51.2%; Top1 23.1%
- Good(any-2) lift: **-0.83pp**; Good(positional) lift: -0.55pp; losses (pp): {'gold': 0.28, 'top1': 0.28, 'winner_in_top3': 0.55}; Miss Δ: +0
- Races with a changed Top3: 102 / 363; fold stability: 2/5
- Decision: **FAIL / HOLD**

## weights: jockey_trainer x1.2

- Baseline:  363 races; 22 Gold / 143 Good-any2 (78 Good-pos) / 321 Pass / 42 Miss; Top3 44.6%; W-in-T3 51.8%; Top1 23.4%
- Candidate: 363 races; 22 Gold / 144 Good-any2 (78 Good-pos) / 320 Pass / 43 Miss; Top3 44.6%; W-in-T3 52.1%; Top1 23.4%
- Good(any-2) lift: **+0.28pp**; Good(positional) lift: +0.00pp; losses (pp): {'gold': 0.0, 'top1': 0.0, 'winner_in_top3': -0.28}; Miss Δ: +1
- Races with a changed Top3: 35 / 363; fold stability: 3/5
- Decision: **FAIL / HOLD**

## weights: stability x0.8 + jockey_trainer x1.2

- Baseline:  363 races; 22 Gold / 143 Good-any2 (78 Good-pos) / 321 Pass / 42 Miss; Top3 44.6%; W-in-T3 51.8%; Top1 23.4%
- Candidate: 363 races; 22 Gold / 140 Good-any2 (76 Good-pos) / 323 Pass / 40 Miss; Top3 44.5%; W-in-T3 52.1%; Top1 22.9%
- Good(any-2) lift: **-0.83pp**; Good(positional) lift: -0.55pp; losses (pp): {'gold': 0.0, 'top1': 0.55, 'winner_in_top3': -0.28}; Miss Δ: -2
- Races with a changed Top3: 115 / 363; fold stability: 3/5
- Decision: **FAIL / HOLD**

## Summary

**No candidate cleared the promotion gate.** Keep the current model; the Phase-4 evidence (zero-hit winners losing on every matrix dimension) points to missing raw evidence, not mis-weighting — improvement work should target data enrichment (sectionals/trials coverage, venue-specific evidence) rather than global score arithmetic.
