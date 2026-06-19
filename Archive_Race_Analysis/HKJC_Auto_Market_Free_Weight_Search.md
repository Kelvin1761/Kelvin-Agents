# HKJC Auto Market-Free Weight Search

- Search uses only existing matrix scores and race metadata interactions.
- Random seed: `20260527`
- Iterations: `12000`
- Split: train `91` races / validation `40` races

## Baseline (Current Matrix Weights)

- Train: 4 Gold / 47 Good / 57 Pass / 0H 13
- Validation: 3 Gold / 15 Good / 20 Pass / 0H 9
- Full: 7 Gold / 62 Good / 77 Pass / 0H 22

## Validation Candidates

| Rank | Validation | Full | Weights |
|---:|---|---|---|
| 1 | Gold +0.0pp / Good -2.5pp / Pass +5.0pp / Place +0.0pp / 0H -1 / 1H +2 | Gold -0.8pp / Good +0.0pp / Pass +5.3pp / Place +1.0pp / 0H -5 / 1H +5 | sectional -0.27; trainer_signal +0.14; stability +0.35; race_shape -0.33; horse_health +0.21; form_line +0.25; hv_race_shape +0.30; hv_sectional -0.23 |
| 2 | Gold +0.0pp / Good -5.0pp / Pass +5.0pp / Place -0.8pp / 0H -1 / 1H +3 | Gold -0.8pp / Good -2.3pp / Pass +6.1pp / Place +0.3pp / 0H -5 / 1H +8 | sectional -0.29; trainer_signal +0.22; stability +0.33; race_shape -0.15; horse_health -0.09; form_line +0.32; hv_race_shape +0.25; hv_sectional -0.36; st_class_advantage -0.22; wet_track_stability -0.35; sprint_sectional +0.14 |
| 3 | Gold +0.0pp / Good -5.0pp / Pass +5.0pp / Place -1.7pp / 0H +0 / 1H +2 | Gold -1.5pp / Good -3.1pp / Pass +5.3pp / Place -0.3pp / 0H -5 / 1H +9 | trainer_signal +0.34; stability +0.27; class_advantage -0.21; horse_health -0.33; form_line +0.19; hv_race_shape +0.44; hv_sectional -0.43; st_class_advantage +0.34; wet_track_stability -0.37; sprint_sectional +0.28 |
| 4 | Gold +0.0pp / Good +0.0pp / Pass +2.5pp / Place +0.8pp / 0H -1 / 1H +1 | Gold -0.8pp / Good +0.0pp / Pass +3.8pp / Place +1.0pp / 0H -5 / 1H +5 | trainer_signal +0.15; stability +0.32; race_shape -0.12; class_advantage +0.14; horse_health +0.31; form_line +0.09; hv_race_shape +0.40; hv_sectional +0.24; wet_track_stability -0.48; sprint_sectional -0.09 |
| 5 | Gold +0.0pp / Good +0.0pp / Pass +2.5pp / Place +0.8pp / 0H -1 / 1H +1 | Gold -0.8pp / Good +0.0pp / Pass +3.8pp / Place +1.0pp / 0H -5 / 1H +5 | sectional +0.25; trainer_signal +0.19; stability +0.35; race_shape -0.14; form_line +0.19; hv_race_shape +0.32; hv_sectional +0.37; st_class_advantage +0.29; wet_track_stability -0.44; sprint_sectional -0.42 |
| 6 | Gold +0.0pp / Good +0.0pp / Pass +2.5pp / Place +0.0pp / 0H +0 / 1H +0 | Gold -0.8pp / Good +0.8pp / Pass +4.6pp / Place +1.0pp / 0H -4 / 1H +3 | sectional -0.11; trainer_signal +0.19; stability +0.26; class_advantage +0.32; horse_health -0.25; form_line +0.16; hv_race_shape +0.25; hv_sectional -0.31; st_class_advantage +0.08; wet_track_stability -0.38; sprint_sectional -0.50 |
| 7 | Gold +0.0pp / Good +0.0pp / Pass +2.5pp / Place +0.0pp / 0H +0 / 1H +0 | Gold -0.8pp / Good -0.8pp / Pass +5.3pp / Place +0.5pp / 0H -4 / 1H +5 | sectional -0.23; trainer_signal +0.25; stability +0.27; race_shape -0.27; class_advantage +0.13; form_line +0.15; hv_race_shape +0.31; hv_sectional +0.39; st_class_advantage +0.20; sprint_sectional -0.42 |
| 8 | Gold +0.0pp / Good +0.0pp / Pass +2.5pp / Place +0.0pp / 0H +0 / 1H +0 | Gold -0.8pp / Good -0.8pp / Pass +4.6pp / Place +0.5pp / 0H -4 / 1H +5 | sectional -0.14; trainer_signal +0.21; stability +0.23; race_shape -0.22; class_advantage +0.19; hv_race_shape +0.42; hv_sectional -0.17; st_class_advantage +0.13; wet_track_stability +0.40 |
| 9 | Gold +0.0pp / Good +0.0pp / Pass +2.5pp / Place +0.0pp / 0H +0 / 1H +0 | Gold -0.8pp / Good +0.0pp / Pass +3.8pp / Place +0.8pp / 0H -4 / 1H +4 | sectional +0.18; stability +0.21; race_shape -0.28; class_advantage +0.23; horse_health +0.18; hv_race_shape +0.23; hv_sectional +0.16; st_class_advantage -0.24; wet_track_stability +0.34; sprint_sectional +0.13 |
| 10 | Gold +0.0pp / Good -2.5pp / Pass +2.5pp / Place +0.0pp / 0H -1 / 1H +2 | Gold -0.8pp / Good -1.5pp / Pass +4.6pp / Place +0.5pp / 0H -5 / 1H +7 | sectional +0.27; trainer_signal +0.26; stability +0.32; class_advantage -0.09; horse_health -0.32; form_line +0.27; hv_race_shape +0.44; hv_sectional +0.25; st_class_advantage +0.29; wet_track_stability +0.28; sprint_sectional -0.49 |
| 11 | Gold +0.0pp / Good -2.5pp / Pass +2.5pp / Place -0.8pp / 0H +0 / 1H +1 | Gold -0.8pp / Good +0.0pp / Pass +4.6pp / Place +0.8pp / 0H -4 / 1H +4 | sectional -0.20; stability +0.23; race_shape -0.15; class_advantage +0.15; horse_health -0.22; form_line +0.24; hv_race_shape +0.10; wet_track_stability -0.39; sprint_sectional +0.19 |
| 12 | Gold +0.0pp / Good -2.5pp / Pass +2.5pp / Place -0.8pp / 0H +0 / 1H +1 | Gold -0.8pp / Good -1.5pp / Pass +5.3pp / Place +0.3pp / 0H -4 / 1H +6 | sectional +0.24; trainer_signal +0.26; stability +0.29; class_advantage +0.28; horse_health -0.33; form_line +0.32; hv_race_shape +0.22; hv_sectional -0.22; st_class_advantage -0.09; sprint_sectional -0.46 |
| 13 | Gold +0.0pp / Good -2.5pp / Pass +2.5pp / Place -0.8pp / 0H +0 / 1H +1 | Gold -0.8pp / Good -1.5pp / Pass +5.3pp / Place +0.3pp / 0H -4 / 1H +6 | sectional -0.28; trainer_signal +0.24; stability +0.24; race_shape -0.19; class_advantage +0.25; form_line +0.27; hv_race_shape +0.36; hv_sectional +0.24; st_class_advantage +0.13; wet_track_stability +0.14; sprint_sectional -0.16 |
| 14 | Gold +0.0pp / Good -2.5pp / Pass +2.5pp / Place -0.8pp / 0H +0 / 1H +1 | Gold -0.8pp / Good +0.0pp / Pass +3.8pp / Place +0.8pp / 0H -4 / 1H +4 | sectional -0.24; trainer_signal +0.11; stability +0.20; class_advantage +0.31; horse_health -0.09; form_line +0.23; hv_sectional +0.15; wet_track_stability -0.41 |
| 15 | Gold +0.0pp / Good -5.0pp / Pass +2.5pp / Place -0.8pp / 0H -1 / 1H +3 | Gold -0.8pp / Good -1.5pp / Pass +4.6pp / Place +0.3pp / 0H -4 / 1H +6 | sectional -0.24; stability +0.28; race_shape -0.27; class_advantage +0.29; horse_health +0.29; form_line +0.28; hv_race_shape +0.44; hv_sectional +0.17; st_class_advantage -0.37; wet_track_stability +0.47; sprint_sectional -0.33 |

## Promotion Gate

PASSED

- Validation: Gold +0.0pp / Good +0.0pp / Pass +2.5pp / Place +0.8pp / 0H -1 / 1H +1
- Full: Gold -0.8pp / Good +0.0pp / Pass +3.8pp / Place +1.0pp / 0H -5 / 1H +5

### Best Delta Weights (To be merged with Current Matrix)
```python
ML_DELTA_WEIGHTS = {
    "sectional": +0.0127,
    "trainer_signal": +0.1494,
    "stability": +0.3157,
    "race_shape": -0.1169,
    "class_advantage": +0.1367,
    "horse_health": +0.3071,
    "form_line": +0.0878,
    "hv_race_shape": +0.4000,
    "hv_sectional": +0.2366,
    "st_class_advantage": +0.0105,
    "wet_track_stability": -0.4809,
    "sprint_sectional": -0.0916,
}
```