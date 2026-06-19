# AU Hidden-Signal Rescue Backtest

Market-free shadow test. Live `rank_score`, `final_rank_score`, and official rankings are unchanged.

## Archive Metrics

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 444 | 23.4% | 18 (4.1%) | 89 (20.0%) | 168 (37.8%) | 49.5% | 68.2% | 42.6% | 63 | 213 | 150 | 18 |
| V1 Formline Merit Rescue | 444 | 23.0% | 18 (4.1%) | 88 (19.8%) | 167 (37.6%) | 49.1% | 68.5% | 42.6% | 62 | 215 | 149 | 18 |
| V2 Trial/JT Comeback Rescue | 444 | 23.0% | 20 (4.5%) | 91 (20.5%) | 171 (38.5%) | 48.9% | 67.8% | 42.9% | 63 | 210 | 151 | 20 |
| V3 Sectional Hardness Relief | 444 | 22.7% | 19 (4.3%) | 75 (16.9%) | 159 (35.8%) | 48.4% | 67.6% | 41.4% | 70 | 215 | 140 | 19 |
| V4 Combined Conservative Overlay | 444 | 22.3% | 19 (4.3%) | 80 (18.0%) | 160 (36.0%) | 48.6% | 68.7% | 42.3% | 60 | 224 | 141 | 19 |

## Archive Delta vs Baseline

| Version | Gold Δ | Good Δ | Pass Δ | 0-hit Δ | 1-hit Δ | Top3 places Δ | Winner Top5 Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1 Formline Merit Rescue | +0 | -1 | -1 | -1 | +2 | +0 | +1 |
| V2 Trial/JT Comeback Rescue | +2 | +2 | +3 | +0 | -3 | +5 | -2 |
| V3 Sectional Hardness Relief | +1 | -14 | -9 | +7 | +2 | -15 | -3 |
| V4 Combined Conservative Overlay | +1 | -9 | -8 | -3 | +11 | -4 | +2 |

## Eagle Farm 2026-06-13 Holdout

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 9 | 22.2% | 0 (0.0%) | 0 (0.0%) | 3 (33.3%) | 66.7% | 77.8% | 33.3% | 3 | 3 | 3 | 0 |
| V1 Formline Merit Rescue | 9 | 22.2% | 0 (0.0%) | 0 (0.0%) | 3 (33.3%) | 66.7% | 66.7% | 33.3% | 3 | 3 | 3 | 0 |
| V2 Trial/JT Comeback Rescue | 9 | 22.2% | 0 (0.0%) | 0 (0.0%) | 1 (11.1%) | 44.4% | 77.8% | 25.9% | 3 | 5 | 1 | 0 |
| V3 Sectional Hardness Relief | 9 | 22.2% | 0 (0.0%) | 0 (0.0%) | 2 (22.2%) | 55.6% | 77.8% | 33.3% | 2 | 5 | 2 | 0 |
| V4 Combined Conservative Overlay | 9 | 22.2% | 0 (0.0%) | 0 (0.0%) | 2 (22.2%) | 55.6% | 77.8% | 29.6% | 3 | 4 | 2 | 0 |

## Eagle Farm Delta vs Baseline

| Version | Gold Δ | Good Δ | Pass Δ | 0-hit Δ | 1-hit Δ | Top3 places Δ | Winner Top5 Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1 Formline Merit Rescue | +0 | +0 | +0 | +0 | +0 | +0 | -1 |
| V2 Trial/JT Comeback Rescue | +0 | +0 | -2 | +0 | +2 | -2 | +0 |
| V3 Sectional Hardness Relief | +0 | +0 | -1 | -1 | +2 | +0 | +0 |
| V4 Combined Conservative Overlay | +0 | +0 | -1 | +0 | +1 | -1 | +0 |

## Promotion Gate

- V4 gate: **FAIL**
- FAIL `archive_pass_not_lower`
- FAIL `archive_top3_places_not_lower`
- PASS `archive_0hit_not_higher`
- PASS `archive_winner_top5_tolerance`
- FAIL `holdout_pass_not_lower`
- FAIL `holdout_top3_places_not_lower`
- PASS `holdout_winner_top5_not_lower`

Recommendation: V4 failed the promotion gate. Keep report-only modifiers disabled and continue shadow research.

## Candidate Quality

| Version | Races With Candidate | Candidates | Candidate Actual Top3 |
|---|---:|---:|---:|
| V1 Formline Merit Rescue | 67 | 86 | 23 (26.7%) |
| V2 Trial/JT Comeback Rescue | 85 | 188 | 62 (33.0%) |
| V3 Sectional Hardness Relief | 342 | 1127 | 286 (25.4%) |
| V4 Combined Conservative Overlay | 385 | 385 | 123 (31.9%) |

Top reasons - V1 Formline Merit Rescue:
- strong_formline_hidden_merit: **64**
- class_rating_support: **16**
- recent_form_not_hard_block: **15**
- balanced_formline_class_confidence: **15**

