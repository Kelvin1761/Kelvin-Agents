# AU Cached Walk-Forward ML

## Dataset

- Races: **336**
- Horses: **3713**
- Cache: `/private/tmp/au_wong_choi_ml_cache/au_labelled_horse_rows.csv`
- Conditions: Good/Firm 238, Soft 69, Heavy 29
- Top venues: Randwick 189, Flemington 147

## Walk-Forward Result

| Model | Result |
|---|---|
| Ability baseline | 8 Gold / 72 Good / 161 Pass / 89 1H / 23 Miss / Top3 43.7% / W-in-T3 49.5% |
| 7D ML | 7 Gold / 62 Good / 147 Pass / 85 1H / 37 Miss / Top3 39.1% / W-in-T3 38.6% |
| 7D + wet interactions ML | 8 Gold / 62 Good / 150 Pass / 88 1H / 34 Miss / Top3 39.9% / W-in-T3 39.1% |
| 7D + Soft/Heavy split interactions ML | 6 Gold / 61 Good / 149 Pass / 88 1H / 35 Miss / Top3 39.1% / W-in-T3 39.7% |

## Ability Baseline By Condition

| Condition | Races | Result |
|---|---:|---|
| Good/Firm | 144 | 6 Gold / 55 Good / 128 Pass / 73 1H / 16 Miss / Top3 43.8% / W-in-T3 50.0% |
| Heavy | 10 | 0 Gold / 5 Good / 9 Pass / 4 1H / 1 Miss / Top3 46.7% / W-in-T3 60.0% |
| Soft | 30 | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% |

## Soft/Heavy Split ML By Condition

| Condition | Races | Result |
|---|---:|---|
| Good/Firm | 144 | 5 Gold / 49 Good / 116 Pass / 67 1H / 28 Miss / Top3 39.4% / W-in-T3 40.3% |
| Heavy | 10 | 0 Gold / 4 Good / 9 Pass / 5 1H / 1 Miss / Top3 43.3% / W-in-T3 60.0% |
| Soft | 30 | 1 Gold / 8 Good / 24 Pass / 16 1H / 6 Miss / Top3 36.7% / W-in-T3 30.0% |

## Wet Interaction Weights

| Feature | Avg logistic weight |
|---|---:|
| `mx_stability` | +0.8166 |
| `ability_score` | -0.7847 |
| `mx_jockey_trainer` | +0.4112 |
| `mx_track` | +0.3569 |
| `mx_sectional` | +0.2912 |
| `wet_flag` | -0.2147 |
| `mx_race_shape` | -0.1884 |
| `wet_stability` | +0.1149 |
| `mx_form_line` | -0.0316 |
| `mx_class_weight` | +0.0286 |
| `wet_race_shape` | +0.0184 |
| `wet_class_weight` | -0.0180 |

## Soft / Heavy Split Interaction Weights

| Feature | Avg logistic weight |
|---|---:|
| `mx_stability` | +0.8068 |
| `ability_score` | -0.7665 |
| `mx_jockey_trainer` | +0.4063 |
| `mx_track` | +0.3539 |
| `mx_sectional` | +0.2779 |
| `heavy_stability` | +0.2579 |
| `soft_flag` | -0.2439 |
| `heavy_sectional` | +0.2021 |
| `mx_race_shape` | -0.1881 |
| `soft_sectional` | -0.0769 |
| `heavy_track` | +0.0569 |
| `heavy_race_shape` | +0.0492 |
| `soft_stability` | +0.0404 |
| `mx_class_weight` | +0.0386 |

## Promotion Gate

FAILED

- Do not bake wet interaction into live AU scoring yet; keep it as shadow diagnostics until it passes walk-forward and venue buckets.

## Recommendation

- Keep live ranking on `ability_score` only.
- Treat wet track as a 7D interaction first: dynamic emphasis inside `track`, `stability`, `sectional`, and `race_shape` when condition is Soft/Heavy.
- Split Soft and Heavy in diagnostics and candidate tuning; Heavy should require stronger proof because archive sample size is much smaller.
- Only promote an 8th dimension if the wet-only ablation beats 7D on out-of-sample races and at least the major venue buckets.