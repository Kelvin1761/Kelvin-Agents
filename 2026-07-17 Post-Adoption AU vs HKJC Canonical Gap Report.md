# AU vs HKJC Wong Choi — Canonical Gap Report (2026-07-17 Post-Adoption)

> Both engines evaluated with `shared_racing/eval_metrics` on stored production
> rankings (`python_auto.ability_score`). Every Good definition reported explicitly.

## Samples

- **AU**: 710 races / 82 meetings, 2025-08-02 → 2026-07-08, engine commit `1b7a203`, sample hash `6e0923e4c354b735`.
- **HKJC**: 243 races / 24 meetings, 2026-04-12 → 2026-07-12, engine commit `1b7a203`, sample hash `3d43e1bae615dbbb`.

## Headline (one ruler)

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AU (full archive) | 710 | 39 (5.5%) | 136 (19.2%) | 290 (40.8%) | 625 (88.0%) | 23.9% | 52.0% | 44.8% | 0.443 |
| HKJC (full archive) | 243 | 9 (3.7%) | 51 (21.0%) | 105 (43.2%) | 198 (81.5%) | 23.5% | 51.9% | 42.8% | 0.427 |
| AU (common window 2026-04-12..2026-07-08) | 339 | 19 (5.6%) | 67 (19.8%) | 138 (40.7%) | 298 (87.9%) | 22.1% | 51.3% | 44.7% | 0.427 |
| HKJC (common window 2026-04-12..2026-07-08) | 232 | 9 (3.9%) | 51 (22.0%) | 100 (43.1%) | 189 (81.5%) | 23.7% | 52.6% | 42.8% | 0.431 |

## Bootstrap 95% confidence intervals

| KPI | AU rate [CI] | HKJC rate [CI] | Gap HKJC−AU [CI] | Gap in common window [CI] |
|---|---|---|---|---|
| good_positional | 19.2% [16.3%, 22.3%] | 21.0% [16.0%, 26.3%] | [-4.2%, 7.7%] | [-4.6%, 9.0%] |
| good_any2 | 40.8% [37.2%, 44.4%] | 43.2% [36.6%, 49.4%] | [-4.8%, 9.2%] | [-5.6%, 10.2%] |
| winner_in_top3 | 52.0% [48.5%, 55.6%] | 51.9% [45.7%, 58.4%] | [-7.3%, 7.3%] | [-7.0%, 9.5%] |
| champion | 23.9% [21.0%, 27.0%] | 23.5% [18.1%, 29.2%] | [-6.5%, 5.8%] | [-5.1%, 8.8%] |

## AU by going family

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AU Good/Firm | 320 | 16 (5.0%) | 60 (18.8%) | 134 (41.9%) | 289 (90.3%) | 27.5% | 53.1% | 45.7% | 0.468 |
| AU Heavy | 116 | 7 (6.0%) | 25 (21.6%) | 48 (41.4%) | 101 (87.1%) | 26.7% | 50.9% | 44.8% | 0.454 |
| AU Soft | 265 | 15 (5.7%) | 49 (18.5%) | 106 (40.0%) | 226 (85.3%) | 18.9% | 50.6% | 43.6% | 0.409 |
| AU Synthetic | 9 | 1 (11.1%) | 2 (22.2%) | 2 (22.2%) | 9 (100.0%) | 11.1% | 66.7% | 44.4% | 0.394 |

## AU by detailed going

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AU Good 4 | 320 | 16 (5.0%) | 60 (18.8%) | 134 (41.9%) | 289 (90.3%) | 27.5% | 53.1% | 45.7% | 0.468 |
| AU Heavy 10 | 14 | 1 (7.1%) | 1 (7.1%) | 7 (50.0%) | 13 (92.9%) | 35.7% | 50.0% | 50.0% | 0.510 |
| AU Heavy 8 | 67 | 4 (6.0%) | 18 (26.9%) | 27 (40.3%) | 58 (86.6%) | 28.4% | 50.7% | 44.3% | 0.476 |
| AU Heavy 9 | 35 | 2 (5.7%) | 6 (17.1%) | 14 (40.0%) | 30 (85.7%) | 20.0% | 51.4% | 43.8% | 0.390 |
| AU Soft | 10 | 1 (10.0%) | 2 (20.0%) | 5 (50.0%) | 9 (90.0%) | 40.0% | 60.0% | 50.0% | 0.578 |
| AU Soft 5 | 95 | 3 (3.2%) | 13 (13.7%) | 36 (37.9%) | 79 (83.2%) | 13.7% | 50.5% | 41.4% | 0.380 |
| AU Soft 6 | 113 | 9 (8.0%) | 25 (22.1%) | 44 (38.9%) | 95 (84.1%) | 19.5% | 48.7% | 43.7% | 0.406 |
| AU Soft 7 | 47 | 2 (4.3%) | 9 (19.1%) | 21 (44.7%) | 43 (91.5%) | 23.4% | 53.2% | 46.8% | 0.439 |
| AU Synthetic 8 | 7 | 1 (14.3%) | 2 (28.6%) | 2 (28.6%) | 7 (100.0%) | 0.0% | 71.4% | 47.6% | 0.327 |
| AU Synthetic None | 2 | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 2 (100.0%) | 50.0% | 50.0% | 33.3% | 0.625 |

Going-adjusted check: HKJC vs **AU Good/Firm only** positional-Good gap 95% CI [-4.3%, 8.9%] (HKJC going is not persisted in Logic files but HKJC turf racing is predominantly Good-ish going; treat as an approximation).

## HKJC by venue

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| HKJC HappyValley | 81 | 5 (6.2%) | 16 (19.8%) | 32 (39.5%) | 66 (81.5%) | 27.2% | 54.3% | 42.4% | 0.456 |
| HKJC ShaTin | 162 | 4 (2.5%) | 35 (21.6%) | 73 (45.1%) | 132 (81.5%) | 21.6% | 50.6% | 43.0% | 0.413 |

## By field size

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AU field 12+ | 250 | 9 (3.6%) | 35 (14.0%) | 75 (30.0%) | 209 (83.6%) | 22.0% | 46.4% | 39.1% | 0.408 |
| AU field 9-11 | 297 | 10 (3.4%) | 50 (16.8%) | 116 (39.1%) | 257 (86.5%) | 22.2% | 49.5% | 43.0% | 0.424 |
| AU field <=8 | 163 | 20 (12.3%) | 51 (31.3%) | 99 (60.7%) | 159 (97.5%) | 30.1% | 65.0% | 56.9% | 0.531 |
| HKJC field 12+ | 215 | 6 (2.8%) | 43 (20.0%) | 93 (43.3%) | 173 (80.5%) | 21.4% | 49.3% | 42.2% | 0.408 |
| HKJC field 9-11 | 21 | 3 (14.3%) | 6 (28.6%) | 9 (42.9%) | 18 (85.7%) | 33.3% | 61.9% | 47.6% | 0.518 |
| HKJC field <=8 | 7 | 0 (0.0%) | 2 (28.6%) | 3 (42.9%) | 7 (100.0%) | 57.1% | 100.0% | 47.6% | 0.762 |

## Reading guide

- **Good (positional)** = model picks 1 and 2 both in the actual top 3 — the definition behind
  both the AU "17.9%" figure and the HKJC calibration doc's 24/91=26.4%.
- **Good (any-2)** = any 2 of the model top 3 in the actual top 3 (cumulative, includes Gold) —
  the AU cached walk-forward's historical `good`.
- Exclusive reflector labels (Gold/Good/Pass/1 Hit/Miss) remain available per race in the JSON output.
