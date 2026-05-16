# AU Auto Market-Free Weight Search

- Search uses only existing section scores and race metadata interactions.
- No market odds, SP, favourite rank, price movement, or market field is used.
- Random seed: `20260515`
- Iterations: `12000`
- Split: train `220` races / validation `95` races

## Baseline

- Train: 2.3% Gold / 14.5% Good / 35.9% Pass / 0H 39
- Validation: 7.4% Gold / 21.1% Good / 35.8% Pass / 0H 13
- Full: 3.8% Gold / 16.5% Good / 35.9% Pass / 0H 52

## Validation Candidates

| Rank | Validation | Full | Weights |
|---:|---|---|---|
| 1 | Gold +0.0pp / Good -1.1pp / Pass +4.2pp / Place +1.1pp / 0H +1 / 1H -5 | Gold +0.3pp / Good +0.0pp / Pass +2.5pp / Place +0.7pp / 0H +2 / 1H -10 | stability -0.24; sectional -0.21; class_weight +0.13; track -0.37; form_line +0.18; field13_form_line +0.14; field912_form_line -0.16; field912_stability -0.34; bm_class_weight -0.36; wet_track -0.60; wet_stability +0.60 |
| 2 | Gold -1.1pp / Good +1.1pp / Pass +3.2pp / Place +0.7pp / 0H +0 / 1H -3 | Gold +0.0pp / Good +1.3pp / Pass +2.2pp / Place +0.7pp / 0H +0 / 1H -7 | stability -0.19; race_shape -0.31; jockey_trainer +0.31; class_weight -0.24; track -0.33; form_line -0.29; field13_race_shape -0.20; field13_sectional +0.46; field13_form_line +0.53; field912_form_line +0.40; field912_stability -0.09; bm_class_weight -0.24; wet_track -0.63 |
| 3 | Gold -1.1pp / Good +0.0pp / Pass +3.2pp / Place +0.0pp / 0H +2 / 1H -5 | Gold -0.3pp / Good +0.3pp / Pass +2.2pp / Place +0.4pp / 0H +2 / 1H -9 | sectional +0.35; race_shape -0.20; jockey_trainer +0.39; class_weight -0.21; track -0.40; field13_race_shape -0.12; field13_sectional -0.20; field13_form_line +0.32; field912_form_line +0.16; field912_stability -0.46; bm_class_weight +0.11; wet_track +0.39; wet_stability +0.40 |
| 4 | Gold -1.1pp / Good -1.1pp / Pass +3.2pp / Place +1.1pp / 0H -1 / 1H -2 | Gold +0.0pp / Good +0.0pp / Pass +1.9pp / Place +0.8pp / 0H -2 / 1H -4 | stability -0.20; sectional +0.39; race_shape -0.36; jockey_trainer +0.11; class_weight -0.36; track -0.45; form_line -0.45; field13_race_shape -0.65; field13_sectional +0.11; field912_form_line -0.15; field912_stability -0.16; wet_track +0.38; wet_stability +0.32 |
| 5 | Gold -2.1pp / Good +0.0pp / Pass +2.1pp / Place -0.4pp / 0H +1 / 1H -3 | Gold -1.3pp / Good +1.3pp / Pass +2.2pp / Place +0.0pp / 0H +3 / 1H -10 | stability +0.25; sectional -0.17; race_shape -0.16; jockey_trainer +0.32; class_weight -0.43; track -0.45; form_line +0.23; field13_race_shape +0.23; field13_sectional +0.58; field13_form_line +0.47; field912_form_line -0.37; field912_stability +0.27; bm_class_weight -0.33; wet_track -0.45; wet_stability +0.26 |
| 6 | Gold +0.0pp / Good +0.0pp / Pass +2.1pp / Place +0.0pp / 0H +2 / 1H -4 | Gold +0.0pp / Good +0.3pp / Pass +1.0pp / Place +0.5pp / 0H -2 / 1H -1 | stability -0.26; sectional -0.35; jockey_trainer +0.43; class_weight +0.20; track -0.25; form_line +0.33; field13_race_shape +0.57; field13_sectional +0.61; field13_form_line -0.11; field912_form_line -0.29; bm_class_weight -0.42; wet_track -0.40; wet_stability +0.47 |
| 7 | Gold -1.1pp / Good -1.1pp / Pass +2.1pp / Place +0.7pp / 0H -1 / 1H -1 | Gold +0.0pp / Good +0.3pp / Pass +1.0pp / Place +0.6pp / 0H -3 / 1H +0 | race_shape -0.10; jockey_trainer +0.12; class_weight -0.40; track -0.36; form_line -0.30; field13_race_shape +0.31; field13_sectional +0.49; field13_form_line -0.56; field912_form_line -0.16; field912_stability -0.18; bm_class_weight +0.10; wet_track -0.09; wet_stability +0.22 |
| 8 | Gold +1.1pp / Good -1.1pp / Pass +2.1pp / Place +0.7pp / 0H +1 / 1H -3 | Gold +0.0pp / Good +0.3pp / Pass +1.3pp / Place +0.6pp / 0H -2 / 1H -2 | stability -0.23; sectional +0.36; race_shape -0.40; class_weight -0.18; track -0.35; form_line +0.23; field13_race_shape +0.13; field13_sectional +0.30; field13_form_line +0.22; field912_form_line +0.14; field912_stability -0.57; bm_class_weight -0.44; wet_track -0.58; wet_stability +0.28 |
| 9 | Gold -1.1pp / Good -1.1pp / Pass +2.1pp / Place -0.4pp / 0H +2 / 1H -4 | Gold -0.6pp / Good +1.0pp / Pass +1.9pp / Place +0.1pp / 0H +3 / 1H -9 | stability -0.33; sectional +0.23; race_shape -0.38; jockey_trainer +0.40; class_weight -0.34; track -0.23; form_line +0.19; field13_race_shape +0.11; field13_sectional +0.33; field13_form_line -0.22; field912_form_line +0.14; field912_stability +0.43; wet_track -0.45; wet_stability +0.46 |
| 10 | Gold +0.0pp / Good -2.1pp / Pass +2.1pp / Place +0.7pp / 0H +0 / 1H -2 | Gold +0.0pp / Good +0.0pp / Pass +1.9pp / Place +0.7pp / 0H -1 / 1H -5 | stability -0.37; sectional +0.30; race_shape -0.17; jockey_trainer +0.19; class_weight -0.10; track -0.41; form_line -0.14; field13_race_shape -0.18; field13_sectional +0.20; field13_form_line +0.48; field912_form_line +0.38; bm_class_weight -0.34; wet_track -0.35; wet_stability +0.30 |
| 11 | Gold -1.1pp / Good -2.1pp / Pass +2.1pp / Place -0.4pp / 0H +2 / 1H -4 | Gold -1.0pp / Good +0.3pp / Pass +2.5pp / Place +0.1pp / 0H +4 / 1H -12 | stability +0.35; sectional +0.36; race_shape -0.34; jockey_trainer +0.27; track -0.32; form_line +0.12; field13_race_shape +0.44; field13_sectional -0.19; field13_form_line +0.47; field912_form_line +0.49; field912_stability -0.28; bm_class_weight -0.60; wet_track -0.49 |
| 12 | Gold -1.1pp / Good -2.1pp / Pass +2.1pp / Place -0.4pp / 0H +2 / 1H -4 | Gold -0.3pp / Good +0.6pp / Pass +1.9pp / Place +0.2pp / 0H +3 / 1H -9 | stability +0.41; sectional -0.24; race_shape -0.24; jockey_trainer +0.41; class_weight -0.30; form_line +0.23; field13_race_shape +0.32; field13_sectional -0.62; field13_form_line -0.40; field912_form_line +0.10; field912_stability +0.44; wet_track -0.63; wet_stability -0.40 |
| 13 | Gold +0.0pp / Good -3.2pp / Pass +2.1pp / Place +0.4pp / 0H +1 / 1H -3 | Gold -0.3pp / Good -0.3pp / Pass +2.2pp / Place +0.4pp / 0H +2 / 1H -9 | sectional +0.19; race_shape +0.25; jockey_trainer +0.33; class_weight +0.08; track -0.37; form_line +0.40; field13_race_shape -0.27; field13_sectional -0.17; field13_form_line +0.50; field912_form_line +0.63; field912_stability -0.61; bm_class_weight -0.49; wet_track -0.16; wet_stability +0.45 |
| 14 | Gold -1.1pp / Good +0.0pp / Pass +1.1pp / Place -0.4pp / 0H +1 / 1H -2 | Gold -0.6pp / Good +0.0pp / Pass +1.6pp / Place +0.3pp / 0H +0 / 1H -5 | stability -0.28; sectional +0.29; race_shape -0.39; jockey_trainer +0.39; class_weight -0.40; track -0.39; form_line +0.09; field13_sectional +0.53; field13_form_line -0.58; field912_stability +0.17; bm_class_weight +0.14; wet_track +0.57; wet_stability +0.23 |
| 15 | Gold +0.0pp / Good -2.1pp / Pass +1.1pp / Place +0.0pp / 0H +1 / 1H -2 | Gold +0.3pp / Good +0.0pp / Pass +1.0pp / Place +0.5pp / 0H -1 / 1H -2 | sectional +0.40; race_shape -0.11; jockey_trainer +0.39; track -0.34; form_line +0.11; field13_race_shape -0.35; field13_sectional -0.49; field13_form_line -0.32; field912_form_line +0.53; field912_stability -0.32; bm_class_weight -0.34; wet_track -0.60; wet_stability -0.52 |

## Promotion Gate

PASSED

- Validation: Gold -1.1pp / Good +1.1pp / Pass +3.2pp / Place +0.7pp / 0H +0 / 1H -3
- Full: Gold +0.0pp / Good +1.3pp / Pass +2.2pp / Place +0.7pp / 0H +0 / 1H -7