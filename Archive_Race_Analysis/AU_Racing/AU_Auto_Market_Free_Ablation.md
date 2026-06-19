# AU Auto Market-Free Ablation

- This test uses archive results for validation only.
- No market odds, SP, favourite rank, market move, or price field is used in candidate scoring.

## Baseline

- Races: **316**
- Gold: **4.1%**
- Good: **20.9%**
- Pass: **38.9%**
- Top3 Place Precision: **42.6%**
- 0-hit / 1-hit / 2-hit / 3-hit: **48 / 145 / 110 / 13**

## Top Candidates

| Rank | Candidate | Gold | Good | Pass | Place | Top3 Win | 0H | 1H | 2H | 3H | Delta |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | formline_purer / place_live | 4.1% | 20.9% | 38.9% | 42.6% | 50.3% | 48 | 145 | 110 | 13 | G +0.0 / Good +0.0 / Pass +0.0 / Place +0.0 / 0H +0 |
| 2 | sectional_speed_heavy / place_live | 4.1% | 20.9% | 38.6% | 42.5% | 50.0% | 48 | 146 | 109 | 13 | G +0.0 / Good +0.0 / Pass -0.3 / Place -0.1 / 0H +0 |
| 3 | sectional_speed_heavy+formline_purer / place_live | 4.1% | 20.9% | 38.6% | 42.5% | 50.0% | 48 | 146 | 109 | 13 | G +0.0 / Good +0.0 / Pass -0.3 / Place -0.1 / 0H +0 |
| 4 | class_weight_heavy_rating / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 5 | class_weight_heavy_rating+formline_purer / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 6 | class_weight_80_20+class_weight_heavy_rating / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 7 | class_weight_no_rating+class_weight_heavy_rating / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 8 | class_weight_class_only+class_weight_heavy_rating / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 9 | class_weight_80_20+class_weight_heavy_rating+formline_purer / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 10 | class_weight_no_rating+class_weight_heavy_rating+formline_purer / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 11 | class_weight_class_only+class_weight_heavy_rating+formline_purer / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 12 | class_weight_80_20+class_weight_no_rating+class_weight_heavy_rating / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 13 | class_weight_80_20+class_weight_class_only+class_weight_heavy_rating / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 14 | class_weight_class_only+class_weight_no_rating+class_weight_heavy_rating / place_live | 4.7% | 20.6% | 38.6% | 42.8% | 50.6% | 47 | 147 | 107 | 15 | G +0.6 / Good -0.3 / Pass -0.3 / Place +0.2 / 0H -1 |
| 15 | class_weight_heavy_rating / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 16 | class_weight_heavy_rating+formline_purer / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 17 | class_weight_80_20+class_weight_heavy_rating / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 18 | sectional_speed_heavy+class_weight_heavy_rating / place_live | 4.4% | 20.6% | 38.6% | 42.7% | 50.9% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 19 | class_weight_no_rating+class_weight_heavy_rating / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 20 | class_weight_class_only+class_weight_heavy_rating / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 21 | class_weight_80_20+class_weight_heavy_rating+formline_purer / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 22 | sectional_speed_heavy+class_weight_heavy_rating+formline_purer / place_live | 4.4% | 20.6% | 38.6% | 42.7% | 50.9% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 23 | class_weight_no_rating+class_weight_heavy_rating+formline_purer / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 24 | class_weight_class_only+class_weight_heavy_rating+formline_purer / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 25 | sectional_speed_heavy+class_weight_80_20+class_weight_heavy_rating / place_live | 4.4% | 20.6% | 38.6% | 42.7% | 50.9% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 26 | class_weight_80_20+class_weight_no_rating+class_weight_heavy_rating / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 27 | class_weight_80_20+class_weight_class_only+class_weight_heavy_rating / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 28 | sectional_speed_heavy+class_weight_no_rating+class_weight_heavy_rating / place_live | 4.4% | 20.6% | 38.6% | 42.7% | 50.9% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 29 | sectional_speed_heavy+class_weight_class_only+class_weight_heavy_rating / place_live | 4.4% | 20.6% | 38.6% | 42.7% | 50.9% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |
| 30 | class_weight_class_only+class_weight_no_rating+class_weight_heavy_rating / place_half | 4.4% | 20.6% | 38.6% | 42.7% | 50.6% | 47 | 147 | 108 | 14 | G +0.3 / Good -0.3 / Pass -0.3 / Place +0.1 / 0H -1 |

## Best Candidate Breakdown

- Candidate: **formline_purer / place_live**

### Field Size

| Field | Races | Gold | Good | Pass | Place | 0H | 1H | 2H | 3H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field <=8 | 52 | 11.5% | 38.5% | 61.5% | 55.1% | 4 | 16 | 26 | 6 |
| Field 9-12 | 183 | 3.3% | 20.8% | 36.6% | 41.9% | 26 | 90 | 61 | 6 |
| Field 13+ | 81 | 1.2% | 9.9% | 29.6% | 36.2% | 18 | 39 | 23 | 1 |

### Race Class

| Class | Races | Gold | Good | Pass | Place | 0H | 1H | 2H | 3H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM58-70 | 124 | 4.0% | 19.4% | 38.7% | 40.9% | 25 | 51 | 43 | 5 |
| BM72-84 | 17 | 0.0% | 29.4% | 58.8% | 49.0% | 2 | 5 | 10 | 0 |
| BM88+ | 5 | 40.0% | 60.0% | 80.0% | 73.3% | 0 | 1 | 2 | 2 |
| Group 1 | 28 | 3.6% | 25.0% | 42.9% | 45.2% | 3 | 13 | 11 | 1 |
| Group 2/3 | 60 | 3.3% | 20.0% | 33.3% | 41.7% | 7 | 33 | 18 | 2 |
| Maiden | 9 | 0.0% | 11.1% | 22.2% | 37.0% | 1 | 6 | 2 | 0 |
| Other | 73 | 4.1% | 19.2% | 37.0% | 42.5% | 10 | 36 | 24 | 3 |

## Promotion Rule

Promote only if overall Pass/Good improves without increasing 0-hit, then re-score archive with the engine and re-run calibration.