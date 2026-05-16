# AU Auto Market-Free Ablation

- This test uses archive results for validation only.
- No market odds, SP, favourite rank, market move, or price field is used in candidate scoring.

## Baseline

- Races: **315**
- Gold: **3.8%**
- Good: **16.5%**
- Pass: **35.9%**
- Top3 Place Precision: **41.1%**
- 0-hit / 1-hit / 2-hit / 3-hit: **52 / 150 / 101 / 12**

## Top Candidates

| Rank | Candidate | Gold | Good | Pass | Place | Top3 Win | 0H | 1H | 2H | 3H | Delta |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | jt_fit_tempered+class_weight_class_only+track_pure / place_live | 4.8% | 17.8% | 36.8% | 41.0% | 47.0% | 59 | 140 | 101 | 15 | G +1.0 / Good +1.3 / Pass +1.0 / Place -0.1 / 0H +7 |
| 2 | jt_fit_tempered+class_weight_class_only+track_pure / place_half | 4.8% | 17.8% | 36.8% | 40.8% | 46.7% | 60 | 139 | 101 | 15 | G +1.0 / Good +1.3 / Pass +1.0 / Place -0.2 / 0H +8 |
| 3 | jt_fit_tempered+class_weight_class_only+track_pure / place_off | 4.8% | 17.8% | 36.8% | 40.8% | 46.3% | 60 | 139 | 101 | 15 | G +1.0 / Good +1.3 / Pass +1.0 / Place -0.2 / 0H +8 |
| 4 | class_weight_80_20 / place_live | 3.8% | 16.8% | 36.8% | 41.0% | 47.9% | 56 | 143 | 104 | 12 | G +0.0 / Good +0.3 / Pass +1.0 / Place -0.1 / 0H +4 |
| 5 | class_weight_80_20 / place_half | 3.8% | 16.8% | 36.8% | 40.7% | 47.6% | 58 | 141 | 104 | 12 | G +0.0 / Good +0.3 / Pass +1.0 / Place -0.3 / 0H +6 |
| 6 | class_weight_80_20 / place_off | 3.8% | 16.8% | 36.8% | 40.7% | 47.3% | 58 | 141 | 104 | 12 | G +0.0 / Good +0.3 / Pass +1.0 / Place -0.3 / 0H +6 |
| 7 | race_shape_pure_pace+jt_fit_tempered+track_pure / place_live | 4.8% | 18.1% | 36.5% | 41.3% | 46.3% | 55 | 145 | 100 | 15 | G +1.0 / Good +1.6 / Pass +0.6 / Place +0.2 / 0H +3 |
| 8 | race_shape_pure_pace+jt_fit_tempered+track_pure / place_half | 4.8% | 18.1% | 36.5% | 41.1% | 46.0% | 57 | 143 | 100 | 15 | G +1.0 / Good +1.6 / Pass +0.6 / Place +0.0 / 0H +5 |
| 9 | jt_fit_tempered+class_weight_80_20 / place_live | 4.1% | 18.1% | 36.5% | 41.0% | 47.9% | 56 | 144 | 102 | 13 | G +0.3 / Good +1.6 / Pass +0.6 / Place -0.1 / 0H +4 |
| 10 | jt_fit_tempered+class_weight_80_20 / place_half | 4.1% | 18.1% | 36.5% | 40.8% | 47.6% | 57 | 143 | 102 | 13 | G +0.3 / Good +1.6 / Pass +0.6 / Place -0.2 / 0H +5 |
| 11 | jt_fit_tempered+class_weight_80_20 / place_off | 4.1% | 18.1% | 36.5% | 40.7% | 47.3% | 58 | 142 | 102 | 13 | G +0.3 / Good +1.6 / Pass +0.6 / Place -0.3 / 0H +6 |
| 12 | race_shape_light_track+jt_fit_tempered+class_weight_80_20 / place_live | 4.4% | 17.8% | 36.5% | 41.1% | 47.9% | 56 | 144 | 101 | 14 | G +0.6 / Good +1.3 / Pass +0.6 / Place +0.0 / 0H +4 |
| 13 | race_shape_light_track+jt_fit_tempered+class_weight_80_20 / place_half | 4.4% | 17.8% | 36.5% | 41.0% | 47.6% | 57 | 143 | 101 | 14 | G +0.6 / Good +1.3 / Pass +0.6 / Place -0.1 / 0H +5 |
| 14 | jt_fit_tempered+class_weight_class_only / place_live | 4.8% | 17.5% | 36.5% | 40.8% | 47.0% | 59 | 141 | 100 | 15 | G +1.0 / Good +1.0 / Pass +0.6 / Place -0.2 / 0H +7 |
| 15 | jt_fit_tempered+class_weight_class_only / place_off | 4.8% | 17.5% | 36.5% | 40.8% | 46.3% | 59 | 141 | 100 | 15 | G +1.0 / Good +1.0 / Pass +0.6 / Place -0.2 / 0H +7 |
| 16 | jt_fit_tempered+class_weight_80_20+class_weight_class_only / place_live | 4.8% | 17.5% | 36.5% | 40.8% | 47.0% | 59 | 141 | 100 | 15 | G +1.0 / Good +1.0 / Pass +0.6 / Place -0.2 / 0H +7 |
| 17 | jt_fit_tempered+class_weight_80_20+class_weight_class_only / place_off | 4.8% | 17.5% | 36.5% | 40.8% | 46.3% | 59 | 141 | 100 | 15 | G +1.0 / Good +1.0 / Pass +0.6 / Place -0.2 / 0H +7 |
| 18 | jt_fit_tempered+class_weight_class_only / place_half | 4.8% | 17.5% | 36.5% | 40.7% | 46.7% | 60 | 140 | 100 | 15 | G +1.0 / Good +1.0 / Pass +0.6 / Place -0.3 / 0H +8 |
| 19 | jt_fit_tempered+class_weight_80_20+class_weight_class_only / place_half | 4.8% | 17.5% | 36.5% | 40.7% | 46.7% | 60 | 140 | 100 | 15 | G +1.0 / Good +1.0 / Pass +0.6 / Place -0.3 / 0H +8 |
| 20 | race_shape_light_track+jt_fit_tempered / place_live | 3.8% | 17.1% | 36.5% | 41.1% | 47.0% | 54 | 146 | 103 | 12 | G +0.0 / Good +0.6 / Pass +0.6 / Place +0.0 / 0H +2 |
| 21 | race_shape_pure_pace+race_shape_light_track+jt_fit_tempered / place_live | 3.8% | 17.1% | 36.5% | 41.1% | 47.0% | 54 | 146 | 103 | 12 | G +0.0 / Good +0.6 / Pass +0.6 / Place +0.0 / 0H +2 |
| 22 | race_shape_light_track+jt_fit_tempered / place_half | 3.8% | 17.1% | 36.5% | 41.0% | 47.0% | 55 | 145 | 103 | 12 | G +0.0 / Good +0.6 / Pass +0.6 / Place -0.1 / 0H +3 |
| 23 | race_shape_pure_pace+race_shape_light_track+jt_fit_tempered / place_half | 3.8% | 17.1% | 36.5% | 41.0% | 47.0% | 55 | 145 | 103 | 12 | G +0.0 / Good +0.6 / Pass +0.6 / Place -0.1 / 0H +3 |
| 24 | race_shape_light_track+class_weight_80_20+track_pure / place_live | 4.1% | 16.5% | 36.5% | 41.2% | 47.3% | 54 | 146 | 102 | 13 | G +0.3 / Good +0.0 / Pass +0.6 / Place +0.1 / 0H +2 |
| 25 | race_shape_light_track+class_weight_80_20+track_pure / place_half | 4.1% | 16.5% | 36.5% | 41.0% | 47.0% | 56 | 144 | 102 | 13 | G +0.3 / Good +0.0 / Pass +0.6 / Place -0.1 / 0H +4 |
| 26 | race_shape_light_track+class_weight_80_20+track_pure / place_off | 4.1% | 16.5% | 36.5% | 41.0% | 46.7% | 56 | 144 | 102 | 13 | G +0.3 / Good +0.0 / Pass +0.6 / Place -0.1 / 0H +4 |
| 27 | race_shape_pure_pace+class_weight_80_20+track_pure / place_live | 4.4% | 16.2% | 36.5% | 41.2% | 47.3% | 55 | 145 | 101 | 14 | G +0.6 / Good -0.3 / Pass +0.6 / Place +0.1 / 0H +3 |
| 28 | race_shape_pure_pace+class_weight_80_20+track_pure / place_half | 4.4% | 16.2% | 36.5% | 41.0% | 47.0% | 57 | 143 | 101 | 14 | G +0.6 / Good -0.3 / Pass +0.6 / Place -0.1 / 0H +5 |
| 29 | race_shape_pure_pace+jt_fit_tempered+track_pure / place_off | 4.8% | 18.1% | 36.2% | 41.0% | 45.7% | 57 | 144 | 99 | 15 | G +1.0 / Good +1.6 / Pass +0.3 / Place -0.1 / 0H +5 |
| 30 | sectional_speed_heavy+jt_fit_tempered+class_weight_class_only / place_live | 4.4% | 18.1% | 36.2% | 41.1% | 46.3% | 55 | 146 | 100 | 14 | G +0.6 / Good +1.6 / Pass +0.3 / Place +0.0 / 0H +3 |

