# AU Class Depth Shadow Test

- Iterator: same recomputed benchmark path as `au_review_auto_weighting.py`.
- Goal: test constrained prize-depth / venue-depth tie-breaks without touching live scoring.

## Baseline

- Meetings: **44**
- Races: **395**
- Champion: **85 / 395 = 21.5%**
- Good: **78 / 395 = 19.7%**
- Pass: **149 / 395 = 37.7%**
- Order Issue: **153**

## Variants

| Variant | Champion | Gold | Good | Pass | MRR | Order | Avg Top4 Hits | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 85 (21.5%) | 18 | 78 (19.7%) | 149 (37.7%) | 0.3612 | 153 | 1.648 | C +0 / G +0 / Good +0 / Pass +0 / Order +0 |
| prize_positive_soft | 82 (20.8%) | 17 | 68 (17.2%) | 151 (38.2%) | 0.3570 | 151 | 1.658 | C -3 / G -1 / Good -10 / Pass +2 / Order -2 |
| prize_tiebreak_small | 85 (21.5%) | 14 | 68 (17.2%) | 147 (37.2%) | 0.3614 | 159 | 1.673 | C +0 / G -4 / Good -10 / Pass -2 / Order +6 |
| prize_tiebreak_bm_focus | 85 (21.5%) | 15 | 70 (17.7%) | 151 (38.2%) | 0.3635 | 155 | 1.663 | C +0 / G -3 / Good -8 / Pass +2 / Order +2 |
| prize_tiebreak_bm_strict | 85 (21.5%) | 16 | 70 (17.7%) | 151 (38.2%) | 0.3599 | 159 | 1.656 | C +0 / G -2 / Good -8 / Pass +2 / Order +6 |
| prize_rank36_bm_micro | 84 (21.3%) | 17 | 69 (17.5%) | 151 (38.2%) | 0.3561 | 159 | 1.646 | C -1 / G -1 / Good -9 / Pass +2 / Order +6 |
| prize_rank46_bm_micro | 84 (21.3%) | 17 | 75 (19.0%) | 151 (38.2%) | 0.3599 | 152 | 1.653 | C -1 / G -1 / Good -3 / Pass +2 / Order -1 |