# HKJC Rating-Interval Gate

- Coverage: {'archive_meetings': 24, 'archive_races': 244, 'archive_runners': 3034, 'archive_rating_history': 2874, 'archive_success_zone': 2153, 'external_races': 9, 'external_success_zone': 78, 'weak_zero_one_races': 181}
- Official local profile rows strictly earlier than each card date; no odds, swaps, or micro tie-breaks.
- Passing candidates: ['NONE']

| candidate | pass | all 0hit Δ | all top2 Δ | all NDCG Δ | holdout top2 Δ | holdout NDCG Δ | weak top2 Δ | external top2 Δ | external NDCG Δ | help/harm | R3 rescues |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bodyweight_recent_stability_to_stability_0.05 | FAIL | +1 | +0 | +0.0022 | +0 | +0.0006 | +0 | +0 | +0.0000 | 1/1 | 1 |
| bodyweight_recent_stability_to_stability_0.075 | FAIL | +1 | +0 | +0.0022 | +0 | +0.0005 | +0 | +0 | +0.0000 | 1/1 | 1 |
| bodyweight_success_zone_to_stability_0.2 | FAIL | +1 | -2 | +0.0030 | +0 | +0.0077 | +0 | +0 | +0.0000 | 1/3 | 2 |
| bodyweight_recent_stability_0.25 | FAIL | +1 | +0 | +0.0024 | +0 | +0.0012 | +0 | +0 | +0.0000 | 1/1 | 1 |
| bodyweight_recent_stability_to_stability_0.1 | FAIL | +1 | -1 | +0.0021 | +0 | +0.0020 | +0 | +1 | +0.0048 | 1/2 | 1 |
| bodyweight_recent_stability_to_stability_0.15 | FAIL | +2 | -4 | +0.0019 | +0 | +0.0023 | -1 | +1 | +0.0048 | 1/5 | 1 |
| bodyweight_success_zone_to_stability_0.15 | FAIL | +1 | -1 | +0.0016 | +0 | +0.0025 | -1 | +0 | +0.0000 | 0/1 | 0 |
| bodyweight_recent_stability_to_stability_0.2 | FAIL | +2 | -4 | +0.0014 | +0 | +0.0027 | -1 | +1 | -0.0087 | 1/5 | 2 |
| bodyweight_recent_stability_to_stability_0.025 | FAIL | +1 | +0 | +0.0014 | +0 | -0.0011 | +0 | +0 | +0.0000 | 1/1 | 1 |
| bodyweight_success_zone_0.25 | FAIL | +0 | +1 | +0.0014 | +0 | -0.0024 | +1 | +0 | -0.0034 | 1/0 | 1 |
| bodyweight_recent_stability_0.15 | FAIL | +0 | +0 | +0.0020 | +0 | +0.0007 | +0 | +0 | +0.0000 | 0/0 | 0 |
| bodyweight_success_zone_0.5 | FAIL | +0 | +3 | +0.0014 | +0 | -0.0013 | +3 | +0 | -0.0034 | 3/0 | 3 |
| bodyweight_success_zone_to_stability_0.075 | FAIL | +1 | -1 | +0.0018 | +0 | -0.0008 | -1 | +0 | +0.0000 | 0/1 | 0 |
| bodyweight_success_zone_to_stability_0.05 | FAIL | +1 | -1 | +0.0018 | +0 | -0.0008 | -1 | +0 | +0.0000 | 0/1 | 0 |
| bodyweight_success_zone_0.15 | FAIL | +0 | +1 | +0.0011 | +0 | -0.0024 | +1 | +0 | -0.0034 | 1/0 | 1 |
| bodyweight_recent_stability_0.1 | FAIL | +0 | +0 | +0.0014 | +0 | -0.0001 | +0 | +0 | +0.0000 | 0/0 | 0 |
| bodyweight_success_zone_0.025 | FAIL | +0 | +0 | +0.0005 | +0 | -0.0001 | +0 | +0 | +0.0000 | 0/0 | 0 |
| bodyweight_success_zone_0.05 | FAIL | +0 | +0 | +0.0005 | +0 | -0.0001 | +0 | +0 | +0.0000 | 0/0 | 0 |
| bodyweight_success_zone_to_stability_0.025 | FAIL | +1 | -1 | +0.0009 | +0 | -0.0001 | -1 | +0 | +0.0000 | 0/1 | 0 |
| bodyweight_success_zone_0.075 | FAIL | +0 | +0 | +0.0003 | +0 | -0.0008 | +0 | +0 | +0.0000 | 0/0 | 0 |
| bodyweight_recent_stability_0.075 | FAIL | +0 | +0 | +0.0005 | +0 | -0.0001 | +0 | +0 | +0.0000 | 0/0 | 0 |
| bodyweight_recent_stability_0.025 | FAIL | +0 | +0 | +0.0005 | +0 | -0.0001 | +0 | +0 | +0.0000 | 0/0 | 0 |
| bodyweight_recent_stability_0.05 | FAIL | +0 | +0 | +0.0005 | +0 | -0.0001 | +0 | +0 | +0.0000 | 0/0 | 0 |
| bodyweight_success_zone_to_stability_0.1 | FAIL | +1 | -1 | -0.0009 | +0 | -0.0008 | -1 | +0 | +0.0000 | 0/1 | 0 |
| bodyweight_success_zone_0.1 | FAIL | +0 | +0 | -0.0009 | +0 | -0.0039 | +0 | +0 | +0.0000 | 0/0 | 0 |
| bodyweight_recent_stability_0.5 | FAIL | +0 | -1 | +0.0008 | -1 | +0.0007 | +1 | +0 | -0.0113 | 2/3 | 2 |
| bodyweight_success_zone_1 | FAIL | +0 | +3 | +0.0001 | -2 | -0.0009 | +5 | +0 | -0.0138 | 6/3 | 7 |
| bodyweight_recent_stability_1 | FAIL | +0 | -4 | -0.0011 | -2 | -0.0040 | +2 | +1 | -0.0367 | 3/7 | 4 |
