# AU ML Readiness Report

**Dataset classification: READY WITH LIMITATIONS**

## Dataset

- Total races: **805**
- Total runners: **8249**
- Date range: **2025-09-06 → 2026-08-07**
- Average field size: **12.21**
- Usable races: **805**
- Excluded races: **0**

## Champion Freeze

- Model: Current AU Wong Choi Rating Matrix
- Commit SHA: `b1865752631720348509307362b7d91ec5c126d9`
- Readiness/report build SHA: `f679b19789492d6272305a9ba7ae0af81c666b27`
- Runtime dataset SHA256: `971305b1e4e8805435c91a3181ab67bdc000bc53ed26ddc17d4b0c9f04773aa5`
- Matrix weights: `{"class_weight": 0.12042, "jockey_trainer": 0.22957, "pace_perf": 0.10559, "race_shape": 0.13485, "stability": 0.3292, "track": 0.08037}`
- Frozen scorer source SHA256:
  - `.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py`: `74617a16ce317d0ac9bfef1851d711d543722a291ef69da5bd32da18030587c4`
  - `.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/scoring.py`: `32b7e19cd8acaab2d7ec5475385e167d250f10462decc7477db151e29fbfde3b`
  - `.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/matrix_mapper.py`: `188e394975bc3d113ed33be81ff2f2b6345412e39522371971e6347d8d6a7534`
- Leaf features: `["form_score", "trial_score", "sectional_score", "pace_map_score", "jockey_score", "trainer_score", "jockey_horse_fit_score", "class_score", "rating_score", "weight_score", "distance_score", "track_score", "formline_score", "consistency_score", "performance_quality_score", "health_score", "confidence_score", "pace_figure_score"]`
- Matrix formulas: `{"class_weight": [["rating_score", 0.7]], "form_line": [["formline_score", 0.78], ["form_score", 0.22]], "jockey_trainer": [["jockey_score", 0.333333], ["trainer_score", 0.285714], ["jockey_horse_fit_score", 0.380952]], "pace_perf": [["pace_figure_score", 0.941744], ["trial_score", 0.058256]], "race_shape": [["pace_map_score", 1.0]], "stability": [["form_score", 0.6], ["performance_quality_score", 0.4]], "track": [["track_score", 1.0]]}`
- Matrix display gains: `{"class_weight": 2.7489, "form_line": 1.0232, "jockey_trainer": 2.4973, "pace_perf": 0.9909, "race_shape": 4.1142, "stability": 0.975, "track": 1.5193}`
- Ability/ranking logic: sum(matrix_score * matrix_weight) + wet_form_feature; rank descending; horse number breaks exact ties
- Wet overlay: `{"max_abs": 5.49, "prior": 0.5, "scale": 13.19, "scope": "Soft/Heavy only; zero on Good/Firm/Synthetic", "shrink_a": 4.0}`
- Thresholds: `{"confidence_top1_top3_gap": {"clear_gte": 5.0, "medium_lt": 5.0, "tight_lt": 2.0}, "grade": [[96, "S+"], [92, "S"], [88, "S-"], [84, "A+"], [80, "A"], [76, "A-"], [72, "B+"], [68, "B"], [64, "B-"], [60, "C+"], [56, "C"], [52, "C-"], [48, "D"], [0, "E"]], "matrix_advantage": 72.0, "matrix_disadvantage": 48.0, "model_top_pick_ranks": [1, 2], "radar_size": {"clear": 4, "medium": 4, "tight": 5}, "top_pick_tie_gap": 0.5}`
- Production betting rule: No automatic odds-based bet/stake rule in the frozen deterministic scorer; it produces rankings and confidence/radar output.
- Research betting rule: After analysis freeze only: flat 1u Win, predicted edge >=5 percentage points, SP 1.5–50; no Place bet without historical Place dividends.

## Data Integrity And Leakage

