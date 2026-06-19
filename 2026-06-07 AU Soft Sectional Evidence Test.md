# AU Soft Sectional Evidence Test

## Dataset

- Soft validation races: **30**
- Soft runners: **354**
- Runners with prior Soft runs: **114** (32.2%)
- Cache: `/private/tmp/au_wong_choi_ml_cache/au_labelled_horse_rows.csv`

## Evidence Signal

| Signal | Actual Top3 | Others | Lift |
|---|---:|---:|---:|
| Avg Soft sectional quality | 0.759 | 0.473 | +0.286 |
| Avg Soft PI | 2.474 | 1.222 | +1.252 |

## Variant Results

| Variant | Soft Result | Soft Delta | Overall Delta |
|---|---|---|---|
| baseline | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | - | - |
| `pi_only` | 2 Gold / 11 Good / 25 Pass / 14 1H / 5 Miss / Top3 42.2% / W-in-T3 43.3% | Gold +0, Good -1, Pass +1, Miss -1, Top3 +0.0pp, W-in-T3 +0.0pp | Gold +0, Good -1, Pass +1, Miss -1, Top3 +0.0pp, W-in-T3 +0.0pp |
| `quality_only` | 2 Gold / 11 Good / 24 Pass / 13 1H / 6 Miss / Top3 41.1% / W-in-T3 43.3% | Gold +0, Good -1, Pass +0, Miss +0, Top3 -1.1pp, W-in-T3 +0.0pp | Gold +0, Good -1, Pass +0, Miss +0, Top3 -0.2pp, W-in-T3 +0.0pp |
| `quality_pi_blend` | 2 Gold / 11 Good / 24 Pass / 13 1H / 6 Miss / Top3 41.1% / W-in-T3 43.3% | Gold +0, Good -1, Pass +0, Miss +0, Top3 -1.1pp, W-in-T3 +0.0pp | Gold +0, Good -1, Pass +0, Miss +0, Top3 -0.2pp, W-in-T3 +0.0pp |
| `positive_only` | 2 Gold / 11 Good / 24 Pass / 13 1H / 6 Miss / Top3 41.1% / W-in-T3 43.3% | Gold +0, Good -1, Pass +0, Miss +0, Top3 -1.1pp, W-in-T3 +0.0pp | Gold +0, Good -1, Pass +0, Miss +0, Top3 -0.2pp, W-in-T3 +0.0pp |

## Gate

FAILED

- No Soft sectional modifier is clean enough to bake.

## Recommendation

- Keep the baked Soft race-shape modifier as the only live Soft adjustment for now.
- Do not add Soft sectional speed until evidence coverage and out-of-sample lift are stronger.