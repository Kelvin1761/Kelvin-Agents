# AU Wong Choi Phase-5 Candidate Shadow Tests (2026-07-17)

> Research-only. Cached 710-race archive, expanding-date OOS folds.
> Gate: Good(any-2) ≥ +1.5pp, losses ≤ 0.5pp (Gold/Top1/W-in-T3), Miss non-regression, Top3 stability ≥ 4/5 folds.

## reliability shrinkage λ=0.15 (all fields)

- Baseline:  363 races; 21 Gold / 135 Good-any2 (62 Good-pos) / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6%
- Candidate: 363 races; 21 Gold / 134 Good-any2 (63 Good-pos) / 299 Pass / 64 Miss; Top3 41.7%; W-in-T3 47.4%; Top1 17.4%
- Good(any-2) lift: **-0.28pp**; Good(positional) lift: +0.28pp; losses (pp): {'gold': 0.0, 'top1': 0.28, 'winner_in_top3': -0.28}; Miss Δ: -1
- Races with a changed Top3: 20 / 363; fold stability: 4/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.15 (12+ fields only)

- Baseline:  363 races; 21 Gold / 135 Good-any2 (62 Good-pos) / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6%
- Candidate: 363 races; 21 Gold / 135 Good-any2 (63 Good-pos) / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6%
- Good(any-2) lift: **+0.00pp**; Good(positional) lift: +0.28pp; losses (pp): {'gold': 0.0, 'top1': 0.0, 'winner_in_top3': 0.0}; Miss Δ: +0
- Races with a changed Top3: 10 / 363; fold stability: 5/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.30 (all fields)

- Baseline:  363 races; 21 Gold / 135 Good-any2 (62 Good-pos) / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6%
- Candidate: 363 races; 21 Gold / 135 Good-any2 (63 Good-pos) / 301 Pass / 62 Miss; Top3 42.0%; W-in-T3 47.7%; Top1 17.4%
- Good(any-2) lift: **+0.00pp**; Good(positional) lift: +0.28pp; losses (pp): {'gold': 0.0, 'top1': 0.28, 'winner_in_top3': -0.55}; Miss Δ: -3
- Races with a changed Top3: 36 / 363; fold stability: 5/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.30 (12+ fields only)

- Baseline:  363 races; 21 Gold / 135 Good-any2 (62 Good-pos) / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6%
- Candidate: 363 races; 21 Gold / 135 Good-any2 (62 Good-pos) / 299 Pass / 64 Miss; Top3 41.8%; W-in-T3 47.1%; Top1 17.6%
- Good(any-2) lift: **+0.00pp**; Good(positional) lift: +0.00pp; losses (pp): {'gold': 0.0, 'top1': 0.0, 'winner_in_top3': 0.0}; Miss Δ: -1
- Races with a changed Top3: 14 / 363; fold stability: 5/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.50 (all fields)

- Baseline:  363 races; 21 Gold / 135 Good-any2 (62 Good-pos) / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6%
- Candidate: 363 races; 21 Gold / 134 Good-any2 (63 Good-pos) / 300 Pass / 63 Miss; Top3 41.8%; W-in-T3 47.1%; Top1 17.4%
- Good(any-2) lift: **-0.28pp**; Good(positional) lift: +0.28pp; losses (pp): {'gold': 0.0, 'top1': 0.28, 'winner_in_top3': 0.0}; Miss Δ: -2
- Races with a changed Top3: 60 / 363; fold stability: 4/5
- Decision: **FAIL / HOLD**

## reliability shrinkage λ=0.50 (12+ fields only)

- Baseline:  363 races; 21 Gold / 135 Good-any2 (62 Good-pos) / 298 Pass / 65 Miss; Top3 41.7%; W-in-T3 47.1%; Top1 17.6%
- Candidate: 363 races; 21 Gold / 134 Good-any2 (62 Good-pos) / 299 Pass / 64 Miss; Top3 41.7%; W-in-T3 46.8%; Top1 17.6%
- Good(any-2) lift: **-0.28pp**; Good(positional) lift: +0.00pp; losses (pp): {'gold': 0.0, 'top1': 0.0, 'winner_in_top3': 0.28}; Miss Δ: -1
- Races with a changed Top3: 27 / 363; fold stability: 4/5
- Decision: **FAIL / HOLD**

## weights: stability x0.8

- Baseline:  363 races; 22 Gold / 143 Good-any2 (65 Good-pos) / 309 Pass / 54 Miss; Top3 43.5%; W-in-T3 47.9%; Top1 17.9%
- Candidate: 363 races; 21 Gold / 144 Good-any2 (69 Good-pos) / 303 Pass / 60 Miss; Top3 43.0%; W-in-T3 47.9%; Top1 17.1%
- Good(any-2) lift: **+0.28pp**; Good(positional) lift: +1.10pp; losses (pp): {'gold': 0.28, 'top1': 0.83, 'winner_in_top3': 0.0}; Miss Δ: +6
- Races with a changed Top3: 79 / 363; fold stability: 2/5
- Decision: **FAIL / HOLD**

## weights: jockey_trainer x1.2

- Baseline:  363 races; 22 Gold / 143 Good-any2 (65 Good-pos) / 309 Pass / 54 Miss; Top3 43.5%; W-in-T3 47.9%; Top1 17.9%
- Candidate: 363 races; 22 Gold / 147 Good-any2 (68 Good-pos) / 305 Pass / 58 Miss; Top3 43.5%; W-in-T3 47.1%; Top1 17.4%
- Good(any-2) lift: **+1.10pp**; Good(positional) lift: +0.83pp; losses (pp): {'gold': 0.0, 'top1': 0.55, 'winner_in_top3': 0.83}; Miss Δ: +4
- Races with a changed Top3: 41 / 363; fold stability: 3/5
- Decision: **FAIL / HOLD**

## weights: stability x0.8 + jockey_trainer x1.2

- Baseline:  363 races; 22 Gold / 143 Good-any2 (65 Good-pos) / 309 Pass / 54 Miss; Top3 43.5%; W-in-T3 47.9%; Top1 17.9%
- Candidate: 363 races; 22 Gold / 143 Good-any2 (67 Good-pos) / 304 Pass / 59 Miss; Top3 43.1%; W-in-T3 47.7%; Top1 16.8%
- Good(any-2) lift: **+0.00pp**; Good(positional) lift: +0.55pp; losses (pp): {'gold': 0.0, 'top1': 1.1, 'winner_in_top3': 0.28}; Miss Δ: +5
- Races with a changed Top3: 92 / 363; fold stability: 1/5
- Decision: **FAIL / HOLD**

## Summary

**No candidate cleared the promotion gate.** Keep the current model; the Phase-4 evidence (zero-hit winners losing on every matrix dimension) points to missing raw evidence, not mis-weighting — improvement work should target data enrichment (sectionals/trials coverage, venue-specific evidence) rather than global score arithmetic.
