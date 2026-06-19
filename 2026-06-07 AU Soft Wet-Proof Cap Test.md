# AU Soft Wet-Proof Cap Test

## Dataset

- Soft validation races: **30**
- Soft runners: **354**
- Flagged runners: **79** (22.3%)
- Cache: `/private/tmp/au_wong_choi_ml_cache/au_labelled_horse_rows.csv`

## Risk Flag Hit Rates

| Flag | Runners | Actual Top3 | Top3 Rate |
|---|---:|---:|---:|
| `ordinary_track_high_score` | 51 | 8 | 15.7% |
| `speed_stability_only` | 51 | 8 | 15.7% |
| `unstable_profile` | 36 | 5 | 13.9% |
| `wide_draw` | 24 | 6 | 25.0% |
| `exposed_no_wet_place` | 8 | 2 | 25.0% |

## Variant Results

| Variant | Soft Result | Soft Delta | Overall Delta |
|---|---|---|---|
| baseline | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | - | - |
| `balanced_cap` | 2 Gold / 12 Good / 25 Pass / 13 1H / 5 Miss / Top3 43.3% / W-in-T3 46.7% | Gold +0, Good +0, Pass +1, Miss -1, Top3 +1.1pp, W-in-T3 +3.3pp | Gold +0, Good +0, Pass +1, Miss -1, Top3 +0.2pp, W-in-T3 +0.5pp |
| `strict_cap` | 2 Gold / 12 Good / 25 Pass / 13 1H / 5 Miss / Top3 43.3% / W-in-T3 46.7% | Gold +0, Good +0, Pass +1, Miss -1, Top3 +1.1pp, W-in-T3 +3.3pp | Gold +0, Good +0, Pass +1, Miss -1, Top3 +0.2pp, W-in-T3 +0.5pp |
| `light_cap` | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |
| `top3_cap` | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp | Gold +0, Good +0, Pass +0, Miss +0, Top3 +0.0pp, W-in-T3 +0.0pp |

## Gate

PASSED

- Candidate(s): `balanced_cap`, `strict_cap`

## Bucket Gate: balanced_cap

- Gate: **PASSED**

| Bucket | Base | Candidate | Delta |
|---|---|---|---|
| venue:Randwick | 2 Gold / 12 Good / 24 Pass / 12 1H / 6 Miss / Top3 42.2% / W-in-T3 43.3% | 2 Gold / 12 Good / 25 Pass / 13 1H / 5 Miss / Top3 43.3% / W-in-T3 46.7% | Top3 +1.1pp / W-in-T3 +3.3pp / Miss -1 / Pass +1 |
| field:Field 13+ | 1 Gold / 6 Good / 8 Pass / 2 1H / 4 Miss / Top3 41.7% / W-in-T3 41.7% | 1 Gold / 6 Good / 8 Pass / 2 1H / 4 Miss / Top3 41.7% / W-in-T3 41.7% | Top3 +0.0pp / W-in-T3 +0.0pp / Miss +0 / Pass +0 |
| field:Field 9-12 | 1 Gold / 4 Good / 12 Pass / 8 1H / 2 Miss / Top3 40.5% / W-in-T3 42.9% | 1 Gold / 4 Good / 13 Pass / 9 1H / 1 Miss / Top3 42.9% / W-in-T3 50.0% | Top3 +2.4pp / W-in-T3 +7.1pp / Miss -1 / Pass +1 |
| field:Field <=8 | 0 Gold / 2 Good / 4 Pass / 2 1H / 0 Miss / Top3 50.0% / W-in-T3 50.0% | 0 Gold / 2 Good / 4 Pass / 2 1H / 0 Miss / Top3 50.0% / W-in-T3 50.0% | Top3 +0.0pp / W-in-T3 +0.0pp / Miss +0 / Pass +0 |
| date:early | 2 Gold / 8 Good / 17 Pass / 9 1H / 3 Miss / Top3 45.0% / W-in-T3 45.0% | 2 Gold / 8 Good / 17 Pass / 9 1H / 3 Miss / Top3 45.0% / W-in-T3 45.0% | Top3 +0.0pp / W-in-T3 +0.0pp / Miss +0 / Pass +0 |
| date:mid | 0 Gold / 4 Good / 7 Pass / 3 1H / 3 Miss / Top3 36.7% / W-in-T3 40.0% | 0 Gold / 4 Good / 8 Pass / 4 1H / 2 Miss / Top3 40.0% / W-in-T3 50.0% | Top3 +3.3pp / W-in-T3 +10.0pp / Miss -1 / Pass +1 |

## Recommendation

- Keep this as shadow only unless a cap reduces Miss without reducing Top3 precision across more archive/live Soft races.