Top reasons - V2 Trial/JT Comeback Rescue:
- strong_trial_signal: **188**
- jockey_horse_fit_support: **136**
- jt_matrix_support: **132**
- trainer_support: **103**
- jockey_support: **85**
- recent_form_not_hard_block: **64**

Top reasons - V3 Sectional Hardness Relief:
- sectional_low_score_relief: **1127**
- distance_ok: **1021**
- confidence_support: **828**
- jt_support: **790**
- track_support: **700**
- rating_support: **332**
- class_support: **255**
- trial_support: **60**

Top reasons - V4 Combined Conservative Overlay:
- sectional_low_score_relief: **301**
- distance_ok: **278**
- confidence_support: **229**
- jt_support: **229**
- track_support: **211**
- rating_support: **120**
- class_support: **85**
- strong_trial_signal: **56**

## Archive Segment - Condition

### Good/Firm

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 43 | 23.3% | 0 (0.0%) | 4 (9.3%) | 16 (37.2%) | 58.1% | 76.7% | 41.9% | 5 | 22 | 16 | 0 |
| V1 Formline Merit Rescue | 43 | 20.9% | 1 (2.3%) | 4 (9.3%) | 16 (37.2%) | 58.1% | 76.7% | 44.2% | 3 | 24 | 15 | 1 |
| V2 Trial/JT Comeback Rescue | 43 | 23.3% | 2 (4.7%) | 6 (14.0%) | 18 (41.9%) | 53.5% | 76.7% | 44.2% | 6 | 19 | 16 | 2 |
| V3 Sectional Hardness Relief | 43 | 25.6% | 1 (2.3%) | 5 (11.6%) | 15 (34.9%) | 58.1% | 79.1% | 39.5% | 8 | 20 | 14 | 1 |
| V4 Combined Conservative Overlay | 43 | 25.6% | 1 (2.3%) | 5 (11.6%) | 17 (39.5%) | 58.1% | 74.4% | 44.2% | 4 | 22 | 16 | 1 |

### Heavy

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 33 | 24.2% | 1 (3.0%) | 4 (12.1%) | 7 (21.2%) | 45.5% | 66.7% | 34.3% | 7 | 19 | 6 | 1 |
| V1 Formline Merit Rescue | 33 | 21.2% | 1 (3.0%) | 4 (12.1%) | 6 (18.2%) | 42.4% | 66.7% | 31.3% | 9 | 18 | 5 | 1 |
| V2 Trial/JT Comeback Rescue | 33 | 21.2% | 1 (3.0%) | 4 (12.1%) | 8 (24.2%) | 42.4% | 69.7% | 36.4% | 6 | 19 | 7 | 1 |
| V3 Sectional Hardness Relief | 33 | 24.2% | 1 (3.0%) | 4 (12.1%) | 10 (30.3%) | 48.5% | 60.6% | 37.4% | 7 | 16 | 9 | 1 |
| V4 Combined Conservative Overlay | 33 | 21.2% | 1 (3.0%) | 4 (12.1%) | 9 (27.3%) | 42.4% | 69.7% | 36.4% | 7 | 17 | 8 | 1 |

### Other

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 301 | 24.9% | 14 (4.7%) | 70 (23.3%) | 125 (41.5%) | 51.5% | 69.1% | 44.4% | 39 | 137 | 111 | 14 |
| V1 Formline Merit Rescue | 301 | 24.9% | 13 (4.3%) | 69 (22.9%) | 125 (41.5%) | 51.2% | 69.1% | 44.3% | 39 | 137 | 112 | 13 |
| V2 Trial/JT Comeback Rescue | 301 | 24.9% | 14 (4.7%) | 71 (23.6%) | 126 (41.9%) | 51.8% | 69.1% | 44.6% | 38 | 137 | 112 | 14 |
| V3 Sectional Hardness Relief | 301 | 23.6% | 13 (4.3%) | 55 (18.3%) | 113 (37.5%) | 49.2% | 68.8% | 42.6% | 42 | 146 | 100 | 13 |
| V4 Combined Conservative Overlay | 301 | 23.6% | 14 (4.7%) | 61 (20.3%) | 113 (37.5%) | 50.2% | 69.8% | 43.2% | 38 | 150 | 99 | 14 |

### Soft

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 67 | 16.4% | 3 (4.5%) | 11 (16.4%) | 20 (29.9%) | 37.3% | 59.7% | 38.8% | 12 | 35 | 17 | 3 |
| V1 Formline Merit Rescue | 67 | 16.4% | 3 (4.5%) | 11 (16.4%) | 20 (29.9%) | 37.3% | 61.2% | 39.3% | 11 | 36 | 17 | 3 |
| V2 Trial/JT Comeback Rescue | 67 | 14.9% | 3 (4.5%) | 10 (14.9%) | 19 (28.4%) | 35.8% | 55.2% | 37.8% | 13 | 35 | 16 | 3 |
| V3 Sectional Hardness Relief | 67 | 16.4% | 4 (6.0%) | 11 (16.4%) | 21 (31.3%) | 38.8% | 58.2% | 39.3% | 13 | 33 | 17 | 4 |
| V4 Combined Conservative Overlay | 67 | 14.9% | 3 (4.5%) | 10 (14.9%) | 21 (31.3%) | 38.8% | 59.7% | 39.8% | 11 | 35 | 18 | 3 |