## Best Candidate Breakdown

- Candidate: **jt_fit_tempered+class_weight_class_only+track_pure / place_live**

### Field Size

| Field | Races | Gold | Good | Pass | Place | 0H | 1H | 2H | 3H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field <=8 | 53 | 11.3% | 22.6% | 62.3% | 54.7% | 5 | 15 | 27 | 6 |
| Field 9-12 | 181 | 5.0% | 20.4% | 37.6% | 42.7% | 26 | 87 | 59 | 9 |
| Field 13+ | 81 | 0.0% | 8.6% | 18.5% | 28.0% | 28 | 38 | 15 | 0 |

### Race Class

| Class | Races | Gold | Good | Pass | Place | 0H | 1H | 2H | 3H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM58-70 | 124 | 4.8% | 20.2% | 36.3% | 40.9% | 23 | 56 | 39 | 6 |
| BM72-84 | 17 | 5.9% | 11.8% | 35.3% | 41.2% | 3 | 8 | 5 | 1 |
| BM88+ | 5 | 0.0% | 20.0% | 60.0% | 53.3% | 0 | 2 | 3 | 0 |
| Group 1 | 28 | 14.3% | 39.3% | 57.1% | 51.2% | 5 | 7 | 12 | 4 |
| Group 2/3 | 59 | 5.1% | 16.9% | 35.6% | 41.8% | 9 | 29 | 18 | 3 |
| Maiden | 9 | 0.0% | 11.1% | 22.2% | 33.3% | 2 | 5 | 2 | 0 |
| Other | 73 | 1.4% | 8.2% | 31.5% | 36.5% | 17 | 33 | 22 | 1 |

## Promotion Rule

Promote only if overall Pass/Good improves without increasing 0-hit, then re-score archive with the engine and re-run calibration.