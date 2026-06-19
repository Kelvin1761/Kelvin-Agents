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
| ML residual overlay | 7 Gold / 67 Good / 157 Pass / 90 1H / 27 Miss / Top3 41.8% / W-in-T3 45.7% | Gold -1, Good -5, Pass -4, Miss +4, Top3 -1.8pp, W-in-T3 -3.8pp |
| Best fixed residual overlay `soft_cap_p0.22_c0.45` | 8 Gold / 73 Good / 161 Pass / 88 1H / 23 Miss / Top3 43.8% / W-in-T3 50.5% | Gold +0, Good +1, Pass +0, Miss +0, Top3 +0.2pp, W-in-T3 +1.1pp |

## Selected Overlay By Fold

| Fold | Train | Tune | Validation | Selected overlay | Tune result | Validation result | Validation delta |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 115 | 37 | 28 | `prob_z_1.00` | 0 Gold / 15 Good / 32 Pass / 17 1H / 5 Miss / Top3 42.3% / W-in-T3 59.5% | 1 Gold / 7 Good / 22 Pass / 15 1H / 6 Miss / Top3 35.7% / W-in-T3 57.1% | Gold +0, Good -1, Pass -1, Miss +1, Top3 -2.4pp, W-in-T3 +0.0pp |
| 2 | 134 | 46 | 30 | `hybrid_s0.8_p0.34` | 0 Gold / 19 Good / 38 Pass / 19 1H / 8 Miss / Top3 41.3% / W-in-T3 56.5% | 1 Gold / 10 Good / 24 Pass / 14 1H / 6 Miss / Top3 38.9% / W-in-T3 26.7% | Gold -1, Good -4, Pass -1, Miss +1, Top3 -6.7pp, W-in-T3 -16.7pp |
| 3 | 162 | 48 | 50 | `soft_cap_p0.22_c0.45` | 3 Gold / 21 Good / 40 Pass / 19 1H / 8 Miss / Top3 44.4% / W-in-T3 54.2% | 3 Gold / 23 Good / 46 Pass / 23 1H / 4 Miss / Top3 48.0% / W-in-T3 54.0% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |
| 4 | 180 | 80 | 40 | `cap_p0.26_c0.45` | 5 Gold / 38 Good / 71 Pass / 33 1H / 9 Miss / Top3 47.5% / W-in-T3 50.0% | 2 Gold / 18 Good / 33 Pass / 15 1H / 7 Miss / Top3 44.2% / W-in-T3 52.5% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |
| 5 | 200 | 100 | 36 | `cap_p0.34_c0.95` | 7 Gold / 49 Good / 88 Pass / 39 1H / 12 Miss / Top3 48.0% / W-in-T3 52.0% | 0 Gold / 9 Good / 32 Pass / 23 1H / 4 Miss / Top3 38.0% / W-in-T3 33.3% | Gold +0, Good +0, Pass -2, Miss +2, Top3 -1.9pp, W-in-T3 -5.6pp |

## Overlay Frequency

| Overlay | Count |
|---|---:|
| `prob_z_1.00` | 1 |
| `hybrid_s0.8_p0.34` | 1 |
| `soft_cap_p0.22_c0.45` | 1 |
| `cap_p0.26_c0.45` | 1 |
| `cap_p0.34_c0.95` | 1 |

## Fixed Overlay Sweep

