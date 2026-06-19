# AU Soft Track Simplification Test

## Dataset

- Validation races: **184**
- Conditions: Good/Firm 144, Soft 30, Heavy 10
- Cache: `/private/tmp/au_wong_choi_ml_cache/au_labelled_horse_rows.csv`

## Soft Factor Signal

| Factor | Actual Top3 Avg | Others Avg | Lift | Read |
|---|---:|---:|---:|---|
| `mx_stability` | 72.69 | 70.85 | +1.84 | signal |
| `mx_track` | 65.17 | 64.39 | +0.77 | weak/noisy |
| `mx_race_shape` | 58.78 | 58.44 | +0.33 | weak/noisy |
| `mx_sectional` | 52.24 | 52.43 | -0.19 | weak/noisy |

## Variant Results

| Variant | Soft Result | Soft Delta | Overall Delta |
|---|---|---|---|
| baseline | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | - | - |
| `track_plus` | 3 Gold / 13 Good / 23 Pass / 10 1H / 7 Miss / Top3 43.3% / W-in-T3 46.7% | Gold +1, Good +1, Pass -1, Miss +1, Top3 +1.1pp, W-in-T3 +3.3pp | Gold +1, Good +1, Pass -1, Miss +1, Top3 +0.2pp, W-in-T3 +0.5pp |
| `sectional_plus` | 2 Gold / 14 Good / 23 Pass / 9 1H / 7 Miss / Top3 43.3% / W-in-T3 46.7% | Gold +0, Good +2, Pass -1, Miss +1, Top3 +1.1pp, W-in-T3 +3.3pp | Gold +0, Good +2, Pass -1, Miss +1, Top3 +0.2pp, W-in-T3 +0.5pp |
| `race_shape_plus` | 2 Gold / 12 Good / 25 Pass / 13 1H / 5 Miss / Top3 43.3% / W-in-T3 43.3% | Gold +0, Good +0, Pass +1, Miss -1, Top3 +1.1pp, W-in-T3 +0.0pp | Gold +0, Good +0, Pass +1, Miss -1, Top3 +0.2pp, W-in-T3 +0.0pp |
| `simple_soft_guard` | 2 Gold / 12 Good / 25 Pass / 13 1H / 5 Miss / Top3 43.3% / W-in-T3 43.3% | Gold +0, Good +0, Pass +1, Miss -1, Top3 +1.1pp, W-in-T3 +0.0pp | Gold +0, Good +0, Pass +1, Miss -1, Top3 +0.2pp, W-in-T3 +0.0pp |
| `track_plus_sectional_minus` | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 46.7% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +3.3pp | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.5pp |
| `stability_minus` | 2 Gold / 13 Good / 23 Pass / 10 1H / 7 Miss / Top3 42.2% / W-in-T3 46.7% | Gold +0, Good +1, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +3.3pp | Gold +0, Good +1, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +0.5pp |
| `track_stability_plus` | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |
| `race_shape_minus` | 1 Gold / 13 Good / 24 Pass / 11 1H / 6 Miss / Top3 42.2% / W-in-T3 40.0% | Gold -1, Good +1, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 -3.3pp | Gold -1, Good +1, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 -0.5pp |
| `sectional_minus` | 0 Gold / 11 Good / 25 Pass / 14 1H / 5 Miss / Top3 40.0% / W-in-T3 40.0% | Gold -2, Good -1, Pass +1, Miss -1, Top3 -2.2pp, W-in-T3 -3.3pp | Gold -2, Good -1, Pass +1, Miss -1, Top3 -0.4pp, W-in-T3 -0.5pp |
| `stability_plus` | 1 Gold / 11 Good / 24 Pass / 13 1H / 6 Miss / Top3 40.0% / W-in-T3 40.0% | Gold -1, Good -1, Pass +0, Miss +0, Top3 -2.2pp, W-in-T3 -3.3pp | Gold -1, Good -1, Pass +0, Miss +0, Top3 -0.4pp, W-in-T3 -0.5pp |
| `track_minus` | 0 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 40.0% / W-in-T3 36.7% | Gold -2, Good +0, Pass +0, Miss +0, Top3 -2.2pp, W-in-T3 -6.7pp | Gold -2, Good +0, Pass +0, Miss +0, Top3 -0.4pp, W-in-T3 -1.1pp |
| `stability_plus_shape_minus` | 1 Gold / 10 Good / 24 Pass / 14 1H / 6 Miss / Top3 38.9% / W-in-T3 36.7% | Gold -1, Good -2, Pass +0, Miss +0, Top3 -3.3pp, W-in-T3 -6.7pp | Gold -1, Good -2, Pass +0, Miss +0, Top3 -0.5pp, W-in-T3 -1.1pp |

## Gate

SHADOW PASSED

- Bucket gate passed for `race_shape_plus`, `simple_soft_guard`; keep as shadow candidate before live bake.

## Bucket Gate: race_shape_plus

- Gate: **PASSED**

