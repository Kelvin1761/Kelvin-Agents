# AU Sector Walk-Forward Gate

## Dataset

- Races: **336**
- Validation races: **184**
- Horses: **3713**
- Cache: `/private/tmp/au_wong_choi_ml_cache/au_labelled_horse_rows.csv`

## Baseline

- Current `ability_score`: 8 Gold / 72 Good / 161 Pass / 89 1H / 23 Miss / Top3 43.7% / W-in-T3 49.5%

## Stage 1: Individual Small Sectors

| Candidate | Result | Delta vs ability | Gate |
|---|---|---|---|
| `consistency_score` | 8 Gold / 64 Good / 156 Pass / 92 1H / 28 Miss / Top3 41.3% / W-in-T3 39.7% | Gold +0, Good -8, Pass -5, Miss +5, Top3 -2.4pp, W-in-T3 -9.8pp | FAILED |
| `jockey_score` | 8 Gold / 55 Good / 155 Pass / 100 1H / 29 Miss / Top3 39.5% / W-in-T3 44.0% | Gold +0, Good -17, Pass -6, Miss +6, Top3 -4.2pp, W-in-T3 -5.4pp | FAILED |
| `rating_score` | 5 Gold / 58 Good / 149 Pass / 91 1H / 35 Miss / Top3 38.4% / W-in-T3 42.9% | Gold -3, Good -14, Pass -12, Miss +12, Top3 -5.3pp, W-in-T3 -6.5pp | FAILED |
| `form_score` | 6 Gold / 60 Good / 145 Pass / 85 1H / 39 Miss / Top3 38.2% / W-in-T3 39.1% | Gold -2, Good -12, Pass -16, Miss +16, Top3 -5.4pp, W-in-T3 -10.3pp | FAILED |
| `health_score` | 6 Gold / 57 Good / 145 Pass / 88 1H / 39 Miss / Top3 37.7% / W-in-T3 37.5% | Gold -2, Good -15, Pass -16, Miss +16, Top3 -6.0pp, W-in-T3 -12.0pp | FAILED |
| `trial_score` | 6 Gold / 60 Good / 143 Pass / 83 1H / 41 Miss / Top3 37.9% / W-in-T3 40.2% | Gold -2, Good -12, Pass -18, Miss +18, Top3 -5.8pp, W-in-T3 -9.2pp | FAILED |
| `trainer_score` | 4 Gold / 58 Good / 143 Pass / 85 1H / 41 Miss / Top3 37.1% / W-in-T3 34.8% | Gold -4, Good -14, Pass -18, Miss +18, Top3 -6.5pp, W-in-T3 -14.7pp | FAILED |
| `track_score` | 3 Gold / 50 Good / 143 Pass / 93 1H / 41 Miss / Top3 35.5% / W-in-T3 39.1% | Gold -5, Good -22, Pass -18, Miss +18, Top3 -8.2pp, W-in-T3 -10.3pp | FAILED |
| `formline_score` | 6 Gold / 54 Good / 141 Pass / 87 1H / 43 Miss / Top3 36.4% / W-in-T3 35.9% | Gold -2, Good -18, Pass -20, Miss +20, Top3 -7.2pp, W-in-T3 -13.6pp | FAILED |
| `distance_score` | 2 Gold / 44 Good / 141 Pass / 97 1H / 43 Miss / Top3 33.9% / W-in-T3 37.0% | Gold -6, Good -28, Pass -20, Miss +20, Top3 -9.8pp, W-in-T3 -12.5pp | FAILED |
| `pace_map_score` | 4 Gold / 49 Good / 139 Pass / 90 1H / 45 Miss / Top3 34.8% / W-in-T3 35.9% | Gold -4, Good -23, Pass -22, Miss +22, Top3 -8.9pp, W-in-T3 -13.6pp | FAILED |
| `class_score` | 3 Gold / 45 Good / 133 Pass / 88 1H / 51 Miss / Top3 32.8% / W-in-T3 33.7% | Gold -5, Good -27, Pass -28, Miss +28, Top3 -10.9pp, W-in-T3 -15.8pp | FAILED |
| `sectional_score` | 2 Gold / 41 Good / 131 Pass / 90 1H / 53 Miss / Top3 31.5% / W-in-T3 31.0% | Gold -6, Good -31, Pass -30, Miss +30, Top3 -12.1pp, W-in-T3 -18.5pp | FAILED |
| `confidence_score` | 3 Gold / 39 Good / 129 Pass / 90 1H / 55 Miss / Top3 31.0% / W-in-T3 33.2% | Gold -5, Good -33, Pass -32, Miss +32, Top3 -12.7pp, W-in-T3 -16.3pp | FAILED |
| `weight_score` | 3 Gold / 46 Good / 128 Pass / 82 1H / 56 Miss / Top3 32.1% / W-in-T3 33.2% | Gold -5, Good -26, Pass -33, Miss +33, Top3 -11.6pp, W-in-T3 -16.3pp | FAILED |
| `jockey_horse_fit_score` | 1 Gold / 39 Good / 128 Pass / 89 1H / 56 Miss / Top3 30.4% / W-in-T3 34.2% | Gold -7, Good -33, Pass -33, Miss +33, Top3 -13.2pp, W-in-T3 -15.2pp | FAILED |