- Duplicate race IDs: **0**
- Duplicate runners: **0**
- Target/future run records in Facts: **0**
- Market-like raw keys quarantined from features: `{}`
- Other integrity counts: `{'declared_field_size_mismatch': 285, 'dead_heat_or_duplicate_winner': 2}`
- Starting Price exists only as `market_sp_label`; explicit allow-lists prevent it entering model features.

## Race Coverage

- Venue: `{"Ballarat": 16, "Ballarat Synthetic": 17, "Belmont": 8, "Canberra": 7, "Canterbury": 29, "Caulfield": 27, "Caulfield Heath": 16, "Coffs Harbour": 8, "Cranbourne": 23, "Doomben": 25, "Eagle Farm": 45, "Flemington": 127, "Geelong": 25, "Gold Coast": 8, "Gosford": 15, "Hawkesbury": 7, "Hobart": 9, "Ipswich": 7, "Kensington": 7, "Moe": 4, "Moree": 7, "Mount Gambier": 7, "Northam": 8, "Pakenham": 24, "Randwick": 182, "Rosehill Gardens": 56, "Sale": 14, "Sandown Lakeside": 31, "Seymour": 8, "Sunshine Coast": 8, "Warwick Farm": 30}`
- Distance: `{"Middle1500-1800": 182, "Sprint1200-1400": 329, "Sprint<=1100": 180, "Staying1900-2200": 74, "Staying2300+": 40}`
- Class: `{"Benchmark": 322, "BlackType": 83, "Handicap": 87, "Maiden": 110, "Other": 185, "SetWeights": 18}`
- Track condition: `{"Good/Firm": 284, "Heavy": 121, "Soft": 370, "Synthetic": 24, "Unknown": 6}`

## Feature Coverage

