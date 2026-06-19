# AU Formline 7D ML Test

Shadow test only. This recomputes archive races with the current engine, so the fixed formline parser is included. It does not change live ranking.

## Guardrails

- Uses only the seven AU matrix scores.
- No odds, flucs, market rank, formguide price movement, or post-7D modifier is used.
- `form_line` is tested as a clean matrix weight, capped during search.
- Seed: `20260612`; iterations per fold: `1200`; formline cap: `10.0%`.

## Data

- Races: **336**
- Validation races: **184**
- Formline coverage: 360/3713 horses with parsed formline rows; avg formline_score 66.6
- Recompute errors: `0`

## Baseline vs Formline Search

- Current static 7D validation: Gold 6 (3.3%) / Good 39 (21.2%) / Pass 72 (39.1%) / 0H 20 / 1H 92 / Top3 43.8% / WTop5 69.6%
- Fold-selected formline validation: Gold 6 (3.3%) / Good 39 (21.2%) / Pass 80 (43.5%) / 0H 22 / 1H 82 / Top3 44.9% / WTop5 68.5%
- Validation delta: Gold +0, Good +0, Pass +8, 0H +2, 1H -10, Top3Places +6, WTop5 -2, Top3 +1.1pp
- Current static 7D full archive: Gold 10 (3.0%) / Good 63 (18.8%) / Pass 133 (39.6%) / 0H 37 / 1H 166 / Top3 43.8% / WTop5 71.7%
- Average searched weights full archive: Gold 13 (3.9%) / Good 64 (19.0%) / Pass 145 (43.2%) / 0H 39 / 1H 152 / Top3 45.1% / WTop5 72.9%
- Full archive delta: Gold +3, Good +1, Pass +12, 0H +2, 1H -14, Top3Places +13, WTop5 +4, Top3 +1.3pp

## Fixed Formline Share Tests

| Formline share | Validation | Validation delta | Full archive delta |
|---:|---|---|---|
| 1.0% | Gold 6 (3.3%) / Good 39 (21.2%) / Pass 72 (39.1%) / 0H 21 / 1H 91 / Top3 43.7% / WTop5 69.6% | Gold +0, Good +0, Pass +0, 0H +1, 1H -1, Top3Places -1, WTop5 +0, Top3 -0.2pp | Gold +0, Good +0, Pass +0, 0H +2, 1H -2, Top3Places -2, WTop5 +0, Top3 -0.2pp |
| 2.0% | Gold 6 (3.3%) / Good 38 (20.7%) / Pass 72 (39.1%) / 0H 21 / 1H 91 / Top3 43.7% / WTop5 69.6% | Gold +0, Good -1, Pass +0, 0H +1, 1H -1, Top3Places -1, WTop5 +0, Top3 -0.2pp | Gold +1, Good -1, Pass +0, 0H +2, 1H -2, Top3Places -1, WTop5 +0, Top3 -0.1pp |
| 4.0% | Gold 6 (3.3%) / Good 38 (20.7%) / Pass 72 (39.1%) / 0H 21 / 1H 91 / Top3 43.7% / WTop5 69.6% | Gold +0, Good -1, Pass +0, 0H +1, 1H -1, Top3Places -1, WTop5 +0, Top3 -0.2pp | Gold +0, Good -1, Pass +0, 0H +3, 1H -3, Top3Places -3, WTop5 +0, Top3 -0.3pp |
| 6.0% | Gold 6 (3.3%) / Good 37 (20.1%) / Pass 71 (38.6%) / 0H 21 / 1H 92 / Top3 43.5% / WTop5 69.0% | Gold +0, Good -2, Pass -1, 0H +1, 1H +0, Top3Places -2, WTop5 -1, Top3 -0.4pp | Gold +0, Good -3, Pass -1, 0H +3, 1H -2, Top3Places -4, WTop5 -3, Top3 -0.4pp |
| 8.0% | Gold 6 (3.3%) / Good 38 (20.7%) / Pass 71 (38.6%) / 0H 22 / 1H 91 / Top3 43.3% / WTop5 69.0% | Gold +0, Good -1, Pass -1, 0H +2, 1H -1, Top3Places -3, WTop5 -1, Top3 -0.5pp | Gold +0, Good -1, Pass -3, 0H +4, 1H -1, Top3Places -7, WTop5 -4, Top3 -0.7pp |
| 10.0% | Gold 6 (3.3%) / Good 38 (20.7%) / Pass 69 (37.5%) / 0H 22 / 1H 93 / Top3 42.9% / WTop5 69.0% | Gold +0, Good -1, Pass -3, 0H +2, 1H +1, Top3Places -5, WTop5 -1, Top3 -0.9pp | Gold +0, Good -1, Pass -6, 0H +4, 1H +2, Top3Places -10, WTop5 -4, Top3 -1.0pp |

## Gate

FAILED

## Current vs Average Searched Weights

| Matrix | Current | Searched avg | Delta |
|---|---:|---:|---:|
| `stability` | 33.0% | 28.3% | -4.7pp |
| `sectional` | 10.5% | 4.2% | -6.3pp |
| `race_shape` | 23.4% | 26.2% | +2.8pp |
| `jockey_trainer` | 21.4% | 24.8% | +3.4pp |
| `class_weight` | 5.0% | 3.9% | -1.1pp |
| `track` | 6.7% | 9.7% | +3.0pp |
| `form_line` | 0.0% | 2.9% | +2.9pp |

## Fold Detail

| Fold | Train | Valid | Validation delta | Weights |
|---:|---:|---:|---|---|
| 1 | 152 | 28 | Gold -1, Good +0, Pass +0, 0H -1, 1H +1, Top3Places +0, WTop5 +0, Top3 +0.0pp | stability 37.8%, sectional 6.0%, race_shape 27.8%, jockey_trainer 24.9%, class_weight 1.9%, track 1.5%, form_line 0.1% |
| 2 | 180 | 30 | Gold +2, Good +1, Pass +2, 0H +0, 1H -2, Top3Places +4, WTop5 +1, Top3 +4.4pp | stability 27.2%, sectional 3.1%, race_shape 26.2%, jockey_trainer 24.1%, class_weight 7.0%, track 12.1%, form_line 0.4% |
| 3 | 210 | 50 | Gold +0, Good +1, Pass +3, 0H +1, 1H -4, Top3Places +2, WTop5 +0, Top3 +1.3pp | stability 24.8%, sectional 4.8%, race_shape 21.9%, jockey_trainer 24.5%, class_weight 4.2%, track 13.4%, form_line 6.3% |
| 4 | 260 | 40 | Gold +0, Good +0, Pass +1, 0H +2, 1H -3, Top3Places -1, WTop5 -2, Top3 -0.8pp | stability 26.0%, sectional 3.4%, race_shape 24.2%, jockey_trainer 24.4%, class_weight 6.5%, track 9.3%, form_line 6.2% |
| 5 | 300 | 36 | Gold -1, Good -2, Pass +2, 0H +0, 1H -2, Top3Places +1, WTop5 -1, Top3 +0.9pp | stability 25.6%, sectional 3.6%, race_shape 30.7%, jockey_trainer 26.1%, class_weight 0.0%, track 12.5%, form_line 1.5% |

## Recommendation

- Do not re-add formline to live ranking yet. Keep the fixed parser for report/watchlist and keep testing on fresh recomputed archives.