## Archive Segment - Class

### BM58-70

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 59 | 20.3% | 1 (1.7%) | 9 (15.3%) | 18 (30.5%) | 49.2% | 66.1% | 40.1% | 7 | 34 | 17 | 1 |
| V1 Formline Merit Rescue | 59 | 20.3% | 1 (1.7%) | 9 (15.3%) | 17 (28.8%) | 47.5% | 67.8% | 39.5% | 7 | 35 | 16 | 1 |
| V2 Trial/JT Comeback Rescue | 59 | 20.3% | 1 (1.7%) | 10 (16.9%) | 17 (28.8%) | 44.1% | 62.7% | 39.0% | 8 | 34 | 16 | 1 |
| V3 Sectional Hardness Relief | 59 | 22.0% | 2 (3.4%) | 10 (16.9%) | 18 (30.5%) | 49.2% | 62.7% | 40.1% | 8 | 33 | 16 | 2 |
| V4 Combined Conservative Overlay | 59 | 22.0% | 1 (1.7%) | 10 (16.9%) | 19 (32.2%) | 49.2% | 69.5% | 40.7% | 7 | 33 | 18 | 1 |

### BM72-84

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 8 | 37.5% | 1 (12.5%) | 2 (25.0%) | 2 (25.0%) | 37.5% | 87.5% | 37.5% | 2 | 4 | 1 | 1 |
| V1 Formline Merit Rescue | 8 | 37.5% | 1 (12.5%) | 2 (25.0%) | 2 (25.0%) | 37.5% | 87.5% | 37.5% | 2 | 4 | 1 | 1 |
| V2 Trial/JT Comeback Rescue | 8 | 37.5% | 1 (12.5%) | 1 (12.5%) | 2 (25.0%) | 37.5% | 87.5% | 37.5% | 2 | 4 | 1 | 1 |
| V3 Sectional Hardness Relief | 8 | 37.5% | 1 (12.5%) | 2 (25.0%) | 2 (25.0%) | 50.0% | 87.5% | 37.5% | 2 | 4 | 1 | 1 |
| V4 Combined Conservative Overlay | 8 | 37.5% | 1 (12.5%) | 1 (12.5%) | 2 (25.0%) | 50.0% | 87.5% | 37.5% | 2 | 4 | 1 | 1 |

### BM88+

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 2 | 0.0% | 0 (0.0%) | 0 (0.0%) | 1 (50.0%) | 50.0% | 50.0% | 50.0% | 0 | 1 | 1 | 0 |
| V1 Formline Merit Rescue | 2 | 0.0% | 0 (0.0%) | 0 (0.0%) | 1 (50.0%) | 50.0% | 50.0% | 50.0% | 0 | 1 | 1 | 0 |
| V2 Trial/JT Comeback Rescue | 2 | 0.0% | 0 (0.0%) | 0 (0.0%) | 1 (50.0%) | 50.0% | 50.0% | 50.0% | 0 | 1 | 1 | 0 |
| V3 Sectional Hardness Relief | 2 | 0.0% | 0 (0.0%) | 0 (0.0%) | 1 (50.0%) | 50.0% | 50.0% | 50.0% | 0 | 1 | 1 | 0 |
| V4 Combined Conservative Overlay | 2 | 0.0% | 0 (0.0%) | 0 (0.0%) | 1 (50.0%) | 50.0% | 50.0% | 50.0% | 0 | 1 | 1 | 0 |

### Group 1

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 6 | 0.0% | 0 (0.0%) | 1 (16.7%) | 1 (16.7%) | 16.7% | 66.7% | 27.8% | 2 | 3 | 1 | 0 |
| V1 Formline Merit Rescue | 6 | 0.0% | 0 (0.0%) | 1 (16.7%) | 1 (16.7%) | 16.7% | 50.0% | 27.8% | 2 | 3 | 1 | 0 |
| V2 Trial/JT Comeback Rescue | 6 | 0.0% | 1 (16.7%) | 1 (16.7%) | 1 (16.7%) | 33.3% | 66.7% | 33.3% | 2 | 3 | 0 | 1 |
| V3 Sectional Hardness Relief | 6 | 0.0% | 0 (0.0%) | 1 (16.7%) | 1 (16.7%) | 16.7% | 66.7% | 27.8% | 2 | 3 | 1 | 0 |
| V4 Combined Conservative Overlay | 6 | 0.0% | 0 (0.0%) | 1 (16.7%) | 1 (16.7%) | 0.0% | 33.3% | 27.8% | 2 | 3 | 1 | 0 |

