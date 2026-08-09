# HKJC Rich Production Matrix Gate

- Sources: `scratch/hkjc_ranking_dataset_current.csv`, `scratch/hkjc_ranking_dataset_2026_07_15_current.csv`
- Coverage: 25 meetings / 245 races / 3054 runners
- Recommendation: **PROMOTE_PASSING**

| Candidate | Pass | 0-hit Δ | Top2 hits Δ | Top3@5 Δ | Competitive recall@5 Δ | NDCG@5 Δ | Winner@5 Δ | MRR Δ | Adjusted 0-hit Δ | Adjusted Top2 Δ | Adjusted NDCG Δ | Help/Harm |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| class_v2_replace | FAIL | +1 | -7 | -0.0163 | -0.0032 | -0.0064 | +0.0041 | +0.0032 | -2 | -5 | -0.0050 | 17/24 |
| class_v2_blend | FAIL | +2 | -3 | -0.0095 | +0.0021 | -0.0020 | -0.0082 | +0.0088 | +0 | -2 | +0.0044 | 7/10 |
| class_v2_confirmed_boost_08 | FAIL | +2 | +0 | +0.0014 | +0.0020 | +0.0009 | +0.0082 | -0.0048 | +1 | +1 | +0.0044 | 4/4 |
| class_v2_confirmed_boost_10 | FAIL | +2 | +0 | +0.0000 | +0.0004 | +0.0014 | +0.0082 | -0.0025 | +1 | +1 | +0.0058 | 5/5 |
| formline_to_trainer | FAIL | +1 | +1 | -0.0109 | -0.0075 | -0.0036 | -0.0041 | +0.0009 | +0 | +2 | -0.0001 | 9/8 |
| formline_to_core | FAIL | +1 | +2 | -0.0163 | -0.0101 | -0.0060 | -0.0082 | -0.0006 | +1 | +2 | -0.0039 | 8/6 |
| shape_to_core_01 | FAIL | -1 | +2 | -0.0041 | -0.0033 | +0.0021 | +0.0000 | +0.0051 | +0 | +1 | +0.0028 | 3/1 |
| shape_to_core_02 | FAIL | -1 | +3 | -0.0054 | -0.0033 | +0.0035 | +0.0041 | +0.0076 | +0 | +2 | +0.0072 | 5/2 |
| shape_to_core | FAIL | -1 | +4 | -0.0014 | -0.0012 | +0.0050 | +0.0122 | +0.0066 | +0 | +2 | +0.0074 | 7/3 |
| shape_to_core_equal | PASS | -2 | +5 | +0.0014 | +0.0006 | +0.0041 | +0.0122 | +0.0019 | -1 | +3 | +0.0071 | 8/3 |
| shape_to_core_stability_led | FAIL | +0 | +6 | +0.0014 | +0.0006 | +0.0041 | +0.0122 | +0.0019 | +1 | +5 | +0.0053 | 11/5 |
| shape_to_trainer_stability | FAIL | -2 | +4 | -0.0014 | -0.0010 | +0.0047 | +0.0122 | +0.0069 | -1 | +3 | +0.0081 | 7/3 |
| formline_shape_to_core | FAIL | +0 | +3 | -0.0095 | -0.0065 | -0.0043 | -0.0122 | +0.0008 | +0 | +3 | -0.0022 | 11/8 |
| class_v2_blend_formline_to_core | FAIL | +0 | -4 | -0.0068 | -0.0026 | +0.0030 | -0.0041 | +0.0103 | -3 | -1 | +0.0095 | 8/12 |

## Matrix competitive-tier AUC

- sectional: 0.586
- trainer_signal: 0.608
- stability: 0.674
- race_shape: 0.571
- class_advantage: 0.613
- horse_health: 0.505
- form_line: 0.515
