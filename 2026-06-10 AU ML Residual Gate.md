# AU ML Residual Gate

## Dataset

- Races: **336**
- Validation races: **184**
- Horses: **3713**
- Cache: `/private/tmp/au_wong_choi_ml_cache/au_labelled_horse_rows.csv`

## Walk-Forward Result

| Model | Result | Delta |
|---|---|---|
| Current ability baseline | 8 Gold / 72 Good / 161 Pass / 89 1H / 23 Miss / Top3 43.7% / W-in-T3 49.5% | - |
| ML residual overlay | 7 Gold / 75 Good / 159 Pass / 84 1H / 25 Miss / Top3 43.7% / W-in-T3 48.9% | Gold -1, Good +3, Pass -2, Miss +2, Top3 +0.0pp, W-in-T3 -0.5pp |
| Best fixed residual overlay `prob_z_0.35` | 6 Gold / 73 Good / 163 Pass / 90 1H / 21 Miss / Top3 43.8% / W-in-T3 51.1% | Gold -2, Good +1, Pass +2, Miss -2, Top3 +0.2pp, W-in-T3 +1.6pp |

## Selected Overlay By Fold

| Fold | Train | Tune | Validation | Selected overlay | Tune result | Validation result | Validation delta |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 115 | 37 | 28 | `cap_p0.34_c0.95` | 0 Gold / 14 Good / 32 Pass / 18 1H / 5 Miss / Top3 41.4% / W-in-T3 59.5% | 0 Gold / 11 Good / 22 Pass / 11 1H / 6 Miss / Top3 39.3% / W-in-T3 57.1% | Gold -1, Good +3, Pass -1, Miss +1, Top3 +1.2pp, W-in-T3 +0.0pp |
| 2 | 134 | 46 | 30 | `soft_cap_p0.22_c0.45` | 1 Gold / 15 Good / 38 Pass / 23 1H / 8 Miss / Top3 39.1% / W-in-T3 63.0% | 2 Gold / 14 Good / 25 Pass / 11 1H / 5 Miss / Top3 45.6% / W-in-T3 43.3% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |
| 3 | 162 | 48 | 50 | `soft_cap_p0.22_c0.45` | 3 Gold / 21 Good / 40 Pass / 19 1H / 8 Miss / Top3 44.4% / W-in-T3 54.2% | 3 Gold / 23 Good / 46 Pass / 23 1H / 4 Miss / Top3 48.0% / W-in-T3 54.0% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |
| 4 | 180 | 80 | 40 | `soft_cap_p0.22_c0.70` | 6 Gold / 37 Good / 71 Pass / 34 1H / 9 Miss / Top3 47.5% / W-in-T3 50.0% | 2 Gold / 18 Good / 34 Pass / 16 1H / 6 Miss / Top3 45.0% / W-in-T3 52.5% | Gold +0, Good +0, Pass +1, Miss -1, Top3 +0.8pp, W-in-T3 +0.0pp |
| 5 | 200 | 100 | 36 | `cap_p0.34_c0.95` | 7 Gold / 48 Good / 88 Pass / 40 1H / 12 Miss / Top3 47.7% / W-in-T3 51.0% | 0 Gold / 9 Good / 32 Pass / 23 1H / 4 Miss / Top3 38.0% / W-in-T3 36.1% | Gold +0, Good +0, Pass -2, Miss +2, Top3 -1.9pp, W-in-T3 -2.8pp |

## Overlay Frequency

| Overlay | Count |
|---|---:|
| `cap_p0.34_c0.95` | 2 |
| `soft_cap_p0.22_c0.45` | 2 |
| `soft_cap_p0.22_c0.70` | 1 |

## Fixed Overlay Sweep

