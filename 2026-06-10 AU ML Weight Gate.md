# AU ML Weight Gate

## Dataset

- Races: **336**
- Validation races: **184**
- Horses: **3713**
- Cache: `/private/tmp/au_wong_choi_ml_cache/au_labelled_horse_rows.csv`

## Walk-Forward Result

| Model | Result | Delta vs ability baseline |
|---|---|---|
| Current ability baseline | 8 Gold / 72 Good / 161 Pass / 89 1H / 23 Miss / Top3 43.7% / W-in-T3 49.5% | - |
| Current 7D weights only | 5 Gold / 74 Good / 158 Pass / 84 1H / 26 Miss / Top3 42.9% / W-in-T3 46.7% | Gold -3, Good +2, Pass -3, Miss +3, Top3 -0.7pp, W-in-T3 -2.7pp |
| ML optimised 7D weights | 6 Gold / 68 Good / 158 Pass / 90 1H / 26 Miss / Top3 42.0% / W-in-T3 45.1% | Gold -2, Good -4, Pass -3, Miss +3, Top3 -1.6pp, W-in-T3 -4.3pp |

## Average ML Weights

| Matrix | Current | ML avg | Delta |
|---|---:|---:|---:|
| `mx_stability` | 33.0% | 33.9% | 0.9% |
| `mx_sectional` | 10.5% | 5.9% | -4.6% |
| `mx_race_shape` | 23.4% | 28.1% | 4.7% |
| `mx_jockey_trainer` | 21.4% | 21.9% | 0.5% |
| `mx_class_weight` | 5.0% | 5.2% | 0.2% |
| `mx_track` | 6.7% | 5.0% | -1.7% |
| `mx_form_line` | 0.0% | 0.0% | 0.0% |

## Fold Detail

| Fold | Train races | Validation races | Train best | Validation ML | Validation delta |
|---:|---:|---:|---|---|---|
| 1 | 152 | 28 | 5 Gold / 63 Good / 137 Pass / 74 1H / 15 Miss / Top3 45.0% / W-in-T3 59.9% | 1 Gold / 7 Good / 23 Pass / 16 1H / 5 Miss / Top3 36.9% / W-in-T3 46.4% | Gold +0, Good -1, Pass +0, Miss +0, Top3 -1.2pp, W-in-T3 -10.7pp |
| 2 | 180 | 30 | 7 Gold / 72 Good / 159 Pass / 87 1H / 21 Miss / Top3 44.1% / W-in-T3 56.7% | 2 Gold / 11 Good / 22 Pass / 11 1H / 8 Miss / Top3 38.9% / W-in-T3 36.7% | Gold +0, Good -3, Pass -3, Miss +3, Top3 -6.7pp, W-in-T3 -6.7pp |
| 3 | 210 | 50 | 7 Gold / 78 Good / 184 Pass / 106 1H / 26 Miss / Top3 42.7% / W-in-T3 55.2% | 2 Gold / 22 Good / 46 Pass / 24 1H / 4 Miss / Top3 46.7% / W-in-T3 52.0% | Gold -1, Good -1, Pass +0, Miss +0, Top3 -1.3pp, W-in-T3 -2.0pp |
| 4 | 260 | 40 | 11 Gold / 101 Good / 228 Pass / 127 1H / 32 Miss / Top3 43.6% / W-in-T3 55.0% | 1 Gold / 18 Good / 34 Pass / 16 1H / 6 Miss / Top3 44.2% / W-in-T3 45.0% | Gold -1, Good +0, Pass +1, Miss -1, Top3 +0.0pp, W-in-T3 -7.5pp |
| 5 | 300 | 36 | 13 Gold / 124 Good / 262 Pass / 138 1H / 38 Miss / Top3 44.3% / W-in-T3 52.7% | 0 Gold / 10 Good / 33 Pass / 23 1H / 3 Miss / Top3 39.8% / W-in-T3 41.7% | Gold +0, Good +1, Pass -1, Miss +1, Top3 +0.0pp, W-in-T3 +2.8pp |

## Gate

FAILED

- Do not replace current AU scoring weights. Current `ability_score` baseline remains stronger out-of-sample.