## Stage 2: Individual 7D Matrix Scores

| Candidate | Result | Delta vs ability | Gate |
|---|---|---|---|
| `mx_stability` | 8 Gold / 64 Good / 156 Pass / 92 1H / 28 Miss / Top3 41.3% / W-in-T3 40.2% | Gold +0, Good -8, Pass -5, Miss +5, Top3 -2.4pp, W-in-T3 -9.2pp | FAILED |
| `mx_track` | 3 Gold / 50 Good / 143 Pass / 93 1H / 41 Miss / Top3 35.5% / W-in-T3 39.1% | Gold -5, Good -22, Pass -18, Miss +18, Top3 -8.2pp, W-in-T3 -10.3pp | FAILED |
| `mx_race_shape` | 2 Gold / 45 Good / 143 Pass / 98 1H / 41 Miss / Top3 34.4% / W-in-T3 34.8% | Gold -6, Good -27, Pass -18, Miss +18, Top3 -9.2pp, W-in-T3 -14.7pp | FAILED |
| `mx_form_line` | 6 Gold / 55 Good / 141 Pass / 86 1H / 43 Miss / Top3 36.6% / W-in-T3 36.4% | Gold -2, Good -17, Pass -20, Miss +20, Top3 -7.1pp, W-in-T3 -13.0pp | FAILED |
| `mx_jockey_trainer` | 4 Gold / 55 Good / 137 Pass / 82 1H / 47 Miss / Top3 35.5% / W-in-T3 38.0% | Gold -4, Good -17, Pass -24, Miss +24, Top3 -8.2pp, W-in-T3 -11.4pp | FAILED |
| `mx_sectional` | 2 Gold / 40 Good / 132 Pass / 92 1H / 52 Miss / Top3 31.5% / W-in-T3 28.8% | Gold -6, Good -32, Pass -29, Miss +29, Top3 -12.1pp, W-in-T3 -20.7pp | FAILED |
| `mx_class_weight` | 3 Gold / 51 Good / 129 Pass / 78 1H / 55 Miss / Top3 33.2% / W-in-T3 37.5% | Gold -5, Good -21, Pass -32, Miss +32, Top3 -10.5pp, W-in-T3 -12.0pp | FAILED |

## Stage 3 / 4: Walk-Forward ML Candidates

