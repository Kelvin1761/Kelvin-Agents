# AU Auto Market-Free Weight Search (Fresh Scores)

- Re-scored all archive races with current mainline engine (P5+P4 + gate removal).
- Random seed: `20260516`
- Iterations: `12000`
- Split: train `242` races / validation `105` races

## Baseline (Fresh Scores)

- Train: 2.1% Gold / 20.7% Good / 40.1% Pass / 0H 38
- Validation: 4.8% Gold / 21.0% Good / 41.0% Pass / 0H 9
- Full: 2.9% Gold / 20.7% Good / 40.3% Pass / 0H 47

## Validation Candidates

| Rank | Validation | Full | Weights |
|---:|---|---|---|
| 1 | Gold +0.0pp / Good -1.0pp / Pass +0.0pp / Place -0.6pp / 0H +2 / 1H -2 | Gold +0.3pp / Good +0.9pp / Pass +1.4pp / Place +0.8pp / 0H -2 / 1H -3 | stability -0.43; sectional +0.28; race_shape +0.32; class_weight -0.38; track +0.34; form_line +0.41; field13_race_shape -0.45; field13_form_line +0.28; field912_form_line -0.65; field912_stability +0.26; bm_class_weight +0.56; wet_stability -0.57 |
| 2 | Gold -1.0pp / Good -1.0pp / Pass +0.0pp / Place -1.0pp / 0H +2 / 1H -2 | Gold +0.6pp / Good +0.0pp / Pass +3.5pp / Place +1.6pp / 0H -3 / 1H -9 | stability -0.19; sectional -0.21; race_shape -0.11; jockey_trainer -0.14; class_weight -0.44; track +0.25; form_line +0.38; field13_sectional -0.12; field13_form_line +0.49; field912_form_line -0.10; field912_stability -0.39; wet_track -0.60; wet_stability -0.22 |
| 3 | Gold -1.0pp / Good -1.0pp / Pass +0.0pp / Place -1.6pp / 0H +4 / 1H -4 | Gold +0.3pp / Good +1.2pp / Pass +2.0pp / Place +0.9pp / 0H -1 / 1H -6 | stability -0.13; race_shape +0.33; jockey_trainer -0.35; class_weight -0.21; track +0.41; form_line +0.15; field13_race_shape -0.37; field13_sectional -0.58; field13_form_line +0.63; field912_form_line -0.55; field912_stability -0.44; bm_class_weight +0.12; wet_track +0.51; wet_stability -0.29 |
| 4 | Gold -1.0pp / Good +1.0pp / Pass -1.0pp / Place -1.6pp / 0H +3 / 1H -2 | Gold +0.0pp / Good +1.2pp / Pass +2.0pp / Place +0.9pp / 0H -2 / 1H -5 | race_shape +0.12; jockey_trainer -0.37; class_weight +0.22; track +0.45; form_line -0.27; field13_race_shape -0.49; field13_sectional -0.20; field13_form_line +0.28; field912_form_line +0.34; field912_stability -0.51; bm_class_weight -0.14; wet_track +0.26; wet_stability -0.29 |
| 5 | Gold +0.0pp / Good +0.0pp / Pass -1.0pp / Place -1.6pp / 0H +4 / 1H -3 | Gold +0.3pp / Good +0.9pp / Pass +2.0pp / Place +0.9pp / 0H -1 / 1H -6 | stability -0.25; sectional -0.17; jockey_trainer -0.31; class_weight +0.18; track +0.44; form_line +0.20; field13_race_shape -0.44; field13_form_line -0.39; field912_form_line -0.57; field912_stability -0.37; bm_class_weight -0.12; wet_track +0.35; wet_stability -0.27 |
| 6 | Gold -1.0pp / Good +0.0pp / Pass -1.0pp / Place -1.9pp / 0H +4 / 1H -3 | Gold +0.0pp / Good +1.2pp / Pass +1.7pp / Place +0.8pp / 0H -2 / 1H -4 | stability +0.29; sectional +0.31; race_shape +0.30; class_weight +0.18; track +0.43; form_line -0.29; field13_race_shape -0.36; field13_sectional -0.57; field13_form_line +0.20; field912_form_line +0.11; field912_stability -0.57; wet_stability +0.37 |
| 7 | Gold +0.0pp / Good -1.0pp / Pass -1.0pp / Place -1.0pp / 0H +2 / 1H -1 | Gold +0.3pp / Good +1.2pp / Pass +1.2pp / Place +0.7pp / 0H -2 / 1H -2 | stability -0.28; sectional +0.34; race_shape -0.12; jockey_trainer -0.22; class_weight -0.43; track +0.33; form_line +0.19; field13_race_shape +0.37; field13_sectional -0.61; field13_form_line +0.62; field912_form_line -0.58; field912_stability -0.08; bm_class_weight +0.45; wet_track +0.38; wet_stability -0.09 |
| 8 | Gold +0.0pp / Good -1.0pp / Pass -1.0pp / Place -1.3pp / 0H +3 / 1H -2 | Gold +1.2pp / Good +0.6pp / Pass +2.6pp / Place +1.3pp / 0H -1 / 1H -8 | stability -0.40; sectional -0.13; race_shape -0.11; jockey_trainer -0.19; class_weight -0.33; track +0.44; form_line +0.28; field13_race_shape -0.56; field13_form_line +0.39; field912_form_line -0.59; bm_class_weight -0.18; wet_track +0.15; wet_stability +0.24 |
| 9 | Gold +0.0pp / Good -1.0pp / Pass -1.0pp / Place -1.3pp / 0H +3 / 1H -2 | Gold +0.3pp / Good +0.6pp / Pass +2.0pp / Place +1.1pp / 0H -3 / 1H -4 | stability -0.20; race_shape -0.25; jockey_trainer -0.41; class_weight +0.14; track +0.36; form_line +0.14; field13_race_shape -0.39; field13_sectional +0.35; field13_form_line +0.35; field912_form_line -0.36; field912_stability -0.34; bm_class_weight -0.62; wet_stability +0.63 |
| 10 | Gold -1.0pp / Good -1.9pp / Pass -1.0pp / Place -1.3pp / 0H +2 / 1H -1 | Gold +0.0pp / Good +0.3pp / Pass +1.7pp / Place +1.0pp / 0H -4 / 1H -2 | stability -0.43; race_shape +0.37; jockey_trainer -0.40; class_weight +0.32; track +0.39; form_line +0.25; field13_race_shape -0.64; field13_sectional -0.29; field13_form_line +0.16; field912_stability -0.12; wet_track -0.27; wet_stability +0.65 |
| 11 | Gold -1.9pp / Good -1.9pp / Pass -1.0pp / Place -1.6pp / 0H +2 / 1H -1 | Gold +0.0pp / Good +0.6pp / Pass +1.2pp / Place +0.9pp / 0H -5 / 1H +1 | stability -0.39; sectional -0.38; race_shape +0.09; jockey_trainer +0.30; class_weight -0.36; track -0.35; form_line +0.22; field13_race_shape -0.13; field13_form_line +0.46; field912_form_line +0.37; field912_stability -0.42; bm_class_weight -0.18; wet_track +0.31; wet_stability +0.38 |
| 12 | Gold -1.0pp / Good -1.9pp / Pass -1.0pp / Place -1.6pp / 0H +3 / 1H -2 | Gold +0.0pp / Good +0.6pp / Pass +2.0pp / Place +0.9pp / 0H -2 / 1H -5 | sectional -0.16; race_shape -0.14; jockey_trainer -0.34; class_weight +0.18; track +0.44; form_line +0.33; field13_race_shape -0.54; field13_sectional +0.30; field13_form_line +0.22; field912_stability -0.48; bm_class_weight -0.27; wet_track -0.27; wet_stability -0.62 |
| 13 | Gold +0.0pp / Good +0.0pp / Pass -1.9pp / Place -1.0pp / 0H +1 / 1H +1 | Gold +0.3pp / Good +1.2pp / Pass +1.4pp / Place +0.9pp / 0H -3 / 1H -2 | stability -0.42; sectional +0.34; jockey_trainer -0.09; class_weight +0.21; track +0.44; form_line -0.08; field13_race_shape -0.40; field13_sectional -0.31; field13_form_line +0.25; field912_form_line -0.55; field912_stability +0.12; wet_track +0.13; wet_stability +0.64 |
| 14 | Gold -1.0pp / Good +0.0pp / Pass -1.9pp / Place -1.6pp / 0H +2 / 1H +0 | Gold +0.9pp / Good +0.0pp / Pass +3.5pp / Place +1.9pp / 0H -5 / 1H -7 | stability -0.27; sectional -0.31; class_weight -0.37; track +0.43; field13_race_shape +0.29; field13_sectional -0.31; field13_form_line +0.31; field912_form_line -0.50; field912_stability -0.60; bm_class_weight -0.44; wet_track +0.52; wet_stability +0.26 |
| 15 | Gold +0.0pp / Good -1.0pp / Pass -1.9pp / Place -0.6pp / 0H +0 / 1H +2 | Gold +0.3pp / Good +0.9pp / Pass +1.7pp / Place +1.0pp / 0H -3 / 1H -3 | stability -0.24; race_shape -0.34; jockey_trainer -0.15; class_weight -0.37; track +0.20; form_line +0.27; field13_race_shape -0.43; field13_sectional -0.29; field13_form_line +0.20; field912_form_line -0.33; bm_class_weight -0.25; wet_track -0.29; wet_stability +0.30 |

## Promotion Gate

FAILED

No candidate improved validation Pass/Good while keeping 0-hit flat or lower on both splits.