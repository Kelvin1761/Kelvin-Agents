# HKJC Rating-Interval Gate

- Coverage: {'archive_meetings': 24, 'archive_races': 244, 'archive_runners': 3034, 'archive_rating_history': 2874, 'archive_success_zone': 2153, 'external_races': 9, 'external_success_zone': 78, 'weak_zero_one_races': 181}
- Official local profile rows strictly earlier than each card date; no odds, swaps, or micro tie-breaks.
- Passing candidates: ['NONE']

| candidate | pass | all 0hit Δ | all top2 Δ | all NDCG Δ | holdout top2 Δ | holdout NDCG Δ | weak top2 Δ | external top2 Δ | external NDCG Δ | help/harm | R3 rescues |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rating_success_zone_0.1 | FAIL | +0 | +1 | +0.0016 | +1 | +0.0045 | +2 | +0 | +0.0022 | 2/1 | 3 |
| rating_success_zone_0.075 | FAIL | +0 | +1 | +0.0021 | +1 | +0.0045 | +2 | +0 | +0.0022 | 2/1 | 3 |
| rating_success_zone_0.15 | FAIL | +1 | +0 | +0.0015 | +1 | +0.0045 | +1 | +0 | -0.0013 | 2/2 | 3 |
| rating_success_zone_0.05 | FAIL | +0 | +1 | +0.0016 | +1 | +0.0042 | +2 | +0 | +0.0000 | 2/1 | 3 |
| rating_success_zone_min2_0.1 | FAIL | +0 | +0 | +0.0008 | +1 | +0.0029 | +2 | +0 | +0.0022 | 2/2 | 3 |
| rating_success_zone_min2_0.125 | FAIL | +0 | -1 | +0.0011 | +1 | +0.0029 | +2 | +0 | -0.0013 | 2/3 | 3 |
| rating_success_zone_0.025 | FAIL | +0 | +0 | +0.0007 | +1 | +0.0031 | +1 | +0 | +0.0000 | 1/1 | 1 |
| rating_success_zone_min2_0.15 | FAIL | +1 | -2 | +0.0003 | +1 | +0.0036 | +1 | +0 | -0.0013 | 2/4 | 3 |
| rating_success_zone_min2_0.075 | FAIL | +0 | +0 | +0.0016 | +0 | +0.0028 | +1 | +0 | +0.0022 | 1/1 | 2 |
| rating_success_zone_min2_0.05 | FAIL | +0 | +0 | +0.0012 | +0 | +0.0025 | +1 | +0 | +0.0000 | 1/1 | 1 |
| rating_success_zone_min3_0.075 | FAIL | +0 | -1 | +0.0009 | +0 | +0.0040 | +0 | +0 | +0.0022 | 0/1 | 1 |
| rating_success_zone_asymmetric_0.075 | FAIL | +0 | -1 | +0.0009 | +0 | +0.0040 | +0 | +0 | +0.0022 | 0/1 | 1 |
| rating_success_zone_uplift_min2_0.125 | FAIL | +0 | +0 | -0.0004 | +0 | +0.0000 | +0 | +0 | +0.0000 | 0/0 | 0 |
| rating_success_zone_uplift_min2_0.15 | FAIL | +0 | +0 | -0.0004 | +0 | +0.0000 | +0 | +0 | +0.0000 | 0/0 | 0 |
| rating_success_zone_uplift_min2_0.05 | FAIL | +0 | +0 | +0.0000 | +0 | +0.0000 | +0 | +0 | +0.0000 | 0/0 | 0 |
| rating_success_zone_uplift_min2_0.075 | FAIL | +0 | +0 | +0.0000 | +0 | +0.0000 | +0 | +0 | +0.0000 | 0/0 | 0 |
| rating_success_zone_uplift_min2_0.1 | FAIL | +0 | +0 | -0.0005 | +0 | +0.0000 | +0 | +0 | +0.0000 | 0/0 | 0 |
| rating_success_zone_min3_0.05 | FAIL | +0 | -1 | +0.0006 | +0 | +0.0025 | +0 | +0 | +0.0000 | 0/1 | 0 |
| rating_success_zone_asymmetric_0.05 | FAIL | +0 | -1 | +0.0006 | +0 | +0.0025 | +0 | +0 | +0.0000 | 0/1 | 0 |
| rating_success_zone_min3_0.125 | FAIL | +0 | -3 | +0.0004 | -1 | +0.0029 | +0 | +0 | +0.0022 | 0/3 | 1 |
| rating_success_zone_asymmetric_0.125 | FAIL | +0 | -3 | +0.0007 | -1 | +0.0029 | +0 | +0 | +0.0022 | 0/3 | 1 |
| rating_success_zone_min3_0.1 | FAIL | +0 | -2 | +0.0001 | -1 | +0.0029 | +0 | +0 | +0.0022 | 0/2 | 1 |
| rating_success_zone_asymmetric_0.1 | FAIL | +0 | -2 | +0.0001 | -1 | +0.0029 | +0 | +0 | +0.0022 | 0/2 | 1 |
| rating_success_zone_min3_0.15 | FAIL | +1 | -4 | -0.0004 | -1 | +0.0036 | -1 | +0 | +0.0022 | 0/4 | 1 |
| rating_success_zone_asymmetric_0.15 | FAIL | +1 | -4 | -0.0002 | -1 | +0.0036 | -1 | +0 | +0.0022 | 0/4 | 1 |