| Overlay | Result | Delta |
|---|---|---|
| `prob_z_0.35` | 6 Gold / 73 Good / 163 Pass / 90 1H / 21 Miss / Top3 43.8% / W-in-T3 51.1% | Gold -2, Good +1, Pass +2, Miss -2, Top3 +0.2pp, W-in-T3 +1.6pp |
| `soft_cap_p0.22_c0.45` | 8 Gold / 73 Good / 161 Pass / 88 1H / 23 Miss / Top3 43.8% / W-in-T3 50.5% | Gold +0, Good +1, Pass +0, Miss +0, Top3 +0.2pp, W-in-T3 +1.1pp |
| `soft_cap_p0.26_c0.45` | 8 Gold / 73 Good / 161 Pass / 88 1H / 23 Miss / Top3 43.8% / W-in-T3 50.5% | Gold +0, Good +1, Pass +0, Miss +0, Top3 +0.2pp, W-in-T3 +1.1pp |
| `soft_cap_p0.22_c0.70` | 9 Gold / 73 Good / 160 Pass / 87 1H / 24 Miss / Top3 43.8% / W-in-T3 50.0% | Gold +1, Good +1, Pass -1, Miss +1, Top3 +0.2pp, W-in-T3 +0.5pp |
| `soft_cap_p0.26_c0.70` | 9 Gold / 73 Good / 160 Pass / 87 1H / 24 Miss / Top3 43.8% / W-in-T3 50.0% | Gold +1, Good +1, Pass -1, Miss +1, Top3 +0.2pp, W-in-T3 +0.5pp |
| `residual_2.60` | 6 Gold / 72 Good / 163 Pass / 91 1H / 21 Miss / Top3 43.7% / W-in-T3 51.1% | Gold -2, Good +0, Pass +2, Miss -2, Top3 +0.0pp, W-in-T3 +1.6pp |
| `residual_2.00` | 6 Gold / 73 Good / 162 Pass / 89 1H / 22 Miss / Top3 43.7% / W-in-T3 51.1% | Gold -2, Good +1, Pass +1, Miss -1, Top3 +0.0pp, W-in-T3 +1.6pp |
| `soft_cap_p0.22_c0.95` | 9 Gold / 72 Good / 160 Pass / 88 1H / 24 Miss / Top3 43.7% / W-in-T3 50.0% | Gold +1, Good +0, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +0.5pp |
| `soft_cap_p0.22_c1.20` | 9 Gold / 72 Good / 160 Pass / 88 1H / 24 Miss / Top3 43.7% / W-in-T3 50.0% | Gold +1, Good +0, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +0.5pp |
| `soft_cap_p0.26_c0.95` | 9 Gold / 72 Good / 160 Pass / 88 1H / 24 Miss / Top3 43.7% / W-in-T3 50.0% | Gold +1, Good +0, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +0.5pp |
| `soft_cap_p0.26_c1.20` | 9 Gold / 72 Good / 160 Pass / 88 1H / 24 Miss / Top3 43.7% / W-in-T3 50.0% | Gold +1, Good +0, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +0.5pp |
| `soft_cap_p0.30_c0.45` | 6 Gold / 74 Good / 161 Pass / 87 1H / 23 Miss / Top3 43.7% / W-in-T3 49.5% | Gold -2, Good +2, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |

## ML Feature Importance

| Feature | Avg importance |
|---|---:|
| `ability_gap_to_third` | 0.2682 |
| `ability_rank` | 0.1526 |
| `jockey_score` | 0.0932 |
| `rating_score` | 0.0902 |
| `field_count` | 0.0777 |
| `ability_z` | 0.0453 |
| `mx_jockey_trainer` | 0.0392 |
| `mx_race_shape` | 0.0330 |
| `stability_minus_track` | 0.0295 |
| `rank_score` | 0.0257 |
| `mx_class_weight` | 0.0158 |
| `ability_rank_pct` | 0.0154 |
| `ability_score` | 0.0145 |
| `ability_gap_prev` | 0.0138 |
| `ability_gap_next` | 0.0087 |
| `mx_stability` | 0.0077 |

## Condition Buckets

| Bucket | Base | Residual | Delta |
|---|---|---|---|
| Good | 6 Gold / 55 Good / 128 Pass / 73 1H / 16 Miss / Top3 43.8% / W-in-T3 50.0% | 6 Gold / 58 Good / 125 Pass / 67 1H / 19 Miss / Top3 43.8% / W-in-T3 49.3% | Gold +0, Good +3, Pass -3, Miss +3, Top3 +0.0pp, W-in-T3 -0.7pp |
| Heavy | 0 Gold / 5 Good / 9 Pass / 4 1H / 1 Miss / Top3 46.7% / W-in-T3 60.0% | 0 Gold / 5 Good / 9 Pass / 4 1H / 1 Miss / Top3 46.7% / W-in-T3 60.0% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |
| Soft | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | 1 Gold / 12 Good / 25 Pass / 13 1H / 5 Miss / Top3 42.2% / W-in-T3 43.3% | Gold -1, Good +0, Pass +1, Miss -1, Top3 +0.0pp, W-in-T3 +0.0pp |

## Venue Buckets

| Bucket | Base | Residual | Delta |
|---|---|---|---|
| Flemington | 3 Gold / 35 Good / 70 Pass / 35 1H / 6 Miss / Top3 47.4% / W-in-T3 57.9% | 3 Gold / 36 Good / 66 Pass / 30 1H / 10 Miss / Top3 46.1% / W-in-T3 55.3% | Gold +0, Good +1, Pass -4, Miss +4, Top3 -1.3pp, W-in-T3 -2.6pp |
| Randwick | 5 Gold / 37 Good / 91 Pass / 54 1H / 17 Miss / Top3 41.0% / W-in-T3 43.5% | 4 Gold / 39 Good / 93 Pass / 54 1H / 15 Miss / Top3 42.0% / W-in-T3 44.4% | Gold -1, Good +2, Pass +2, Miss -2, Top3 +0.9pp, W-in-T3 +0.9pp |

## Gate

FAILED

- Best fixed overlay is directionally positive, but lift is below the live promotion threshold. Keep it as shadow diagnostics, not live scoring.

## Guardrails

- Residual modifier is capped to +/-1.8 points.
- Overlay parameters are tuned only on earlier dates inside each fold.
- Live promotion requires at least 0.5pp Top3 improvement, no winner-in-top3 loss, and no Miss increase.