### Group 2/3

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 16 | 12.5% | 0 (0.0%) | 0 (0.0%) | 3 (18.8%) | 37.5% | 56.2% | 31.2% | 4 | 9 | 3 | 0 |
| V1 Formline Merit Rescue | 16 | 6.2% | 0 (0.0%) | 0 (0.0%) | 3 (18.8%) | 37.5% | 62.5% | 33.3% | 3 | 10 | 3 | 0 |
| V2 Trial/JT Comeback Rescue | 16 | 12.5% | 0 (0.0%) | 0 (0.0%) | 3 (18.8%) | 25.0% | 50.0% | 31.2% | 4 | 9 | 3 | 0 |
| V3 Sectional Hardness Relief | 16 | 12.5% | 0 (0.0%) | 0 (0.0%) | 2 (12.5%) | 31.2% | 62.5% | 25.0% | 6 | 8 | 2 | 0 |
| V4 Combined Conservative Overlay | 16 | 12.5% | 0 (0.0%) | 0 (0.0%) | 4 (25.0%) | 31.2% | 50.0% | 33.3% | 4 | 8 | 4 | 0 |

### Maiden

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 23 | 30.4% | 1 (4.3%) | 3 (13.0%) | 10 (43.5%) | 52.2% | 65.2% | 43.5% | 4 | 9 | 9 | 1 |
| V1 Formline Merit Rescue | 23 | 26.1% | 1 (4.3%) | 3 (13.0%) | 10 (43.5%) | 52.2% | 65.2% | 43.5% | 4 | 9 | 9 | 1 |
| V2 Trial/JT Comeback Rescue | 23 | 21.7% | 1 (4.3%) | 3 (13.0%) | 9 (39.1%) | 47.8% | 69.6% | 42.0% | 4 | 10 | 8 | 1 |
| V3 Sectional Hardness Relief | 23 | 30.4% | 2 (8.7%) | 3 (13.0%) | 11 (47.8%) | 52.2% | 65.2% | 46.4% | 4 | 8 | 9 | 2 |
| V4 Combined Conservative Overlay | 23 | 21.7% | 1 (4.3%) | 3 (13.0%) | 10 (43.5%) | 52.2% | 69.6% | 44.9% | 3 | 10 | 9 | 1 |

### Other

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 330 | 24.2% | 15 (4.5%) | 74 (22.4%) | 133 (40.3%) | 50.9% | 69.1% | 43.8% | 44 | 153 | 118 | 15 |
| V1 Formline Merit Rescue | 330 | 24.2% | 15 (4.5%) | 73 (22.1%) | 133 (40.3%) | 50.6% | 69.1% | 43.8% | 44 | 153 | 118 | 15 |
| V2 Trial/JT Comeback Rescue | 330 | 24.2% | 16 (4.8%) | 76 (23.0%) | 138 (41.8%) | 51.5% | 69.1% | 44.5% | 43 | 149 | 122 | 16 |
| V3 Sectional Hardness Relief | 330 | 23.0% | 14 (4.2%) | 59 (17.9%) | 124 (37.6%) | 49.4% | 68.5% | 42.4% | 48 | 158 | 110 | 14 |
| V4 Combined Conservative Overlay | 330 | 23.0% | 16 (4.8%) | 65 (19.7%) | 123 (37.3%) | 50.0% | 69.7% | 43.1% | 42 | 165 | 107 | 16 |


## Archive Segment - Field Size

### Field 13+

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 108 | 16.7% | 2 (1.9%) | 13 (12.0%) | 33 (30.6%) | 43.5% | 63.9% | 36.7% | 24 | 51 | 31 | 2 |
| V1 Formline Merit Rescue | 108 | 15.7% | 1 (0.9%) | 12 (11.1%) | 33 (30.6%) | 42.6% | 63.9% | 37.0% | 22 | 53 | 32 | 1 |
| V2 Trial/JT Comeback Rescue | 108 | 16.7% | 2 (1.9%) | 14 (13.0%) | 36 (33.3%) | 42.6% | 62.0% | 38.3% | 22 | 50 | 34 | 2 |
| V3 Sectional Hardness Relief | 108 | 18.5% | 3 (2.8%) | 12 (11.1%) | 28 (25.9%) | 38.9% | 60.2% | 34.0% | 29 | 51 | 25 | 3 |
| V4 Combined Conservative Overlay | 108 | 17.6% | 4 (3.7%) | 13 (12.0%) | 31 (28.7%) | 40.7% | 61.1% | 36.4% | 25 | 52 | 27 | 4 |

### Field 9-12

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 252 | 22.6% | 7 (2.8%) | 46 (18.3%) | 86 (34.1%) | 48.4% | 62.7% | 41.3% | 33 | 133 | 79 | 7 |
| V1 Formline Merit Rescue | 252 | 22.2% | 7 (2.8%) | 46 (18.3%) | 85 (33.7%) | 48.0% | 63.1% | 41.0% | 34 | 133 | 78 | 7 |
| V2 Trial/JT Comeback Rescue | 252 | 21.8% | 7 (2.8%) | 46 (18.3%) | 84 (33.3%) | 46.8% | 62.7% | 40.6% | 36 | 132 | 77 | 7 |
| V3 Sectional Hardness Relief | 252 | 21.4% | 6 (2.4%) | 38 (15.1%) | 76 (30.2%) | 47.2% | 63.5% | 39.3% | 37 | 139 | 70 | 6 |
| V4 Combined Conservative Overlay | 252 | 20.6% | 5 (2.0%) | 40 (15.9%) | 75 (29.8%) | 47.2% | 65.1% | 39.9% | 30 | 147 | 70 | 5 |

