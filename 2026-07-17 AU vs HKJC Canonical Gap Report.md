# AU vs HKJC Wong Choi — Canonical Gap Report (2026-07-17)

> Both engines evaluated with `shared_racing/eval_metrics` on stored production
> rankings (`python_auto.ability_score`). Every Good definition reported explicitly.

## Samples

- **AU**: 710 races / 82 meetings, 2025-08-02 → 2026-07-08, engine commit `a8b44a9`, sample hash `6e0923e4c354b735`.
- **HKJC**: 243 races / 24 meetings, 2026-04-12 → 2026-07-12, engine commit `a8b44a9`, sample hash `3d43e1bae615dbbb`.

## Headline (one ruler)

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AU (full archive) | 710 | 31 (4.4%) | 125 (17.6%) | 273 (38.5%) | 602 (84.8%) | 21.0% | 48.7% | 42.5% | 0.413 |
| HKJC (full archive) | 243 | 9 (3.7%) | 51 (21.0%) | 105 (43.2%) | 198 (81.5%) | 23.5% | 51.9% | 42.8% | 0.427 |
| AU (common window 2026-04-12..2026-07-08) | 339 | 16 (4.7%) | 55 (16.2%) | 123 (36.3%) | 275 (81.1%) | 16.8% | 45.1% | 40.7% | 0.377 |
| HKJC (common window 2026-04-12..2026-07-08) | 232 | 9 (3.9%) | 51 (22.0%) | 100 (43.1%) | 189 (81.5%) | 23.7% | 52.6% | 42.8% | 0.431 |

## Bootstrap 95% confidence intervals

| KPI | AU rate [CI] | HKJC rate [CI] | Gap HKJC−AU [CI] | Gap in common window [CI] |
|---|---|---|---|---|
| good_positional | 17.6% [14.9%, 20.4%] | 21.0% [16.0%, 26.3%] | [-2.6%, 9.4%] | [-0.8%, 12.6%] |
| good_any2 | 38.5% [34.9%, 42.1%] | 43.2% [36.6%, 49.4%] | [-2.0%, 11.6%] | [-1.3%, 14.8%] |
| winner_in_top3 | 48.7% [45.4%, 52.4%] | 51.9% [45.7%, 58.4%] | [-4.1%, 10.5%] | [-1.0%, 15.5%] |
| champion | 21.0% [18.2%, 23.9%] | 23.5% [18.1%, 29.2%] | [-3.5%, 8.8%] | [0.1%, 13.8%] |

## AU by going family

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AU Good/Firm | 320 | 14 (4.4%) | 62 (19.4%) | 131 (40.9%) | 292 (91.2%) | 22.5% | 52.8% | 45.5% | 0.434 |
| AU Heavy | 116 | 4 (3.4%) | 19 (16.4%) | 41 (35.3%) | 90 (77.6%) | 23.3% | 50.9% | 38.8% | 0.435 |
| AU Soft | 265 | 12 (4.5%) | 42 (15.8%) | 98 (37.0%) | 213 (80.4%) | 18.1% | 42.6% | 40.6% | 0.377 |
| AU Synthetic | 9 | 1 (11.1%) | 2 (22.2%) | 3 (33.3%) | 7 (77.8%) | 22.2% | 55.6% | 40.7% | 0.442 |

