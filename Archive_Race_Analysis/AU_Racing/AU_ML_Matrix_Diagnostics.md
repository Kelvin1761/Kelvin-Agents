# AU ML Matrix Diagnostics

- Races: `316`
- Meetings: `34`
- Horses: `3482`
- Split: train `221` races / validation `95` races

## Baseline

- Champion: 19.0%
- Winner in Top3: 46.8%
- Gold: 4.1%
- Good: 18.4%
- Pass (Top3 hit >= 2): 35.8%
- Top3 Place Precision: 41.0%
- Zero-hit: 16.8%

## Section Power

| Section | Variant | Pass | Good | Place | Zero-hit |
|---|---|---:|---:|---:|---:|
| jockey_trainer | jockey_score | 31.6% | 15.2% | 38.9% | 18.7% |
| stability | matrix_combo | 31.6% | 14.2% | 38.9% | 19.3% |
| stability | consistency_score | 31.6% | 14.2% | 38.9% | 19.3% |
| jockey_trainer | trainer_score | 29.4% | 12.3% | 35.1% | 26.3% |
| sectional | trial_score | 27.8% | 13.0% | 34.9% | 25.3% |
| stability | form_score | 27.2% | 13.0% | 34.8% | 25.0% |
| track | health_score | 27.2% | 13.0% | 34.8% | 25.0% |
| form_line | form_score | 27.2% | 13.0% | 34.8% | 25.0% |
| race_shape | pace_map_score | 26.9% | 10.4% | 32.6% | 30.1% |
| form_line | matrix_combo | 26.3% | 11.4% | 34.3% | 25.6% |
| form_line | formline_score | 26.3% | 11.4% | 34.3% | 25.6% |
| race_shape | track_score | 24.1% | 10.8% | 33.2% | 25.9% |
| track | matrix_combo | 24.1% | 10.8% | 33.2% | 25.9% |
| track | track_score | 24.1% | 10.8% | 33.2% | 25.9% |
| jockey_trainer | matrix_combo | 23.4% | 12.0% | 33.1% | 26.9% |
| race_shape | matrix_combo | 22.8% | 9.2% | 31.8% | 29.4% |
| sectional | distance_score | 22.8% | 8.2% | 32.1% | 27.5% |
| sectional | sectional_score | 21.8% | 10.4% | 31.2% | 29.4% |
| class_weight | weight_score | 21.2% | 9.8% | 30.7% | 31.0% |
| sectional | matrix_combo | 20.3% | 9.2% | 30.7% | 29.7% |
| jockey_trainer | jockey_horse_fit_score | 19.6% | 7.0% | 29.2% | 32.9% |
| class_weight | class_score | 19.0% | 7.9% | 29.2% | 32.6% |
| class_weight | matrix_combo | 15.2% | 6.3% | 25.6% | 39.2% |

## Weight Search

| Rank | Validation Pass | Validation Good | Validation Place | Validation Zero-hit | Weights |
|---:|---:|---:|---:|---:|---|
| 1 | 45.3% | 23.2% | 46.0% | 14.7% | stability 0.245, sectional 0.166, race_shape 0.130, jockey_trainer 0.013, class_weight 0.236, track 0.016, form_line 0.194 |
| 2 | 45.3% | 21.1% | 46.7% | 12.6% | stability 0.227, sectional 0.062, race_shape 0.176, jockey_trainer 0.028, class_weight 0.258, track 0.016, form_line 0.233 |
| 3 | 45.3% | 20.0% | 46.3% | 12.6% | stability 0.281, sectional 0.031, race_shape 0.149, jockey_trainer 0.013, class_weight 0.226, track 0.019, form_line 0.280 |
| 4 | 44.2% | 21.1% | 47.0% | 10.5% | stability 0.213, sectional 0.057, race_shape 0.173, jockey_trainer 0.017, class_weight 0.258, track 0.065, form_line 0.217 |
| 5 | 44.2% | 20.0% | 46.0% | 12.6% | stability 0.327, sectional 0.342, race_shape 0.163, jockey_trainer 0.030, class_weight 0.057, track 0.022, form_line 0.058 |
| 6 | 43.2% | 27.4% | 46.0% | 10.5% | stability 0.322, sectional 0.038, race_shape 0.211, jockey_trainer 0.099, class_weight 0.179, track 0.039, form_line 0.111 |
| 7 | 43.2% | 25.3% | 46.0% | 10.5% | stability 0.214, sectional 0.071, race_shape 0.321, jockey_trainer 0.027, class_weight 0.100, track 0.035, form_line 0.231 |
| 8 | 43.2% | 23.2% | 45.6% | 11.6% | stability 0.262, sectional 0.047, race_shape 0.120, jockey_trainer 0.045, class_weight 0.148, track 0.144, form_line 0.235 |
| 9 | 43.2% | 22.1% | 45.6% | 11.6% | stability 0.199, sectional 0.102, race_shape 0.192, jockey_trainer 0.031, class_weight 0.162, track 0.065, form_line 0.248 |
| 10 | 43.2% | 21.1% | 46.3% | 8.4% | stability 0.342, sectional 0.023, race_shape 0.221, jockey_trainer 0.059, class_weight 0.221, track 0.107, form_line 0.027 |

## Section Formula Search

| Section | Validation Pass | Validation Good | Validation Place | Validation Zero-hit | Candidate | Live? |
|---|---:|---:|---:|---:|---|---|
| stability | 41.1% | 23.2% | 44.9% | 9.5% | form_score 0.600, consistency_score 0.400 | yes |
| sectional | 41.1% | 25.3% | 44.9% | 9.5% | sectional_score 0.370, distance_score 0.166, trial_score 0.463 | no |
| race_shape | 43.2% | 24.2% | 46.3% | 10.5% | pace_map_score 0.120, track_score 0.880 | no |
| jockey_trainer | 44.2% | 21.1% | 47.4% | 10.5% | jockey_score 0.014, trainer_score 0.529, jockey_horse_fit_score 0.456 | no |
| class_weight | 42.1% | 22.1% | 44.9% | 10.5% | class_score 0.110, weight_score 0.890 | no |
| track | 42.1% | 23.2% | 45.3% | 9.5% | track_score 0.963, health_score 0.037 | no |
| form_line | 41.1% | 23.2% | 44.9% | 9.5% | formline_score 0.780, form_score 0.220 | yes |