| Candidate | Result | Delta vs ability | Gate |
|---|---|---|---|
| `stage1_plus_stage2` | 8 Gold / 62 Good / 162 Pass / 100 1H / 22 Miss / Top3 42.0% / W-in-T3 50.5% | Gold +0, Good -10, Pass +1, Miss -1, Top3 -1.6pp, W-in-T3 +1.1pp | FAILED |
| `stage4_base_7d_to_ability_overlay` | 8 Gold / 64 Good / 161 Pass / 97 1H / 23 Miss / Top3 42.2% / W-in-T3 49.5% | Gold +0, Good -8, Pass +0, Miss +0, Top3 -1.4pp, W-in-T3 +0.0pp | FAILED |
| `stage1_all_small_sectors` | 8 Gold / 59 Good / 158 Pass / 99 1H / 26 Miss / Top3 40.8% / W-in-T3 48.4% | Gold +0, Good -13, Pass -3, Miss +3, Top3 -2.9pp, W-in-T3 -1.1pp | FAILED |
| `stage2_all_7d_matrix` | 9 Gold / 66 Good / 150 Pass / 84 1H / 34 Miss / Top3 40.8% / W-in-T3 45.1% | Gold +1, Good -6, Pass -11, Miss +11, Top3 -2.9pp, W-in-T3 -4.3pp | FAILED |

## Fold Detail