## AU by detailed going

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AU Good 4 | 320 | 14 (4.4%) | 62 (19.4%) | 131 (40.9%) | 292 (91.2%) | 22.5% | 52.8% | 45.5% | 0.434 |
| AU Heavy 10 | 14 | 0 (0.0%) | 5 (35.7%) | 10 (71.4%) | 13 (92.9%) | 35.7% | 57.1% | 54.8% | 0.548 |
| AU Heavy 8 | 67 | 3 (4.5%) | 11 (16.4%) | 23 (34.3%) | 52 (77.6%) | 25.4% | 52.2% | 38.8% | 0.437 |
| AU Heavy 9 | 35 | 1 (2.9%) | 3 (8.6%) | 8 (22.9%) | 25 (71.4%) | 14.3% | 45.7% | 32.4% | 0.385 |
| AU Soft | 10 | 0 (0.0%) | 2 (20.0%) | 3 (30.0%) | 9 (90.0%) | 20.0% | 50.0% | 40.0% | 0.407 |
| AU Soft 5 | 95 | 3 (3.2%) | 16 (16.8%) | 36 (37.9%) | 77 (81.1%) | 17.9% | 45.3% | 40.7% | 0.381 |
| AU Soft 6 | 113 | 6 (5.3%) | 13 (11.5%) | 39 (34.5%) | 89 (78.8%) | 17.7% | 41.6% | 39.5% | 0.372 |
| AU Soft 7 | 47 | 3 (6.4%) | 11 (23.4%) | 20 (42.6%) | 38 (80.9%) | 19.1% | 38.3% | 43.3% | 0.374 |
| AU Synthetic 8 | 7 | 1 (14.3%) | 1 (14.3%) | 2 (28.6%) | 5 (71.4%) | 14.3% | 57.1% | 38.1% | 0.410 |
| AU Synthetic None | 2 | 0 (0.0%) | 1 (50.0%) | 1 (50.0%) | 2 (100.0%) | 50.0% | 50.0% | 50.0% | 0.556 |

Going-adjusted check: HKJC vs **AU Good/Firm only** positional-Good gap 95% CI [-4.9%, 8.2%] (HKJC going is not persisted in Logic files but HKJC turf racing is predominantly Good-ish going; treat as an approximation).

## HKJC by venue

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| HKJC HappyValley | 81 | 5 (6.2%) | 16 (19.8%) | 32 (39.5%) | 66 (81.5%) | 27.2% | 54.3% | 42.4% | 0.456 |
| HKJC ShaTin | 162 | 4 (2.5%) | 35 (21.6%) | 73 (45.1%) | 132 (81.5%) | 21.6% | 50.6% | 43.0% | 0.413 |

## By field size

| Sample | Races | Gold | Good (positional) | Good (any-2) | Pass (any hit) | Top1 win | W-in-Top3 | Top3 prec | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AU field 12+ | 250 | 6 (2.4%) | 27 (10.8%) | 73 (29.2%) | 199 (79.6%) | 18.8% | 42.0% | 37.1% | 0.369 |
| AU field 9-11 | 297 | 7 (2.4%) | 45 (15.2%) | 104 (35.0%) | 252 (84.8%) | 19.2% | 46.8% | 40.7% | 0.402 |
| AU field <=8 | 163 | 18 (11.0%) | 53 (32.5%) | 96 (58.9%) | 151 (92.6%) | 27.6% | 62.6% | 54.2% | 0.499 |
| HKJC field 12+ | 215 | 6 (2.8%) | 43 (20.0%) | 93 (43.3%) | 173 (80.5%) | 21.4% | 49.3% | 42.2% | 0.408 |
| HKJC field 9-11 | 21 | 3 (14.3%) | 6 (28.6%) | 9 (42.9%) | 18 (85.7%) | 33.3% | 61.9% | 47.6% | 0.518 |
| HKJC field <=8 | 7 | 0 (0.0%) | 2 (28.6%) | 3 (42.9%) | 7 (100.0%) | 57.1% | 100.0% | 47.6% | 0.762 |

## Reading guide

- **Good (positional)** = model picks 1 and 2 both in the actual top 3 — the definition behind
  both the AU "17.9%" figure and the HKJC calibration doc's 24/91=26.4%.
- **Good (any-2)** = any 2 of the model top 3 in the actual top 3 (cumulative, includes Gold) —
  the AU cached walk-forward's historical `good`.
- Exclusive reflector labels (Gold/Good/Pass/1 Hit/Miss) remain available per race in the JSON output.
