# HKJC Next Pre-Race Signal Gate

- Coverage: {'archive_meetings': 24, 'archive_races': 244, 'archive_runners': 3034, 'external_races': 9, 'weak_zero_one_races': 180, 'finish_time_runners': 1825, 'last_margin_runners': 1784, 'walkforward_strength_runners': 1893, 'external_walkforward_strength_runners': 103}
- Baseline includes the promoted 5% exact class/course/distance normalized sectional blend.
- Frozen pre-race inputs only; full-field matrix rerank; no odds, swaps, or micro tie-breaks.
- Passing candidates: ['NONE']

| candidate | pass | all 0hit Δ | all top2 Δ | all NDCG Δ | holdout top2 Δ | holdout NDCG Δ | weak top2 Δ | external NDCG Δ | help/harm | R3 rescues |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| finish_time_to_sectional_0.025 | FAIL | +0 | +1 | -0.0001 | +1 | -0.0001 | +1 | -0.0113 | 1/0 | 1 |
| strength_residual_min2_to_formline_0.075 | FAIL | +0 | +0 | -0.0001 | +0 | +0.0012 | +0 | -0.0013 | 0/0 | 0 |
| expectation_residual_min2_to_formline_0.075 | FAIL | +0 | +0 | -0.0004 | +0 | +0.0012 | +0 | -0.0013 | 0/0 | 0 |
| race_strength_to_formline_0.05 | FAIL | +0 | +1 | +0.0006 | +0 | -0.0004 | +1 | +0.0022 | 1/0 | 1 |
| cold_ceiling_to_sectional_0.05 | FAIL | +0 | +0 | +0.0002 | +0 | +0.0007 | +0 | +0.0000 | 0/0 | 0 |
| cold_ceiling_to_stability_0.10 | FAIL | +0 | +0 | +0.0002 | +0 | +0.0007 | +0 | +0.0000 | 0/0 | 0 |
| cold_ceiling_to_sectional_0.08 | FAIL | +0 | +0 | -0.0009 | +0 | +0.0007 | +0 | +0.0000 | 0/0 | 0 |
| cold_ceiling_to_sectional_0.03 | FAIL | +0 | +0 | +0.0002 | +0 | +0.0005 | +0 | +0.0000 | 0/0 | 0 |
| cold_ceiling_to_stability_0.05 | FAIL | +0 | +0 | +0.0002 | +0 | +0.0005 | +0 | +0.0000 | 0/0 | 0 |
| cold_ceiling_to_stability_0.08 | FAIL | +0 | +0 | +0.0002 | +0 | +0.0005 | +0 | +0.0000 | 0/0 | 0 |
| speed_time_consensus_to_sectional_0.025 | FAIL | +0 | +0 | +0.0007 | +0 | +0.0005 | +0 | -0.0113 | 0/0 | 0 |
| cold_ceiling_to_stability_0.03 | FAIL | +0 | +0 | +0.0002 | +0 | +0.0005 | +0 | +0.0000 | 0/0 | 0 |
| expectation_residual_min2_to_formline_0.05 | FAIL | +0 | +0 | -0.0006 | +0 | +0.0001 | +0 | +0.0022 | 0/0 | 0 |
| strength_residual_min2_to_formline_0.05 | FAIL | +0 | +0 | -0.0006 | +0 | +0.0001 | +0 | +0.0022 | 0/0 | 0 |
| strength_residual_to_formline_0.05 | FAIL | +0 | +1 | +0.0005 | +0 | -0.0008 | +1 | +0.0022 | 1/0 | 1 |
| strength_residual_to_formline_0.075 | FAIL | +0 | +1 | +0.0003 | +0 | -0.0011 | +1 | +0.0022 | 1/0 | 1 |
| cold_ceiling_to_sectional_0.10 | FAIL | +0 | +0 | -0.0010 | +0 | +0.0004 | +0 | +0.0000 | 0/0 | 0 |
| race_strength_min2_to_formline_0.05 | FAIL | +0 | +0 | +0.0003 | +0 | -0.0004 | +0 | +0.0022 | 0/0 | 0 |
| race_strength_to_formline_0.075 | FAIL | +0 | +1 | +0.0003 | +0 | -0.0013 | +1 | +0.0022 | 1/0 | 1 |
| strength_residual_to_formline_0.025 | FAIL | +0 | +0 | +0.0005 | +0 | +0.0001 | +0 | +0.0022 | 0/0 | 0 |
| race_strength_to_formline_0.025 | FAIL | +0 | +0 | +0.0004 | +0 | -0.0001 | +0 | +0.0022 | 0/0 | 0 |
| opponent_quality_to_formline_0.05 | FAIL | +0 | -2 | -0.0016 | +0 | -0.0002 | +0 | +0.0000 | 0/2 | 0 |
| strength_residual_to_formline_0.1 | FAIL | +0 | +1 | +0.0002 | +0 | -0.0010 | +1 | +0.0022 | 1/0 | 1 |
| strength_residual_min2_to_formline_0.1 | FAIL | +0 | +0 | -0.0007 | +0 | +0.0003 | +0 | -0.0013 | 0/0 | 0 |
| race_strength_to_formline_0.1 | FAIL | +0 | +1 | +0.0002 | +0 | -0.0010 | +1 | -0.0280 | 1/0 | 1 |
| race_strength_min2_to_formline_0.1 | FAIL | +0 | +0 | -0.0007 | +0 | +0.0002 | +0 | -0.0315 | 0/0 | 0 |
| expectation_residual_to_formline_0.1 | FAIL | +0 | +2 | -0.0009 | +0 | -0.0025 | +2 | -0.0013 | 2/0 | 3 |
| expectation_residual_to_formline_0.075 | FAIL | +0 | +1 | +0.0001 | +0 | -0.0011 | +1 | +0.0022 | 1/0 | 1 |
| expectation_residual_min2_to_formline_0.1 | FAIL | +0 | +1 | -0.0009 | +0 | -0.0015 | +1 | -0.0013 | 1/0 | 1 |
| expectation_residual_to_formline_0.025 | FAIL | +0 | +0 | +0.0002 | +0 | -0.0008 | +0 | +0.0022 | 0/0 | 0 |
| expectation_residual_to_formline_0.05 | FAIL | +0 | +0 | +0.0002 | +0 | -0.0008 | +0 | +0.0022 | 0/0 | 0 |
| opponent_quality_to_formline_0.03 | FAIL | +0 | -1 | -0.0004 | +0 | -0.0002 | +0 | +0.0000 | 0/1 | 0 |
| race_strength_positive_to_formline_0.1 | FAIL | +0 | -1 | -0.0009 | +0 | +0.0005 | +0 | +0.0022 | 0/1 | 0 |
| race_strength_positive_to_formline_0.075 | FAIL | +0 | -1 | -0.0009 | +0 | +0.0005 | +0 | +0.0022 | 0/1 | 0 |
| race_strength_positive_to_formline_0.05 | FAIL | +0 | -1 | -0.0010 | +0 | +0.0000 | +0 | +0.0022 | 0/1 | 0 |
| expectation_residual_positive_to_formline_0.05 | FAIL | +0 | -1 | -0.0010 | +0 | +0.0000 | +0 | +0.0022 | 0/1 | 0 |
| strength_residual_positive_to_formline_0.05 | FAIL | +0 | -1 | -0.0010 | +0 | +0.0000 | +0 | +0.0022 | 0/1 | 0 |
| strength_residual_positive_to_formline_0.075 | FAIL | +0 | -1 | -0.0011 | +0 | +0.0000 | +0 | +0.0022 | 0/1 | 0 |
| strength_residual_positive_to_formline_0.1 | FAIL | +0 | -1 | -0.0011 | +0 | +0.0000 | +0 | +0.0022 | 0/1 | 0 |
| race_strength_min2_to_formline_0.075 | FAIL | +0 | +0 | -0.0017 | +0 | -0.0035 | +0 | -0.0013 | 0/0 | 0 |
| expectation_residual_positive_to_formline_0.1 | FAIL | +0 | -1 | -0.0013 | +0 | -0.0009 | +0 | +0.0022 | 0/1 | 0 |
| expectation_residual_positive_to_formline_0.075 | FAIL | +0 | -1 | -0.0014 | +0 | -0.0009 | +0 | +0.0022 | 0/1 | 0 |
| finish_time_to_sectional_0.1 | FAIL | +0 | +1 | -0.0018 | +0 | -0.0005 | +3 | -0.0395 | 4/3 | 3 |
| finish_time_to_sectional_0.05 | FAIL | +0 | +0 | -0.0024 | +0 | -0.0047 | +1 | -0.0093 | 1/1 | 1 |
| speed_time_consensus_to_sectional_0.05 | FAIL | +0 | -1 | +0.0013 | -1 | +0.0022 | +0 | -0.0113 | 0/1 | 0 |
| speed_time_consensus_to_sectional_0.1 | FAIL | +0 | -1 | -0.0003 | -1 | +0.0013 | +1 | -0.0120 | 1/2 | 1 |
| speed_time_consensus_to_sectional_0.075 | FAIL | +0 | -2 | +0.0002 | -2 | +0.0011 | +0 | -0.0093 | 0/2 | 0 |
| finish_time_to_sectional_0.075 | FAIL | +1 | -2 | -0.0018 | -2 | -0.0028 | +0 | -0.0093 | 1/3 | 1 |