| Feature | Coverage | Missing | Neutral 60 | Unique | Range |
|---|---:|---:|---:|---:|---|
| `recent_field_percentile_3` | 7.2% | 92.8% | 0.0% | 116 | 0.191…1 |
| `same_going_place_rate` | 10.3% | 89.7% | 0.0% | 29 | 0…1 |
| `pf_l800_delta_avg` | 46.6% | 53.4% | 0.0% | 1753 | -4.48…23 |
| `pf_l200_delta_avg` | 46.8% | 53.2% | 0.0% | 1047 | -1.48…12.6 |
| `pf_l400_delta_avg` | 46.8% | 53.2% | 0.0% | 1435 | -2.88…15 |
| `pf_tempo_qrank_avg` | 46.8% | 53.2% | 0.0% | 727 | 0.0067…1 |
| `same_track_place_rate` | 47.6% | 52.4% | 0.0% | 22 | 0…1 |
| `current_jockey_place_rate` | 48.7% | 51.3% | 0.0% | 69 | 0…1 |
| `current_jockey_win_rate` | 48.7% | 51.3% | 0.0% | 64 | 0…1 |
| `same_distance_place_rate` | 52.8% | 47.2% | 0.0% | 27 | 0…1 |
| `rating` | 71.6% | 28.4% | 2.0% | 92 | 31…153 |
| `near_distance_place_rate` | 77.6% | 22.4% | 0.0% | 33 | 0…1 |
| `pf_early_race_pace` | 80.7% | 19.3% | 0.0% | 6 | — |
| `pf_early_runner_pace` | 80.7% | 19.3% | 0.0% | 6 | — |
| `shape_consensus` | 82.2% | 17.8% | 0.0% | 3 | — |
| `pf_race_time_diff_avg` | 82.8% | 17.2% | 0.0% | 2597 | -5.49…20.6 |
| `class_move` | 90.9% | 9.1% | 0.0% | 5 | — |
| `recent_finish_best_3` | 91.9% | 8.1% | 0.0% | 10 | 1…10 |
| `recent_finish_mean_3` | 91.9% | 8.1% | 0.0% | 37 | 1…10 |
| `recent_finish_mean_5` | 91.9% | 8.1% | 0.0% | 90 | 1…10 |
| `recent_place_rate_5` | 91.9% | 8.1% | 0.0% | 11 | 0…1 |
| `recent_win_rate_5` | 91.9% | 8.1% | 0.0% | 11 | 0…1 |
| `pf_l600_delta_avg` | 94.4% | 5.6% | 0.0% | 2675 | -10.9…17.7 |
| `weight` | 94.4% | 5.6% | 3.0% | 40 | 49…76.5 |
| `days_since_last_run` | 94.8% | 5.2% | 0.0% | 310 | 2…784 |
| `trainer_ly_place_rate` | 97.2% | 2.8% | 0.0% | 2130 | 0…1 |
| `trainer_ly_win_rate` | 97.2% | 2.8% | 0.0% | 1807 | 0…0.5 |
| `jockey_ly_place_rate` | 99.3% | 0.7% | 0.0% | 1859 | 0.0435…0.6 |
| `jockey_ly_win_rate` | 99.3% | 0.7% | 0.0% | 1770 | 0…0.4 |
| `going_bucket` | 99.4% | 0.6% | 0.0% | 4 | — |
| `barrier` | 100.0% | 0.0% | 0.0% | 24 | 1…24 |
| `barrier_pct` | 100.0% | 0.0% | 0.0% | 172 | 0…1 |
| `current_jockey_rides` | 100.0% | 0.0% | 0.0% | 26 | 0…38 |
| `days_since_last_run_missing` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `distance_bucket` | 100.0% | 0.0% | 0.0% | 5 | — |
| `field_size` | 100.0% | 0.0% | 0.0% | 21 | 4…24 |
| `field_size_bucket` | 100.0% | 0.0% | 0.0% | 3 | — |
| `formal_count` | 100.0% | 0.0% | 0.0% | 11 | 0…10 |
| `jockey_ly_log_rides` | 100.0% | 0.0% | 0.0% | 754 | 0…6.97 |
| `leaf_class_score` | 100.0% | 0.0% | 22.7% | 28 | 47.7…67.5 |
| `leaf_class_score_derived` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_class_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_class_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_class_score_observed` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_confidence_score` | 100.0% | 0.0% | 0.0% | 29 | 63…92 |
| `leaf_confidence_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 1…1 |
| `leaf_confidence_score_fallback` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_confidence_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_confidence_score_observed` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_consistency_score` | 100.0% | 0.0% | 0.0% | 316 | 46.1…100 |
| `leaf_consistency_score_derived` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_consistency_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_consistency_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_consistency_score_observed` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_distance_score` | 100.0% | 0.0% | 16.5% | 15 | 49…66 |
| `leaf_distance_score_derived` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_distance_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_distance_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_distance_score_observed` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_form_score` | 100.0% | 0.0% | 6.9% | 1476 | 35.5…100 |
| `leaf_form_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_form_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_form_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_form_score_observed` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_formline_score` | 100.0% | 0.0% | 10.7% | 127 | 53…100 |
| `leaf_formline_score_derived` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_formline_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_formline_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_formline_score_observed` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_health_score` | 100.0% | 0.0% | 17.3% | 23 | 55…61.4 |
| `leaf_health_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_health_score_fallback` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_health_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_health_score_observed` | 100.0% | 0.0% | 0.0% | 1 | 1…1 |
| `leaf_jockey_horse_fit_score` | 100.0% | 0.0% | 0.0% | 226 | 55.9…74.4 |
| `leaf_jockey_horse_fit_score_derived` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_jockey_horse_fit_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_jockey_horse_fit_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_jockey_horse_fit_score_observed` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_jockey_score` | 100.0% | 0.0% | 0.7% | 1455 | 32.7…94.4 |
| `leaf_jockey_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_jockey_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_jockey_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_jockey_score_observed` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_pace_figure_score` | 100.0% | 0.0% | 5.9% | 4713 | 0…100 |
| `leaf_pace_figure_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_pace_figure_score_fallback` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_pace_figure_score_missing` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_pace_figure_score_observed` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_pace_map_score` | 100.0% | 0.0% | 1.6% | 561 | 50.6…64 |
| `leaf_pace_map_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_pace_map_score_fallback` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_pace_map_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_pace_map_score_observed` | 100.0% | 0.0% | 0.0% | 1 | 1…1 |
| `leaf_performance_quality_score` | 100.0% | 0.0% | 0.0% | 3753 | 0…100 |
| `leaf_performance_quality_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_performance_quality_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_performance_quality_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_performance_quality_score_observed` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_rating_score` | 100.0% | 0.0% | 1.8% | 2099 | 47…73.5 |
| `leaf_rating_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_rating_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_rating_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_rating_score_observed` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_sectional_score` | 100.0% | 0.0% | 46.2% | 26 | 60…100 |
| `leaf_sectional_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_sectional_score_fallback` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_sectional_score_missing` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_sectional_score_observed` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_track_score` | 100.0% | 0.0% | 0.0% | 175 | 42.9…86.7 |
| `leaf_track_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_track_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_track_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_track_score_observed` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_trainer_score` | 100.0% | 0.0% | 3.1% | 1901 | 25.2…97.6 |
| `leaf_trainer_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_trainer_score_fallback` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_trainer_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_trainer_score_observed` | 100.0% | 0.0% | 0.0% | 1 | 1…1 |
| `leaf_trial_score` | 100.0% | 0.0% | 29.2% | 35 | 58…100 |
| `leaf_trial_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_trial_score_fallback` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_trial_score_missing` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_trial_score_observed` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_weight_score` | 100.0% | 0.0% | 83.1% | 5 | 53…63 |
| `leaf_weight_score_derived` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_weight_score_fallback` | 100.0% | 0.0% | 0.0% | 1 | 0…0 |
| `leaf_weight_score_missing` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `leaf_weight_score_observed` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `pf_run_count` | 100.0% | 0.0% | 0.0% | 11 | 0…10 |
| `race_distance` | 100.0% | 0.0% | 0.0% | 60 | 800…3.9e+03 |
| `race_type` | 100.0% | 0.0% | 0.0% | 6 | — |
| `rating_missing` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `shape_back_count` | 100.0% | 0.0% | 0.0% | 5 | 0…4 |
| `shape_consensus_count` | 100.0% | 0.0% | 0.0% | 5 | 0…4 |
| `shape_early_work_count` | 100.0% | 0.0% | 0.0% | 2 | 0…1 |
| `shape_entropy` | 100.0% | 0.0% | 0.0% | 4 | 0…3 |
| `shape_front_count` | 100.0% | 0.0% | 0.0% | 5 | 0…4 |
| `shape_inside_count` | 100.0% | 0.0% | 0.0% | 5 | 0…4 |
| `shape_mid_count` | 100.0% | 0.0% | 0.0% | 5 | 0…4 |
| `shape_wide_no_cover_count` | 100.0% | 0.0% | 0.0% | 4 | 0…3 |
| `source_coverage_pct` | 100.0% | 0.0% | 0.0% | 14 | 27.8…100 |
| `surface` | 100.0% | 0.0% | 0.0% | 2 | — |
| `trainer_ly_log_rides` | 100.0% | 0.0% | 0.0% | 770 | 0…7.92 |
| `trial_count` | 100.0% | 0.0% | 0.0% | 19 | 0…18 |
| `trial_top3_count` | 100.0% | 0.0% | 0.0% | 15 | 0…14 |
| `venue` | 100.0% | 0.0% | 0.0% | 31 | — |

## Feature Quality Findings

- Suspicious range/type findings: `{}`
- Constant/dead features in this historical snapshot:
  - `leaf_form_score_derived` = `0`
  - `leaf_form_score_missing` = `0`
  - `leaf_trial_score_derived` = `0`
  - `leaf_trial_score_missing` = `0`
  - `leaf_sectional_score_derived` = `0`
  - `leaf_sectional_score_fallback` = `0`
  - `leaf_pace_map_score_observed` = `1`
  - `leaf_pace_map_score_derived` = `0`
  - `leaf_pace_map_score_fallback` = `0`
  - `leaf_pace_map_score_missing` = `0`
  - `leaf_jockey_score_derived` = `0`
  - `leaf_jockey_score_missing` = `0`
  - `leaf_trainer_score_observed` = `1`
  - `leaf_trainer_score_derived` = `0`
  - `leaf_trainer_score_fallback` = `0`
  - `leaf_trainer_score_missing` = `0`
  - `leaf_jockey_horse_fit_score_observed` = `0`
  - `leaf_jockey_horse_fit_score_missing` = `0`
  - `leaf_class_score_observed` = `0`
  - `leaf_class_score_missing` = `0`
  - `leaf_rating_score_derived` = `0`
  - `leaf_rating_score_missing` = `0`
  - `leaf_weight_score_derived` = `0`
  - `leaf_weight_score_fallback` = `0`
  - `leaf_distance_score_observed` = `0`
  - `leaf_distance_score_missing` = `0`
  - `leaf_track_score_derived` = `0`
  - `leaf_track_score_missing` = `0`
  - `leaf_formline_score_observed` = `0`
  - `leaf_formline_score_missing` = `0`
  - `leaf_consistency_score_observed` = `0`
  - `leaf_consistency_score_missing` = `0`
  - `leaf_performance_quality_score_derived` = `0`
  - `leaf_performance_quality_score_missing` = `0`
  - `leaf_health_score_observed` = `1`
  - `leaf_health_score_derived` = `0`
  - `leaf_health_score_fallback` = `0`
  - `leaf_health_score_missing` = `0`
  - `leaf_confidence_score_observed` = `0`
  - `leaf_confidence_score_derived` = `1`
  - `leaf_confidence_score_fallback` = `0`
  - `leaf_confidence_score_missing` = `0`
  - `leaf_pace_figure_score_derived` = `0`
  - `leaf_pace_figure_score_fallback` = `0`
- Exact duplicate non-constant feature groups:
  - `["days_since_last_run_missing", "leaf_form_score_fallback", "leaf_distance_score_fallback", "leaf_consistency_score_fallback"]`
  - `["leaf_form_score_observed", "leaf_distance_score_derived", "leaf_consistency_score_derived"]`
- Conceptual overlap requiring regularisation/joint interpretation:
  - `rating, leaf_rating_score` — Raw official rating and its engineered 0–100 leaf encode related ability information; regularisation/trees must decide whether both add value.
  - `recent_finish_mean_3, recent_finish_mean_5, recent_finish_best_3, leaf_form_score` — Overlapping recent-form horizons can duplicate the same finishing-position signal.
  - `recent_place_rate_5, recent_win_rate_5, leaf_consistency_score` — Rolling outcomes overlap with the engineered consistency leaf.
  - `pf_l600_delta_avg, pf_race_time_diff_avg, leaf_pace_figure_score` — Raw PF aggregates and the pace-figure leaf are related; importance must be read jointly.
  - `jockey_ly_win_rate, jockey_ly_place_rate, leaf_jockey_score` — Raw jockey rates partly feed the engineered jockey score.
  - `trainer_ly_win_rate, trainer_ly_place_rate, leaf_trainer_score` — Raw trainer rates partly feed the engineered trainer score.

## Known Limitations

- The archive has already been used for prior Rating Matrix optimisation; the final chronological test is new to this ML run but is not globally untouched.
- Stable provider horse/jockey/trainer IDs are unavailable; normalized names are used for joins and names are excluded from ML features.
- The result-aligned snapshot excludes scratchings and does not preserve target-time scratching history.
- Historical body weight and historical place dividends/CLV snapshots are unavailable.
- Some Rating Matrix leaves use documented fallback/default values; evidence-state flags are included so ML can distinguish them.

## Recommended Feature Set

- Raw point-in-time race/horse/history/people/PF/shape features.
- Current 0–100 leaf scores as engineered inputs, paired with observed/derived/fallback/missing flags.
- Low-cardinality race context categories (venue, going, surface, race type, distance and field-size bands).
- Exclude horse/jockey/trainer names, all market fields, result fields, Rating Matrix aggregate score and matrix aggregates from independent challengers.

## Decision

Continue automatically into chronological ML training.
