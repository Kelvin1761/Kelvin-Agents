# AU Class Normalization Shadow Test

- Iterator: same `recomputed` mainline benchmark path as `au_review_auto_weighting.py`.
- Scope: shadow-only rerank deltas; production engine is unchanged.

## Baseline

- Meetings: **44**
- Races: **395**
- Champion: **71 / 395 = 18.0%**
- Good: **68 / 395 = 17.2%**
- Pass: **135 / 395 = 34.2%**
- Order Issue: **149**

## Variants

| Variant | Champion | Gold | Good | Pass | MRR | Order | Avg Top4 Hits | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 71 (18.0%) | 14 | 68 (17.2%) | 135 (34.2%) | 0.3126 | 149 | 1.522 | C +0 / G +0 / Good +0 / Pass +0 / Order +0 |
| class_ladder_soft | 67 (17.0%) | 16 | 56 (14.2%) | 128 (32.4%) | 0.2998 | 153 | 1.486 | C -4 / G +2 / Good -12 / Pass -7 / Order +4 |
| class_venue_soft | 67 (17.0%) | 18 | 53 (13.4%) | 129 (32.7%) | 0.3008 | 148 | 1.491 | C -4 / G +4 / Good -15 / Pass -6 / Order -1 |
| class_venue_weight_soft | 68 (17.2%) | 18 | 53 (13.4%) | 129 (32.7%) | 0.3015 | 146 | 1.489 | C -3 / G +4 / Good -15 / Pass -6 / Order -3 |
| class_venue_weight_med | 70 (17.7%) | 16 | 52 (13.2%) | 131 (33.2%) | 0.3029 | 148 | 1.489 | C -1 / G +2 / Good -16 / Pass -4 / Order -1 |

## Best Shadow Candidate

- Variant: **class_venue_weight_med**
- Champion: **70** (`-1`)
- Good: **52** (`-16`)
- Pass: **131** (`-4`)
- Order Issue: **148** (`-1`)

## Promotion Gate

- Promote only if Pass improves, Good does not drop materially, and Order Issue does not worsen.