| Bucket | Base | Candidate | Delta |
|---|---|---|---|
| venue:Randwick | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | 2 Gold / 12 Good / 25 Pass / 13 1H / 5 Miss / Top3 43.3% / W-in-T3 43.3% | Top3 +1.1pp / W-in-T3 +0.0pp / Miss -1 / Pass +1 |
| field:Field 13+ | 1 Gold / 6 Good / 8 Pass / 2 1H / 4 Miss / Top3 41.7% / W-in-T3 41.7% | 1 Gold / 6 Good / 8 Pass / 2 1H / 4 Miss / Top3 41.7% / W-in-T3 41.7% | Top3 +0.0pp / W-in-T3 +0.0pp / Miss +0 / Pass +0 |
| field:Field 9-12 | 1 Gold / 4 Good / 12 Pass / 8 1H / 2 Miss / Top3 40.5% / W-in-T3 42.9% | 1 Gold / 4 Good / 13 Pass / 9 1H / 1 Miss / Top3 42.9% / W-in-T3 42.9% | Top3 +2.4pp / W-in-T3 +0.0pp / Miss -1 / Pass +1 |
| field:Field <=8 | 0 Gold / 2 Good / 4 Pass / 2 1H / 0 Miss / Top3 50.0% / W-in-T3 50.0% | 0 Gold / 2 Good / 4 Pass / 2 1H / 0 Miss / Top3 50.0% / W-in-T3 50.0% | Top3 +0.0pp / W-in-T3 +0.0pp / Miss +0 / Pass +0 |
| date:early | 2 Gold / 8 Good / 17 Pass / 9 1H / 3 Miss / Top3 45.0% / W-in-T3 45.0% | 2 Gold / 8 Good / 17 Pass / 9 1H / 3 Miss / Top3 45.0% / W-in-T3 45.0% | Top3 +0.0pp / W-in-T3 +0.0pp / Miss +0 / Pass +0 |
| date:mid | 0 Gold / 4 Good / 7 Pass / 3 1H / 3 Miss / Top3 36.7% / W-in-T3 40.0% | 0 Gold / 4 Good / 8 Pass / 4 1H / 2 Miss / Top3 40.0% / W-in-T3 40.0% | Top3 +3.3pp / W-in-T3 +0.0pp / Miss -1 / Pass +1 |

## Bucket Gate: simple_soft_guard

- Gate: **PASSED**

| Bucket | Base | Candidate | Delta |
|---|---|---|---|
| venue:Randwick | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | 2 Gold / 12 Good / 25 Pass / 13 1H / 5 Miss / Top3 43.3% / W-in-T3 43.3% | Top3 +1.1pp / W-in-T3 +0.0pp / Miss -1 / Pass +1 |
| field:Field 13+ | 1 Gold / 6 Good / 8 Pass / 2 1H / 4 Miss / Top3 41.7% / W-in-T3 41.7% | 1 Gold / 6 Good / 8 Pass / 2 1H / 4 Miss / Top3 41.7% / W-in-T3 41.7% | Top3 +0.0pp / W-in-T3 +0.0pp / Miss +0 / Pass +0 |
| field:Field 9-12 | 1 Gold / 4 Good / 12 Pass / 8 1H / 2 Miss / Top3 40.5% / W-in-T3 42.9% | 1 Gold / 4 Good / 13 Pass / 9 1H / 1 Miss / Top3 42.9% / W-in-T3 42.9% | Top3 +2.4pp / W-in-T3 +0.0pp / Miss -1 / Pass +1 |
| field:Field <=8 | 0 Gold / 2 Good / 4 Pass / 2 1H / 0 Miss / Top3 50.0% / W-in-T3 50.0% | 0 Gold / 2 Good / 4 Pass / 2 1H / 0 Miss / Top3 50.0% / W-in-T3 50.0% | Top3 +0.0pp / W-in-T3 +0.0pp / Miss +0 / Pass +0 |
| date:early | 2 Gold / 8 Good / 17 Pass / 9 1H / 3 Miss / Top3 45.0% / W-in-T3 45.0% | 2 Gold / 8 Good / 17 Pass / 9 1H / 3 Miss / Top3 45.0% / W-in-T3 45.0% | Top3 +0.0pp / W-in-T3 +0.0pp / Miss +0 / Pass +0 |
| date:mid | 0 Gold / 4 Good / 7 Pass / 3 1H / 3 Miss / Top3 36.7% / W-in-T3 40.0% | 0 Gold / 4 Good / 8 Pass / 4 1H / 2 Miss / Top3 40.0% / W-in-T3 40.0% | Top3 +3.3pp / W-in-T3 +0.0pp / Miss -1 / Pass +1 |

## Recommendation

- Keep live `ability_score` ranking unchanged.
- Do not create an 8D matrix for Soft yet.
- Current simple test treats `race_shape` and `sectional` as possible Soft noise candidates; only promote if repeated walk-forward stays positive.