### Field <=8

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 84 | 34.5% | 9 (10.7%) | 30 (35.7%) | 49 (58.3%) | 60.7% | 90.5% | 54.0% | 6 | 29 | 40 | 9 |
| V1 Formline Merit Rescue | 84 | 34.5% | 10 (11.9%) | 30 (35.7%) | 49 (58.3%) | 60.7% | 90.5% | 54.4% | 6 | 29 | 39 | 10 |
| V2 Trial/JT Comeback Rescue | 84 | 34.5% | 11 (13.1%) | 31 (36.9%) | 51 (60.7%) | 63.1% | 90.5% | 56.0% | 5 | 28 | 40 | 11 |
| V3 Sectional Hardness Relief | 84 | 32.1% | 10 (11.9%) | 25 (29.8%) | 55 (65.5%) | 64.3% | 89.3% | 57.5% | 4 | 25 | 45 | 10 |
| V4 Combined Conservative Overlay | 84 | 33.3% | 10 (11.9%) | 27 (32.1%) | 54 (64.3%) | 63.1% | 89.3% | 56.7% | 5 | 25 | 44 | 10 |


## Archive Changed Examples

### WORSE - V3 Sectional Hardness Relief - 2025-08-02 Flemington Race 1-9 R2
- Context: Other / Other / Field <=8
- Hits: 3 -> 2
- Baseline Top3:
  - #7 Muktamil (rank 1, pos 3, score 67.86)
  - #6 Bold Soul (rank 2, pos 1, score 67.51)
  - #2 Changingoftheguard (rank 3, pos 2, score 65.84)
- Shadow Top3:
  - #7 Muktamil (rank 1, pos 3, score 67.86)
  - #6 Bold Soul (rank 2, pos 1, score 67.51)
  - #8 Samuel Langhorne (rank 5, pos 7, score 66.59, +1.25 v3_sectional_hardness_relief)

### WORSE - V4 Combined Conservative Overlay - 2025-08-02 Flemington Race 1-9 R2
- Context: Other / Other / Field <=8
- Hits: 3 -> 2
- Baseline Top3:
  - #7 Muktamil (rank 1, pos 3, score 67.86)
  - #6 Bold Soul (rank 2, pos 1, score 67.51)
  - #2 Changingoftheguard (rank 3, pos 2, score 65.84)
- Shadow Top3:
  - #7 Muktamil (rank 1, pos 3, score 67.86)
  - #6 Bold Soul (rank 2, pos 1, score 67.51)
  - #8 Samuel Langhorne (rank 5, pos 7, score 66.59, +1.25 v4_combined_conservative)

### WORSE - V3 Sectional Hardness Relief - 2025-08-02 Flemington Race 1-9 R3
- Context: Other / Other / Field 13+
- Hits: 2 -> 1
- Baseline Top3:
  - #6 De Bergerac (rank 1, pos 1, score 69.55)
  - #10 Prevailed (rank 2, pos 4, score 68.72)
  - #2 Capper Thirtynine (rank 3, pos 2, score 68.28)
- Shadow Top3:
  - #6 De Bergerac (rank 1, pos 1, score 69.55)
  - #10 Prevailed (rank 2, pos 4, score 68.72)
  - #15 She's Pretty Rich (rank 4, pos 11, score 68.45, +1.12 v3_sectional_hardness_relief)

### WORSE - V3 Sectional Hardness Relief - 2025-08-02 Flemington Race 1-9 R4
- Context: Other / Other / Field 9-12
- Hits: 2 -> 1
- Baseline Top3:
  - #2 Losesomewinmore (rank 1, pos 1, score 66.34)
  - #8 Smart Little Miss (rank 2, pos 9, score 65.26)
  - #6 Call To Glory (rank 3, pos 2, score 64.50)
- Shadow Top3:
  - #2 Losesomewinmore (rank 1, pos 1, score 66.34)
  - #5 Veloce Carro (rank 4, pos 6, score 65.57, +1.25 v3_sectional_hardness_relief)
  - #10 Commands Success (rank 5, pos 5, score 65.39, +1.12 v3_sectional_hardness_relief)

### WORSE - V4 Combined Conservative Overlay - 2025-08-02 Flemington Race 1-9 R4
- Context: Other / Other / Field 9-12
- Hits: 2 -> 1
- Baseline Top3:
  - #2 Losesomewinmore (rank 1, pos 1, score 66.34)
  - #8 Smart Little Miss (rank 2, pos 9, score 65.26)
  - #6 Call To Glory (rank 3, pos 2, score 64.50)
