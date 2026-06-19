# AU Auto Market-Free Weight Search

- Search uses only existing section scores and race metadata interactions.
- No market odds, SP, favourite rank, price movement, or market field is used.
- Random seed: `20260515`
- Iterations: `12000`
- Split: train `233` races / validation `100` races

## Baseline

- Train: 4.3% Gold / 18.9% Good / 39.5% Pass / 0H 40
- Validation: 3.0% Gold / 25.0% Good / 38.0% Pass / 0H 10
- Full: 3.9% Gold / 20.7% Good / 39.0% Pass / 0H 50

## Validation Candidates

| Rank | Validation | Full | Weights |
|---:|---|---|---|
| 1 | Gold +1.0pp / Good +0.0pp / Pass +2.0pp / Place +0.7pp / 0H +1 / 1H -3 | Gold +1.2pp / Good +1.2pp / Pass +1.2pp / Place +0.9pp / 0H -1 / 1H -3 | stability +0.08; sectional -0.12; race_shape +0.36; class_weight +0.25; track -0.19; form_line -0.28; field13_race_shape -0.25; field13_sectional +0.15; field13_form_line -0.48; field912_form_line +0.15; field912_stability -0.18; bm_class_weight -0.46; wet_track -0.50; wet_stability -0.62 |
| 2 | Gold +0.0pp / Good -1.0pp / Pass +1.0pp / Place +0.3pp / 0H +0 / 1H -1 | Gold +0.9pp / Good +0.6pp / Pass +1.2pp / Place +1.2pp / 0H -5 / 1H +1 | stability +0.42; sectional -0.26; race_shape +0.08; jockey_trainer +0.27; track -0.12; form_line -0.12; field13_race_shape -0.42; field13_sectional -0.46; field13_form_line -0.43; field912_form_line -0.56; field912_stability -0.32; bm_class_weight -0.56; wet_track -0.34; wet_stability -0.23 |
| 3 | Gold +0.0pp / Good -1.0pp / Pass +1.0pp / Place +0.3pp / 0H +0 / 1H -1 | Gold +0.0pp / Good +0.6pp / Pass +0.3pp / Place +0.7pp / 0H -6 / 1H +5 | stability -0.26; race_shape -0.35; jockey_trainer +0.19; form_line +0.36; field13_race_shape +0.55; field13_form_line -0.62; field912_form_line -0.43; field912_stability +0.26; bm_class_weight -0.33; wet_track -0.32; wet_stability +0.25 |
| 4 | Gold +0.0pp / Good -1.0pp / Pass +1.0pp / Place -0.3pp / 0H +2 / 1H -3 | Gold +0.0pp / Good +0.6pp / Pass +1.2pp / Place +0.7pp / 0H -3 / 1H -1 | stability -0.19; sectional -0.29; race_shape -0.33; jockey_trainer +0.33; class_weight -0.24; field13_race_shape +0.25; field13_form_line +0.39; field912_form_line -0.41; field912_stability +0.15; bm_class_weight -0.36; wet_track -0.50; wet_stability -0.47 |
| 5 | Gold +1.0pp / Good -2.0pp / Pass +1.0pp / Place +0.7pp / 0H +0 / 1H -1 | Gold +0.6pp / Good +0.3pp / Pass +1.2pp / Place +0.9pp / 0H -3 / 1H -1 | stability -0.41; sectional -0.08; jockey_trainer +0.26; class_weight +0.19; track -0.33; form_line -0.31; field13_race_shape +0.34; field13_sectional +0.33; field912_stability +0.09; bm_class_weight -0.61; wet_track -0.44 |
| 6 | Gold +0.0pp / Good +0.0pp / Pass +0.0pp / Place +0.3pp / 0H -1 / 1H +1 | Gold +0.6pp / Good +1.5pp / Pass +0.3pp / Place +0.8pp / 0H -5 / 1H +4 | stability -0.13; race_shape -0.21; jockey_trainer +0.14; form_line -0.16; field13_race_shape +0.48; field13_form_line -0.41; field912_form_line -0.61; bm_class_weight -0.31; wet_track -0.56; wet_stability -0.37 |
| 7 | Gold +0.0pp / Good +0.0pp / Pass +0.0pp / Place -0.3pp / 0H +1 / 1H -1 | Gold +0.9pp / Good +0.9pp / Pass +0.6pp / Place +0.7pp / 0H -2 / 1H +0 | sectional -0.28; race_shape +0.16; class_weight -0.37; track -0.29; form_line -0.40; field13_race_shape +0.11; field13_sectional +0.30; field13_form_line -0.15; field912_form_line +0.22; field912_stability +0.10; bm_class_weight -0.19; wet_track -0.26; wet_stability -0.48 |
| 8 | Gold +0.0pp / Good -1.0pp / Pass +0.0pp / Place +0.3pp / 0H -1 / 1H +1 | Gold +0.3pp / Good +0.9pp / Pass +0.0pp / Place +0.5pp / 0H -4 / 1H +4 | stability -0.10; sectional -0.14; race_shape -0.26; class_weight +0.35; form_line -0.16; field13_race_shape +0.27; field13_sectional -0.56; field13_form_line -0.30; field912_form_line +0.45; field912_stability -0.26; bm_class_weight -0.52; wet_track -0.43; wet_stability -0.20 |
| 9 | Gold +0.0pp / Good -1.0pp / Pass +0.0pp / Place +0.0pp / 0H +0 / 1H +0 | Gold +0.9pp / Good +0.6pp / Pass +0.3pp / Place +0.8pp / 0H -4 / 1H +3 | stability -0.11; sectional -0.43; jockey_trainer +0.23; class_weight +0.16; track -0.29; form_line +0.08; field13_sectional +0.40; field13_form_line +0.12; field912_form_line -0.37; field912_stability +0.21; bm_class_weight -0.58; wet_track -0.30; wet_stability -0.39 |
| 10 | Gold +0.0pp / Good -2.0pp / Pass +0.0pp / Place +0.0pp / 0H +0 / 1H +0 | Gold +0.9pp / Good +0.3pp / Pass +0.3pp / Place +0.9pp / 0H -5 / 1H +4 | stability -0.22; sectional -0.40; jockey_trainer +0.19; class_weight +0.30; track -0.19; form_line -0.39; field13_race_shape -0.14; field13_sectional +0.26; field13_form_line +0.49; field912_form_line -0.35; field912_stability +0.15; bm_class_weight -0.48; wet_track -0.34 |
| 11 | Gold +0.0pp / Good -2.0pp / Pass +0.0pp / Place +0.0pp / 0H +0 / 1H +0 | Gold +0.3pp / Good +0.6pp / Pass +0.0pp / Place +0.3pp / 0H -2 / 1H +2 | stability -0.42; sectional +0.20; race_shape +0.36; jockey_trainer +0.25; class_weight -0.19; form_line -0.29; field13_race_shape -0.62; field13_sectional -0.36; field912_stability +0.45; wet_track -0.45; wet_stability -0.58 |
| 12 | Gold +0.0pp / Good -3.0pp / Pass +0.0pp / Place +0.0pp / 0H +0 / 1H +0 | Gold -0.3pp / Good +0.3pp / Pass +0.3pp / Place +0.5pp / 0H -5 / 1H +4 | stability -0.09; sectional -0.18; race_shape +0.40; jockey_trainer +0.36; class_weight -0.31; track -0.28; field13_race_shape -0.13; field13_sectional -0.27; field13_form_line -0.17; field912_form_line +0.40; bm_class_weight -0.40; wet_track -0.51; wet_stability -0.12 |
| 13 | Gold +0.0pp / Good -1.0pp / Pass -1.0pp / Place +0.0pp / 0H -1 / 1H +2 | Gold +0.3pp / Good +0.9pp / Pass +0.0pp / Place +0.5pp / 0H -4 / 1H +4 | stability -0.32; class_weight +0.15; track -0.10; form_line -0.35; field13_race_shape -0.63; field13_sectional -0.48; field13_form_line +0.20; field912_form_line -0.60; bm_class_weight -0.58; wet_track -0.37; wet_stability +0.13 |
| 14 | Gold +0.0pp / Good -1.0pp / Pass -1.0pp / Place +0.0pp / 0H -1 / 1H +2 | Gold +0.9pp / Good +0.6pp / Pass +0.3pp / Place +0.7pp / 0H -3 / 1H +2 | stability +0.31; race_shape +0.28; jockey_trainer +0.31; class_weight +0.27; form_line -0.40; field13_race_shape +0.23; field13_sectional -0.49; field13_form_line -0.30; field912_form_line -0.31; field912_stability -0.26; bm_class_weight -0.49; wet_track -0.39; wet_stability -0.48 |
| 15 | Gold +0.0pp / Good -2.0pp / Pass -1.0pp / Place -0.3pp / 0H +0 / 1H +1 | Gold +0.3pp / Good +0.0pp / Pass +1.2pp / Place +0.9pp / 0H -4 / 1H +0 | stability -0.25; sectional -0.33; race_shape +0.18; jockey_trainer +0.16; form_line -0.34; field13_race_shape -0.19; field13_sectional +0.32; field13_form_line +0.41; field912_form_line -0.31; field912_stability +0.58; bm_class_weight -0.51; wet_track -0.60; wet_stability -0.18 |

## Promotion Gate

FAILED

No candidate improved validation Pass/Good while keeping validation and full 0-hit flat or lower.