| Candidate | Fold | Train | Valid | Result | Delta |
|---|---:|---:|---:|---|---|
| `stage1_plus_stage2` | 1 | 152 | 28 | 0 Gold / 8 Good / 22 Pass / 14 1H / 6 Miss / Top3 35.7% / W-in-T3 46.4% | Gold -1, Good +0, Pass -1, Miss +1, Top3 -2.4pp, W-in-T3 -10.7pp |
| `stage1_plus_stage2` | 2 | 180 | 30 | 3 Gold / 9 Good / 27 Pass / 18 1H / 3 Miss / Top3 43.3% / W-in-T3 43.3% | Gold +1, Good -5, Pass +2, Miss -2, Top3 -2.2pp, W-in-T3 +0.0pp |
| `stage1_plus_stage2` | 3 | 210 | 50 | 3 Gold / 20 Good / 45 Pass / 25 1H / 5 Miss / Top3 45.3% / W-in-T3 56.0% | Gold +0, Good -3, Pass -1, Miss +1, Top3 -2.7pp, W-in-T3 +2.0pp |
| `stage1_plus_stage2` | 4 | 260 | 40 | 1 Gold / 13 Good / 34 Pass / 21 1H / 6 Miss / Top3 40.0% / W-in-T3 50.0% | Gold -1, Good -5, Pass +1, Miss -1, Top3 -4.2pp, W-in-T3 -2.5pp |
| `stage1_plus_stage2` | 5 | 300 | 36 | 1 Gold / 12 Good / 34 Pass / 22 1H / 2 Miss / Top3 43.5% / W-in-T3 52.8% | Gold +1, Good +3, Pass +0, Miss +0, Top3 +3.7pp, W-in-T3 +13.9pp |
| `stage4_base_7d_to_ability_overlay` | 1 | 152 | 28 | 0 Gold / 10 Good / 22 Pass / 12 1H / 6 Miss / Top3 38.1% / W-in-T3 50.0% | Gold -1, Good +2, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 -7.1pp |
| `stage4_base_7d_to_ability_overlay` | 2 | 180 | 30 | 3 Gold / 10 Good / 26 Pass / 16 1H / 4 Miss / Top3 43.3% / W-in-T3 33.3% | Gold +1, Good -4, Pass +1, Miss -1, Top3 -2.2pp, W-in-T3 -10.0pp |
| `stage4_base_7d_to_ability_overlay` | 3 | 210 | 50 | 3 Gold / 19 Good / 45 Pass / 26 1H / 5 Miss / Top3 44.7% / W-in-T3 56.0% | Gold +0, Good -4, Pass -1, Miss +1, Top3 -3.3pp, W-in-T3 +2.0pp |
| `stage4_base_7d_to_ability_overlay` | 4 | 260 | 40 | 1 Gold / 12 Good / 34 Pass / 22 1H / 6 Miss / Top3 39.2% / W-in-T3 52.5% | Gold -1, Good -6, Pass +1, Miss -1, Top3 -5.0pp, W-in-T3 +0.0pp |
| `stage4_base_7d_to_ability_overlay` | 5 | 300 | 36 | 1 Gold / 13 Good / 34 Pass / 21 1H / 2 Miss / Top3 44.4% / W-in-T3 50.0% | Gold +1, Good +4, Pass +0, Miss +0, Top3 +4.6pp, W-in-T3 +11.1pp |
| `stage1_all_small_sectors` | 1 | 152 | 28 | 0 Gold / 9 Good / 21 Pass / 12 1H / 7 Miss / Top3 35.7% / W-in-T3 46.4% | Gold -1, Good +1, Pass -2, Miss +2, Top3 -2.4pp, W-in-T3 -10.7pp |
| `stage1_all_small_sectors` | 2 | 180 | 30 | 2 Gold / 9 Good / 25 Pass / 16 1H / 5 Miss / Top3 40.0% / W-in-T3 40.0% | Gold +0, Good -5, Pass +0, Miss +0, Top3 -5.6pp, W-in-T3 -3.3pp |
| `stage1_all_small_sectors` | 3 | 210 | 50 | 4 Gold / 18 Good / 44 Pass / 26 1H / 6 Miss / Top3 44.0% / W-in-T3 54.0% | Gold +1, Good -5, Pass -2, Miss +2, Top3 -4.0pp, W-in-T3 +0.0pp |
| `stage1_all_small_sectors` | 4 | 260 | 40 | 1 Gold / 12 Good / 36 Pass / 24 1H / 4 Miss / Top3 40.8% / W-in-T3 50.0% | Gold -1, Good -6, Pass +3, Miss -3, Top3 -3.3pp, W-in-T3 -2.5pp |
| `stage1_all_small_sectors` | 5 | 300 | 36 | 1 Gold / 11 Good / 32 Pass / 21 1H / 4 Miss / Top3 40.7% / W-in-T3 47.2% | Gold +1, Good +2, Pass -2, Miss +2, Top3 +0.9pp, W-in-T3 +8.3pp |
| `stage2_all_7d_matrix` | 1 | 152 | 28 | 1 Gold / 9 Good / 22 Pass / 13 1H / 6 Miss / Top3 38.1% / W-in-T3 32.1% | Gold +0, Good +1, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 -25.0pp |
| `stage2_all_7d_matrix` | 2 | 180 | 30 | 2 Gold / 9 Good / 25 Pass / 16 1H / 5 Miss / Top3 40.0% / W-in-T3 33.3% | Gold +0, Good -5, Pass +0, Miss +0, Top3 -5.6pp, W-in-T3 -10.0pp |
| `stage2_all_7d_matrix` | 3 | 210 | 50 | 3 Gold / 20 Good / 46 Pass / 26 1H / 4 Miss / Top3 46.0% / W-in-T3 56.0% | Gold +0, Good -3, Pass +0, Miss +0, Top3 -2.0pp, W-in-T3 +2.0pp |
| `stage2_all_7d_matrix` | 4 | 260 | 40 | 1 Gold / 15 Good / 28 Pass / 13 1H / 12 Miss / Top3 36.7% / W-in-T3 45.0% | Gold -1, Good -3, Pass -5, Miss +5, Top3 -7.5pp, W-in-T3 -7.5pp |
| `stage2_all_7d_matrix` | 5 | 300 | 36 | 2 Gold / 13 Good / 29 Pass / 16 1H / 7 Miss / Top3 40.7% / W-in-T3 50.0% | Gold +2, Good +4, Pass -5, Miss +5, Top3 +0.9pp, W-in-T3 +11.1pp |

## Promotion Gate

FAILED

- No sector or ML candidate beat the current `ability_score` with flat/lower Miss and no winner-in-top3 loss.
- Live AU scoring weights should remain unchanged.