# HKJC Rating-Interval Gate

- Coverage: {'archive_meetings': 24, 'archive_races': 244, 'archive_runners': 3034, 'archive_rating_history': 2874, 'archive_success_zone': 2153, 'external_races': 9, 'external_success_zone': 78, 'weak_zero_one_races': 181}
- Official local profile rows strictly earlier than each card date; no odds, swaps, or micro tie-breaks.
- Passing candidates: ['NONE']

| candidate | pass | all 0hit Δ | all top2 Δ | all NDCG Δ | holdout top2 Δ | holdout NDCG Δ | weak top2 Δ | external top2 Δ | external NDCG Δ | help/harm | R3 rescues |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| trial_quality_to_stability_0.2 | FAIL | +1 | -1 | +0.0029 | +0 | +0.0070 | +0 | +0 | -0.0049 | 1/2 | 2 |
| trial_quality_to_stability_0.15 | FAIL | +1 | -2 | +0.0015 | +0 | +0.0068 | -1 | +0 | -0.0034 | 0/2 | 1 |
| trial_recency_to_stability_0.075 | FAIL | +1 | -2 | +0.0035 | +0 | +0.0046 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_recency_to_stability_0.15 | FAIL | +1 | -1 | +0.0008 | +0 | +0.0019 | +0 | +0 | -0.0034 | 1/2 | 2 |
| trial_recency_to_stability_0.1 | FAIL | +1 | -2 | +0.0030 | +0 | +0.0046 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_quality_uplift_to_stability_0.2 | FAIL | +1 | -2 | +0.0012 | +0 | +0.0055 | -1 | +0 | -0.0049 | 0/2 | 0 |
| trial_recency_to_stability_0.05 | FAIL | +1 | -2 | +0.0026 | +0 | +0.0021 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_quality_to_stability_0.075 | FAIL | +1 | -2 | +0.0027 | +0 | +0.0035 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_quality_uplift_to_stability_0.15 | FAIL | +1 | -2 | +0.0001 | +0 | +0.0052 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_quality_to_stability_0.1 | FAIL | +1 | -2 | +0.0014 | +0 | +0.0035 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_quality_to_stability_0.05 | FAIL | +1 | -2 | +0.0019 | +0 | +0.0021 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_recency_to_stability_0.2 | FAIL | +1 | -1 | -0.0013 | +0 | +0.0010 | +0 | +0 | -0.0034 | 1/2 | 2 |
| trial_quality_uplift_to_stability_0.05 | FAIL | +1 | -2 | +0.0005 | +0 | +0.0000 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_quality_uplift_to_stability_0.075 | FAIL | +1 | -2 | +0.0005 | +0 | +0.0014 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_quality_uplift_to_stability_0.1 | FAIL | +1 | -2 | -0.0006 | +0 | +0.0014 | -1 | +0 | -0.0034 | 0/2 | 0 |
| trial_quality_to_stability_0.025 | FAIL | +1 | -2 | +0.0012 | +0 | +0.0021 | -1 | +0 | +0.0000 | 0/2 | 0 |
| trial_recency_to_stability_0.025 | FAIL | +1 | -2 | +0.0012 | +0 | +0.0021 | -1 | +0 | +0.0000 | 0/2 | 0 |
| trial_quality_uplift_to_stability_0.025 | FAIL | +1 | -2 | +0.0000 | +0 | +0.0000 | -1 | +0 | +0.0000 | 0/2 | 0 |
