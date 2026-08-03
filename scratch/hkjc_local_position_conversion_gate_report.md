# HKJC Local Position-Conversion Gate

- Coverage: {'archive_meetings': 24, 'archive_races': 244, 'archive_runners': 3034, 'position_runners': 2897, 'position_samples': 15328, 'external_races': 9, 'external_position_runners': 103, 'weak_zero_one_races': 181}
- Official local horse-profile positions only; strict pre-race cutoff.
- Full-field matrix rerank; no odds, swaps, or micro tie-breaks.
- Passing candidates: ['NONE']

| candidate | pass | all 0hit Δ | all top2 Δ | adjusted NDCG Δ | holdout top2 Δ | holdout NDCG Δ | weak top2 Δ | external NDCG Δ | help/harm | R3 rescues |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sustainable_to_race_shape_0.05 | FAIL | +1 | +5 | +0.0041 | +3 | +0.0004 | +5 | -0.0302 | 6/1 | 6 |
| conversion_to_race_shape_0.05 | FAIL | +2 | +2 | +0.0008 | +3 | -0.0012 | +4 | -0.0282 | 6/4 | 7 |
| conversion_to_race_shape_0.075 | FAIL | +1 | +3 | -0.0012 | +3 | -0.0021 | +5 | -0.0275 | 7/4 | 8 |
| sustainable_to_race_shape_0.025 | FAIL | +1 | +2 | +0.0019 | +2 | -0.0027 | +2 | +0.0000 | 3/1 | 3 |
| hidden_close_to_race_shape_0.025 | FAIL | +1 | +1 | +0.0014 | +2 | +0.0004 | +1 | +0.0000 | 2/1 | 3 |
| hidden_close_to_race_shape_0.05 | FAIL | +1 | -1 | +0.0010 | +2 | -0.0012 | +1 | +0.0000 | 2/3 | 3 |
| hidden_close_to_race_shape_0.075 | FAIL | +1 | -1 | -0.0004 | +2 | -0.0013 | +1 | -0.0087 | 2/3 | 3 |
| conversion_to_race_shape_0.025 | FAIL | +1 | +0 | -0.0007 | +2 | -0.0006 | +2 | +0.0000 | 3/3 | 3 |
| conversion_to_race_shape_0.1 | FAIL | -2 | +5 | -0.0013 | +2 | -0.0025 | +8 | -0.0275 | 10/5 | 12 |
| sustainable_to_race_shape_0.075 | FAIL | +1 | +3 | +0.0047 | +1 | -0.0018 | +5 | -0.0302 | 8/5 | 9 |
| gain_to_race_shape_0.05 | FAIL | +2 | +0 | +0.0017 | +1 | +0.0014 | +2 | +0.0006 | 4/4 | 5 |
| hidden_close_to_race_shape_0.1 | FAIL | +1 | -2 | +0.0007 | +1 | -0.0009 | +1 | -0.0087 | 2/4 | 3 |
| gain_to_race_shape_0.025 | FAIL | +1 | -1 | +0.0004 | +1 | +0.0022 | +1 | +0.0000 | 2/3 | 3 |
| conversion_to_formline_0.05 | FAIL | +1 | +0 | -0.0007 | +1 | -0.0013 | +0 | -0.0034 | 1/1 | 1 |
| conversion_to_formline_0.1 | FAIL | +1 | +1 | -0.0014 | +1 | -0.0006 | +2 | -0.0034 | 3/2 | 3 |
| conversion_to_formline_0.025 | FAIL | +0 | +1 | -0.0014 | +1 | +0.0002 | +1 | +0.0000 | 1/0 | 1 |
| conversion_to_formline_0.075 | FAIL | +1 | +1 | -0.0017 | +1 | -0.0011 | +2 | -0.0034 | 3/2 | 3 |
| sustainable_formline_confirmed_uplift_0.075 | FAIL | +1 | -1 | +0.0044 | +0 | +0.0030 | -1 | +0.0000 | 0/1 | 0 |
| sustainable_to_race_shape_0.1 | FAIL | +0 | +3 | +0.0038 | +0 | -0.0009 | +6 | -0.0302 | 9/6 | 11 |
| conversion_formline_confirmed_uplift_0.075 | FAIL | +1 | -1 | +0.0015 | +0 | +0.0014 | -1 | +0.0000 | 0/1 | 1 |
| sustainable_formline_confirmed_uplift_0.025 | FAIL | +0 | +0 | +0.0007 | +0 | +0.0000 | +0 | +0.0000 | 0/0 | 0 |
| conversion_formline_confirmed_uplift_0.015 | FAIL | +0 | +0 | +0.0003 | +0 | +0.0000 | +0 | +0.0000 | 0/0 | 0 |
| gain_to_race_shape_0.075 | FAIL | +1 | +0 | +0.0002 | +0 | -0.0018 | +4 | -0.0307 | 6/6 | 8 |
| sustainable_formline_confirmed_uplift_0.015 | FAIL | +0 | +0 | +0.0002 | +0 | +0.0000 | +0 | +0.0000 | 0/0 | 0 |
| gain_formline_confirmed_uplift_0.015 | FAIL | +0 | +0 | +0.0001 | +0 | +0.0000 | +0 | +0.0000 | 0/0 | 0 |
| gain_to_race_shape_0.1 | FAIL | +0 | +1 | +0.0001 | +0 | -0.0021 | +5 | -0.0609 | 7/6 | 9 |
| hidden_close_formline_confirmed_uplift_0.015 | FAIL | +0 | +0 | +0.0000 | +0 | +0.0000 | +0 | +0.0000 | 0/0 | 0 |
| conversion_formline_confirmed_uplift_0.025 | FAIL | +0 | +0 | -0.0000 | +0 | -0.0015 | +0 | +0.0000 | 0/0 | 0 |
| hidden_close_formline_confirmed_uplift_0.025 | FAIL | +0 | +0 | -0.0001 | +0 | +0.0000 | +0 | +0.0000 | 0/0 | 1 |
| sustainable_formline_confirmed_uplift_0.04 | FAIL | +0 | +0 | -0.0001 | +0 | +0.0000 | +0 | +0.0000 | 0/0 | 0 |
| sustainable_formline_confirmed_uplift_0.05 | FAIL | +0 | +0 | -0.0001 | +0 | -0.0002 | +0 | +0.0000 | 0/0 | 0 |
| conversion_formline_confirmed_uplift_0.04 | FAIL | +1 | -1 | -0.0001 | +0 | -0.0015 | -1 | +0.0000 | 0/1 | 1 |
| conversion_formline_confirmed_uplift_0.05 | FAIL | +1 | -1 | -0.0002 | +0 | -0.0017 | -1 | +0.0000 | 0/1 | 1 |
| gain_formline_confirmed_uplift_0.025 | FAIL | +0 | +0 | -0.0007 | +0 | -0.0015 | +0 | +0.0000 | 0/0 | 1 |
| gain_formline_confirmed_uplift_0.04 | FAIL | +0 | +0 | -0.0007 | +0 | -0.0015 | +0 | +0.0000 | 0/0 | 1 |
| hidden_close_formline_confirmed_uplift_0.04 | FAIL | +0 | +0 | -0.0008 | +0 | -0.0015 | +0 | +0.0000 | 0/0 | 1 |
| hidden_close_formline_confirmed_uplift_0.05 | FAIL | +0 | +0 | -0.0008 | +0 | -0.0015 | +0 | +0.0000 | 0/0 | 1 |
| hidden_close_formline_confirmed_uplift_0.075 | FAIL | +0 | +0 | -0.0008 | +0 | -0.0016 | +0 | +0.0000 | 0/0 | 1 |
| gain_formline_confirmed_uplift_0.05 | FAIL | +1 | -1 | -0.0009 | +0 | -0.0018 | -1 | +0.0000 | 0/1 | 1 |
| gain_formline_confirmed_uplift_0.075 | FAIL | +1 | -1 | -0.0009 | +0 | -0.0017 | -1 | +0.0000 | 0/1 | 1 |