- Shadow Top3:
  - #2 Losesomewinmore (rank 1, pos 1, score 66.34)
  - #5 Veloce Carro (rank 4, pos 6, score 65.57, +1.25 v4_combined_conservative)
  - #8 Smart Little Miss (rank 2, pos 9, score 65.26)

### WORSE - V3 Sectional Hardness Relief - 2025-08-02 Flemington Race 1-9 R6
- Context: Other / Other / Field 9-12
- Hits: 3 -> 1
- Baseline Top3:
  - #7 Running By (rank 1, pos 2, score 67.23)
  - #8 Zou Sensation (rank 2, pos 1, score 66.87)
  - #6 Fortunate Kiss (rank 3, pos 3, score 66.82)
- Shadow Top3:
  - #9 Green Fly (rank 4, pos 4, score 67.67, +1.25 v3_sectional_hardness_relief)
  - #2 Munhamek (rank 5, pos 8, score 67.52, +1.25 v3_sectional_hardness_relief)
  - #7 Running By (rank 1, pos 2, score 67.23)

### WORSE - V4 Combined Conservative Overlay - 2025-08-02 Flemington Race 1-9 R6
- Context: Other / Other / Field 9-12
- Hits: 3 -> 2
- Baseline Top3:
  - #7 Running By (rank 1, pos 2, score 67.23)
  - #8 Zou Sensation (rank 2, pos 1, score 66.87)
  - #6 Fortunate Kiss (rank 3, pos 3, score 66.82)
- Shadow Top3:
  - #9 Green Fly (rank 4, pos 4, score 67.67, +1.25 v4_combined_conservative)
  - #7 Running By (rank 1, pos 2, score 67.23)
  - #8 Zou Sensation (rank 2, pos 1, score 66.87)

### WORSE - V3 Sectional Hardness Relief - 2025-08-02 Flemington Race 1-9 R8
- Context: Other / Other / Field 13+
- Hits: 2 -> 0
- Baseline Top3:
  - #11 One Long Day (rank 1, pos 10, score 69.93)
  - #3 Hard To Cross (rank 2, pos 3, score 68.21)
  - #15 Too Darn Discreet (rank 3, pos 1, score 67.62)
- Shadow Top3:
  - #11 One Long Day (rank 1, pos 10, score 69.93)
  - #7 Whisky On The Hill (rank 4, pos 8, score 68.72, +1.12 v3_sectional_hardness_relief)
  - #14 He'll Rip (rank 7, pos 11, score 68.39, +1.25 v3_sectional_hardness_relief)

### WORSE - V4 Combined Conservative Overlay - 2025-08-02 Flemington Race 1-9 R8
- Context: Other / Other / Field 13+
- Hits: 2 -> 1
- Baseline Top3:
  - #11 One Long Day (rank 1, pos 10, score 69.93)
  - #3 Hard To Cross (rank 2, pos 3, score 68.21)
  - #15 Too Darn Discreet (rank 3, pos 1, score 67.62)
- Shadow Top3:
  - #11 One Long Day (rank 1, pos 10, score 69.93)
  - #14 He'll Rip (rank 7, pos 11, score 68.39, +1.25 v4_combined_conservative)
  - #3 Hard To Cross (rank 2, pos 3, score 68.21)

### WORSE - V3 Sectional Hardness Relief - 2025-08-23 Randwick Race 1-10 R2
- Context: Other / Other / Field 13+
- Hits: 2 -> 1
- Baseline Top3:
  - #8 Xcessive Force (rank 1, pos 2, score 68.77)
  - #2 Exit Fee (rank 2, pos 6, score 68.47)
  - #5 Neil (rank 3, pos 1, score 68.22)
- Shadow Top3:
  - #8 Xcessive Force (rank 1, pos 2, score 68.77)
  - #4 Calido Magic (rank 4, pos 5, score 68.72, +1.25 v3_sectional_hardness_relief)
  - #2 Exit Fee (rank 2, pos 6, score 68.47)

### WORSE - V4 Combined Conservative Overlay - 2025-08-23 Randwick Race 1-10 R2
- Context: Other / Other / Field 13+
- Hits: 2 -> 1
- Baseline Top3:
  - #8 Xcessive Force (rank 1, pos 2, score 68.77)
  - #2 Exit Fee (rank 2, pos 6, score 68.47)
  - #5 Neil (rank 3, pos 1, score 68.22)
- Shadow Top3:
  - #8 Xcessive Force (rank 1, pos 2, score 68.77)
  - #4 Calido Magic (rank 4, pos 5, score 68.72, +1.25 v4_combined_conservative)
  - #2 Exit Fee (rank 2, pos 6, score 68.47)

### IMPROVED - V3 Sectional Hardness Relief - 2025-08-23 Randwick Race 1-10 R3
- Context: Other / Other / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #5 Bluestone (rank 1, pos 3, score 68.24)
  - #6 Piggyback (rank 2, pos 4, score 68.23)
  - #1 Juja Kibo (rank 3, pos 6, score 66.89)
