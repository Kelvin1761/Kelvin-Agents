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
| ML optimised 7D weights | 6 Gold / 72 Good / 158 Pass / 86 1H / 26 Miss / Top3 42.8% / W-in-T3 48.4% | Gold -2, Good +0, Pass -3, Miss +3, Top3 -0.9pp, W-in-T3 -1.1pp |

## Average ML Weights

| Matrix | Current | ML avg | Delta |
|---|---:|---:|---:|
| `mx_stability` | 33.0% | 33.6% | 0.6% |
| `mx_sectional` | 10.5% | 5.5% | -5.0% |
| `mx_race_shape` | 23.4% | 28.5% | 5.1% |
| `mx_jockey_trainer` | 21.4% | 22.8% | 1.4% |
| `mx_class_weight` | 5.0% | 7.0% | 2.0% |
| `mx_track` | 6.7% | 2.4% | -4.3% |
| `mx_form_line` | 0.0% | 0.3% | 0.3% |

## Fold Detail

| Fold | Train races | Validation races | Train best | Validation ML | Validation delta |
|---:|---:|---:|---|---|---|
| 1 | 152 | 28 | 5 Gold / 63 Good / 137 Pass / 74 1H / 15 Miss / Top3 45.0% / W-in-T3 59.9% | 1 Gold / 7 Good / 23 Pass / 16 1H / 5 Miss / Top3 36.9% / W-in-T3 46.4% | Gold +0, Good -1, Pass +0, Miss +0, Top3 -1.2pp, W-in-T3 -10.7pp |
| 2 | 180 | 30 | 7 Gold / 72 Good / 159 Pass / 87 1H / 21 Miss / Top3 44.1% / W-in-T3 56.7% | 2 Gold / 11 Good / 22 Pass / 11 1H / 8 Miss / Top3 38.9% / W-in-T3 36.7% | Gold +0, Good -3, Pass -3, Miss +3, Top3 -6.7pp, W-in-T3 -6.7pp |
| 3 | 210 | 50 | 7 Gold / 78 Good / 184 Pass / 106 1H / 26 Miss / Top3 42.7% / W-in-T3 55.2% | 2 Gold / 22 Good / 46 Pass / 24 1H / 4 Miss / Top3 46.7% / W-in-T3 52.0% | Gold -1, Good -1, Pass +0, Miss +0, Top3 -1.3pp, W-in-T3 -2.0pp |
| 4 | 260 | 40 | 12 Gold / 106 Good / 226 Pass / 120 1H / 34 Miss / Top3 44.1% / W-in-T3 54.2% | 1 Gold / 20 Good / 34 Pass / 14 1H / 6 Miss / Top3 45.8% / W-in-T3 50.0% | Gold -1, Good +2, Pass +1, Miss -1, Top3 +1.7pp, W-in-T3 -2.5pp |
| 5 | 300 | 36 | 12 Gold / 123 Good / 262 Pass / 139 1H / 38 Miss / Top3 44.1% / W-in-T3 53.3% | 0 Gold / 12 Good / 33 Pass / 21 1H / 3 Miss / Top3 41.7% / W-in-T3 52.8% | Gold +0, Good +3, Pass -1, Miss +1, Top3 +1.9pp, W-in-T3 +13.9pp |

## Gate

FAILED

- Do not replace current AU scoring weights. Current `ability_score` baseline remains stronger out-of-sample.