| Overlay | Result | Delta |
|---|---|---|
| `soft_cap_p0.22_c0.45` | 8 Gold / 73 Good / 161 Pass / 88 1H / 23 Miss / Top3 43.8% / W-in-T3 50.5% | Gold +0, Good +1, Pass +0, Miss +0, Top3 +0.2pp, W-in-T3 +1.1pp |
| `soft_cap_p0.26_c0.45` | 8 Gold / 73 Good / 161 Pass / 88 1H / 23 Miss / Top3 43.8% / W-in-T3 50.5% | Gold +0, Good +1, Pass +0, Miss +0, Top3 +0.2pp, W-in-T3 +1.1pp |
| `soft_cap_p0.22_c0.70` | 9 Gold / 73 Good / 160 Pass / 87 1H / 24 Miss / Top3 43.8% / W-in-T3 50.0% | Gold +1, Good +1, Pass -1, Miss +1, Top3 +0.2pp, W-in-T3 +0.5pp |
| `soft_cap_p0.26_c0.70` | 9 Gold / 73 Good / 160 Pass / 87 1H / 24 Miss / Top3 43.8% / W-in-T3 50.0% | Gold +1, Good +1, Pass -1, Miss +1, Top3 +0.2pp, W-in-T3 +0.5pp |
| `cap_p0.26_c0.45` | 8 Gold / 73 Good / 161 Pass / 88 1H / 23 Miss / Top3 43.8% / W-in-T3 49.5% | Gold +0, Good +1, Pass +0, Miss +0, Top3 +0.2pp, W-in-T3 +0.0pp |
| `cap_p0.26_c0.70` | 8 Gold / 73 Good / 161 Pass / 88 1H / 23 Miss / Top3 43.8% / W-in-T3 49.5% | Gold +0, Good +1, Pass +0, Miss +0, Top3 +0.2pp, W-in-T3 +0.0pp |
| `cap_p0.26_c0.95` | 8 Gold / 73 Good / 161 Pass / 88 1H / 23 Miss / Top3 43.8% / W-in-T3 49.5% | Gold +0, Good +1, Pass +0, Miss +0, Top3 +0.2pp, W-in-T3 +0.0pp |
| `cap_p0.26_c1.20` | 8 Gold / 73 Good / 161 Pass / 88 1H / 23 Miss / Top3 43.8% / W-in-T3 49.5% | Gold +0, Good +1, Pass +0, Miss +0, Top3 +0.2pp, W-in-T3 +0.0pp |
| `soft_cap_p0.22_c0.95` | 9 Gold / 72 Good / 160 Pass / 88 1H / 24 Miss / Top3 43.7% / W-in-T3 50.0% | Gold +1, Good +0, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +0.5pp |
| `soft_cap_p0.22_c1.20` | 9 Gold / 72 Good / 160 Pass / 88 1H / 24 Miss / Top3 43.7% / W-in-T3 50.0% | Gold +1, Good +0, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +0.5pp |
| `soft_cap_p0.26_c0.95` | 9 Gold / 72 Good / 160 Pass / 88 1H / 24 Miss / Top3 43.7% / W-in-T3 50.0% | Gold +1, Good +0, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +0.5pp |
| `soft_cap_p0.26_c1.20` | 9 Gold / 72 Good / 160 Pass / 88 1H / 24 Miss / Top3 43.7% / W-in-T3 50.0% | Gold +1, Good +0, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +0.5pp |

## ML Feature Importance

| Feature | Avg importance |
|---|---:|
| `ability_gap_to_third` | 0.2718 |
| `ability_rank` | 0.1550 |
| `jockey_score` | 0.0950 |
| `rating_score` | 0.0903 |
| `field_count` | 0.0760 |
| `ability_z` | 0.0483 |
| `mx_jockey_trainer` | 0.0438 |
| `stability_minus_track` | 0.0319 |
| `mx_race_shape` | 0.0307 |
| `ability_score` | 0.0185 |
| `ability_gap_prev` | 0.0166 |
| `ability_rank_pct` | 0.0162 |
| `mx_class_weight` | 0.0151 |
| `wet_jockey_trainer` | 0.0082 |
| `ability_gap_next` | 0.0078 |
| `mx_stability` | 0.0076 |

## Condition Buckets

| Bucket | Base | Residual | Delta |
|---|---|---|---|
| Good | 6 Gold / 55 Good / 128 Pass / 73 1H / 16 Miss / Top3 43.8% / W-in-T3 50.0% | 5 Gold / 51 Good / 124 Pass / 73 1H / 20 Miss / Top3 41.7% / W-in-T3 44.4% | Gold -1, Good -4, Pass -4, Miss +4, Top3 -2.1pp, W-in-T3 -5.6pp |
| Heavy | 0 Gold / 5 Good / 9 Pass / 4 1H / 1 Miss / Top3 46.7% / W-in-T3 60.0% | 0 Gold / 5 Good / 9 Pass / 4 1H / 1 Miss / Top3 46.7% / W-in-T3 60.0% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |
| Soft | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | 2 Gold / 11 Good / 24 Pass / 13 1H / 6 Miss / Top3 41.1% / W-in-T3 46.7% | Gold +0, Good -1, Pass +0, Miss +0, Top3 -1.1pp, W-in-T3 +3.3pp |

## Venue Buckets

| Bucket | Base | Residual | Delta |
|---|---|---|---|
| Flemington | 3 Gold / 35 Good / 70 Pass / 35 1H / 6 Miss / Top3 47.4% / W-in-T3 57.9% | 2 Gold / 33 Good / 64 Pass / 31 1H / 12 Miss / Top3 43.4% / W-in-T3 48.7% | Gold -1, Good -2, Pass -6, Miss +6, Top3 -3.9pp, W-in-T3 -9.2pp |
| Randwick | 5 Gold / 37 Good / 91 Pass / 54 1H / 17 Miss / Top3 41.0% / W-in-T3 43.5% | 5 Gold / 34 Good / 93 Pass / 59 1H / 15 Miss / Top3 40.7% / W-in-T3 43.5% | Gold +0, Good -3, Pass +2, Miss -2, Top3 -0.3pp, W-in-T3 +0.0pp |

## Gate

FAILED

- Best fixed overlay is directionally positive, but lift is below the live promotion threshold. Keep it as shadow diagnostics, not live scoring.

## Guardrails

- Residual modifier is capped to +/-1.8 points.
- Overlay parameters are tuned only on earlier dates inside each fold.
- Live promotion requires at least 0.5pp Top3 improvement, no winner-in-top3 loss, and no Miss increase.