- Shadow Top3:
  - #5 Bluestone (rank 1, pos 3, score 68.24)
  - #6 Piggyback (rank 2, pos 4, score 68.23)
  - #4 Cormac T (rank 5, pos 2, score 67.66, +1.12 v3_sectional_hardness_relief)

### IMPROVED - V3 Sectional Hardness Relief - 2025-08-23 Randwick Race 1-10 R7
- Context: Other / Other / Field <=8
- Hits: 2 -> 3
- Baseline Top3:
  - #4 Autumn Glow (rank 1, pos 1, score 69.15)
  - #8 Hi Dubai (rank 2, pos 3, score 68.83)
  - #10 Bonita Queen (rank 3, pos 8, score 68.33)
- Shadow Top3:
  - #4 Autumn Glow (rank 1, pos 1, score 69.15)
  - #8 Hi Dubai (rank 2, pos 3, score 68.83)
  - #12 Gangsta Granny (rank 4, pos 2, score 68.62, +1.12 v3_sectional_hardness_relief)

### IMPROVED - V3 Sectional Hardness Relief - 2025-08-23 Randwick Race 1-10 R9
- Context: Other / Other / Field <=8
- Hits: 1 -> 2
- Baseline Top3:
  - #5 General Salute (rank 1, pos 3, score 68.50)
  - #8 Romeo's Choice (rank 2, pos 5, score 68.37)
  - #6 Corniche (rank 3, pos 6, score 67.70)
- Shadow Top3:
  - #12 Just Feelin' Lucky (rank 4, pos 8, score 68.62, +1.12 v3_sectional_hardness_relief)
  - #5 General Salute (rank 1, pos 3, score 68.50)
  - #4 Lazzura (rank 5, pos 1, score 68.42, +1.12 v3_sectional_hardness_relief)

### IMPROVED - V2 Trial/JT Comeback Rescue - 2025-09-06 Randwick Race 1-10 R2
- Context: Good/Firm / Other / Field 13+
- Hits: 1 -> 2
- Baseline Top3:
  - #5 So Magnificent (rank 1, pos 1, score 77.90)
  - #14 Lightning Speed (rank 2, pos 16, score 76.53)
  - #19 Graceful Ellen (rank 3, pos 13, score 76.13)
- Shadow Top3:
  - #5 So Magnificent (rank 1, pos 1, score 77.90)
  - #15 Zumbo (rank 4, pos 2, score 76.87, +1.25 v2_trial_jt_comeback)
  - #16 Poisen Point (rank 5, pos 4, score 76.66, +1.36 v2_trial_jt_comeback)

### IMPROVED - V1 Formline Merit Rescue - 2025-09-06 Randwick Race 1-10 R4
- Context: Good/Firm / Other / Field <=8
- Hits: 2 -> 3
- Baseline Top3:
  - #8 Travolta (rank 1, pos 2, score 69.26)
  - #6 Muktamil (rank 2, pos 3, score 68.13)
  - #5 Tajanis (rank 3, pos 5, score 63.81)
- Shadow Top3:
  - #8 Travolta (rank 1, pos 2, score 69.26)
  - #6 Muktamil (rank 2, pos 3, score 68.13)
  - #1 Changingoftheguard (rank 4, pos 1, score 63.91, +0.63 v1_formline_merit)

### IMPROVED - V2 Trial/JT Comeback Rescue - 2025-09-06 Randwick Race 1-10 R4
- Context: Good/Firm / Other / Field <=8
- Hits: 2 -> 3
- Baseline Top3:
  - #8 Travolta (rank 1, pos 2, score 69.26)
  - #6 Muktamil (rank 2, pos 3, score 68.13)
  - #5 Tajanis (rank 3, pos 5, score 63.81)
- Shadow Top3:
  - #8 Travolta (rank 1, pos 2, score 69.26)
  - #6 Muktamil (rank 2, pos 3, score 68.13)
  - #1 Changingoftheguard (rank 4, pos 1, score 64.33, +1.05 v2_trial_jt_comeback)

### IMPROVED - V4 Combined Conservative Overlay - 2025-09-06 Randwick Race 1-10 R4
- Context: Good/Firm / Other / Field <=8
- Hits: 2 -> 3
- Baseline Top3:
  - #8 Travolta (rank 1, pos 2, score 69.26)
  - #6 Muktamil (rank 2, pos 3, score 68.13)
  - #5 Tajanis (rank 3, pos 5, score 63.81)
- Shadow Top3:
  - #8 Travolta (rank 1, pos 2, score 69.26)
  - #6 Muktamil (rank 2, pos 3, score 68.13)
  - #1 Changingoftheguard (rank 4, pos 1, score 64.33, +1.05 v4_combined_conservative)

### WORSE - V2 Trial/JT Comeback Rescue - 2025-09-06 Randwick Race 1-10 R8
- Context: Good/Firm / Group 2/3 / Field 9-12
- Hits: 2 -> 1
- Baseline Top3:
  - #4 Lady Shenandoah (rank 1, pos 2, score 75.37)
  - #9 In Flight (rank 2, pos 6, score 74.68)
  - #5 Headwall (rank 3, pos 1, score 73.88)
