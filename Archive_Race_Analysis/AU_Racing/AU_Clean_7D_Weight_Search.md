# AU Clean 7D Weight Search

Shadow test only. This does not change live weights.

## Guardrails

- Uses only the seven AU matrix scores.
- No odds, flucs, market rank, formguide price movement, or post-7D modifier is used.
- Walk-forward by date: train on earlier races, validate on later races.
- Seed: `20260612`; iterations per fold: `1200`.

## Baseline vs Search

- Current static 7D validation: Gold 5 (2.7%) / Good 40 (21.7%) / Pass 74 (40.2%) / 0H 26 / 1H 84 / Top3 42.9% / WTop5 67.4%
- Fold-selected validation: Gold 7 (3.8%) / Good 43 (23.4%) / Pass 70 (38.0%) / 0H 28 / 1H 86 / Top3 42.2% / WTop5 65.2%
- Validation delta: Gold +2, Good +3, Pass -4, 0H +2, 1H +2, Top3Places -4, WTop5 -4, Top3 -0.7pp
- Current static 7D full archive: Gold 11 (3.3%) / Good 61 (18.2%) / Pass 130 (38.7%) / 0H 43 / 1H 163 / Top3 43.1% / WTop5 70.5%
- Average searched weights full archive: Gold 11 (3.3%) / Good 60 (17.9%) / Pass 132 (39.3%) / 0H 43 / 1H 161 / Top3 43.3% / WTop5 70.2%
- Full archive delta: Gold +0, Good -1, Pass +2, 0H +0, 1H -2, Top3Places +2, WTop5 -1, Top3 +0.2pp

## Gate

FAILED

## Current vs Average Searched Weights

| Matrix | Current | Searched avg | Delta |
|---|---:|---:|---:|
| `stability` | 33.0% | 38.9% | +5.9pp |
| `sectional` | 10.5% | 8.1% | -2.4pp |
| `race_shape` | 23.4% | 24.2% | +0.8pp |
| `jockey_trainer` | 21.4% | 22.3% | +0.9pp |
| `class_weight` | 5.0% | 3.2% | -1.8pp |
| `track` | 6.7% | 3.3% | -3.4pp |
| `form_line` | 0.0% | 0.0% | +0.0pp |

## Fold Detail

| Fold | Train | Valid | Validation delta | Weights |
|---:|---:|---:|---|---|
| 1 | 152 | 28 | Gold +1, Good +2, Pass -1, 0H +0, 1H +1, Top3Places +0, WTop5 +0, Top3 +0.0pp | stability 41.1%, sectional 3.8%, race_shape 24.1%, jockey_trainer 23.1%, class_weight 7.8%, track 0.0%, form_line 0.0% |
| 2 | 180 | 30 | Gold +0, Good -2, Pass -1, 0H +2, 1H -1, Top3Places -3, WTop5 +1, Top3 -3.3pp | stability 45.3%, sectional 7.0%, race_shape 24.8%, jockey_trainer 19.6%, class_weight 0.9%, track 2.3%, form_line 0.2% |
| 3 | 210 | 50 | Gold +1, Good +2, Pass -1, 0H +1, 1H +0, Top3Places -1, WTop5 -2, Top3 -0.7pp | stability 25.8%, sectional 13.3%, race_shape 28.2%, jockey_trainer 18.0%, class_weight 2.7%, track 12.0%, form_line 0.0% |
| 4 | 260 | 40 | Gold +0, Good +1, Pass +0, 0H +0, 1H +0, Top3Places +0, WTop5 -1, Top3 +0.0pp | stability 40.5%, sectional 9.7%, race_shape 19.4%, jockey_trainer 25.9%, class_weight 2.6%, track 1.9%, form_line 0.0% |
| 5 | 300 | 36 | Gold +0, Good +0, Pass -1, 0H -1, 1H +2, Top3Places +0, WTop5 -2, Top3 +0.0pp | stability 41.8%, sectional 6.5%, race_shape 24.4%, jockey_trainer 25.1%, class_weight 1.7%, track 0.4%, form_line 0.0% |

## Recommendation

- Do not change live 7D weights yet. Current clean static weights remain the official ranking baseline.