- Shadow Top3:
  - #4 Lady Shenandoah (rank 1, pos 2, score 75.37)
  - #9 In Flight (rank 2, pos 6, score 74.68)
  - #1 Jimmysstar (rank 4, pos 5, score 73.90, +1.46 v2_trial_jt_comeback)

### IMPROVED - V1 Formline Merit Rescue - 2025-09-06 Randwick Race 1-10 R9
- Context: Good/Firm / Group 2/3 / Field 13+
- Hits: 0 -> 1
- Baseline Top3:
  - #17 Depth Of Character (rank 1, pos 12, score 75.75)
  - #6 Kovalica (rank 2, pos 11, score 75.10)
  - #15 Swiftfalcon (rank 3, pos 6, score 72.95)
- Shadow Top3:
  - #17 Depth Of Character (rank 1, pos 12, score 75.75)
  - #6 Kovalica (rank 2, pos 11, score 75.10)
  - #5 Private Eye (rank 4, pos 2, score 73.14, +0.77 v1_formline_merit)


## Eagle Farm Changed Examples

### IMPROVED - V3 Sectional Hardness Relief - 2026-06-13 Eagle Farm Race 1-9 R2
- Context: Heavy / Other / Field 13+
- Hits: 0 -> 1
- Baseline Top3:
  - #4 Bowdene (rank 1, pos 9, score 63.73)
  - #8 Pearl Of Dubai (rank 2, pos 5, score 63.42)
  - #5 Hard To Exceed (rank 3, pos 7, score 62.73)
- Shadow Top3:
  - #4 Bowdene (rank 1, pos 9, score 63.73)
  - #8 Pearl Of Dubai (rank 2, pos 5, score 63.42)
  - #2 Areprice (rank 5, pos 3, score 62.88, +1.25 v3_sectional_hardness_relief)

### WORSE - V2 Trial/JT Comeback Rescue - 2026-06-13 Eagle Farm Race 1-9 R6
- Context: Heavy / Group 2/3 / Field 13+
- Hits: 2 -> 1
- Baseline Top3:
  - #10 Savagery Vibe (rank 1, pos 3, score 68.14)
  - #5 Ahha Ahha (rank 2, pos 14, score 67.74)
  - #8 She's Got Pizzazz (rank 3, pos 1, score 65.80)
- Shadow Top3:
  - #10 Savagery Vibe (rank 1, pos 3, score 68.14)
  - #5 Ahha Ahha (rank 2, pos 14, score 67.74)
  - #13 Poster Girl (rank 4, pos 4, score 66.97, +1.22 v2_trial_jt_comeback)

### WORSE - V3 Sectional Hardness Relief - 2026-06-13 Eagle Farm Race 1-9 R6
- Context: Heavy / Group 2/3 / Field 13+
- Hits: 2 -> 1
- Baseline Top3:
  - #10 Savagery Vibe (rank 1, pos 3, score 68.14)
  - #5 Ahha Ahha (rank 2, pos 14, score 67.74)
  - #8 She's Got Pizzazz (rank 3, pos 1, score 65.80)
- Shadow Top3:
  - #10 Savagery Vibe (rank 1, pos 3, score 68.14)
  - #5 Ahha Ahha (rank 2, pos 14, score 67.74)
  - #13 Poster Girl (rank 4, pos 4, score 66.99, +1.25 v3_sectional_hardness_relief)

### WORSE - V4 Combined Conservative Overlay - 2026-06-13 Eagle Farm Race 1-9 R6
- Context: Heavy / Group 2/3 / Field 13+
- Hits: 2 -> 1
- Baseline Top3:
  - #10 Savagery Vibe (rank 1, pos 3, score 68.14)
  - #5 Ahha Ahha (rank 2, pos 14, score 67.74)
  - #8 She's Got Pizzazz (rank 3, pos 1, score 65.80)
- Shadow Top3:
  - #10 Savagery Vibe (rank 1, pos 3, score 68.14)
  - #5 Ahha Ahha (rank 2, pos 14, score 67.74)
  - #13 Poster Girl (rank 4, pos 4, score 66.99, +1.25 v4_combined_conservative)

### WORSE - V2 Trial/JT Comeback Rescue - 2026-06-13 Eagle Farm Race 1-9 R9
- Context: Heavy / Group 2/3 / Field 9-12
- Hits: 2 -> 1
- Baseline Top3:
  - #4 Asterix (rank 1, pos 6, score 67.52)
  - #5 Militarize (rank 2, pos 3, score 66.37)
  - #7 Royal Supremacy (rank 3, pos 1, score 63.27)
- Shadow Top3:
  - #4 Asterix (rank 1, pos 6, score 67.52)
  - #5 Militarize (rank 2, pos 3, score 66.37)
  - #8 Zambardo (rank 5, pos 7, score 63.40, +1.01 v2_trial_jt_comeback)
