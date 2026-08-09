# HKJC Full-Archive Competitiveness Calibration

- Coverage: 25 meetings / 245 races / 3054 runners
- Selected regularization: 0.5
- Recommendation: **HOLD**

| Feature | Weight |
|---|---:|
| published_prior | 0.6940 |
| stability | 0.0742 |
| trainer_signal | 0.0516 |
| class_rating_experience | 0.0289 |
| speed_engine | 0.0708 |
| recent_mean_finish | 0.0804 |

| Slice | 0-hit Δ | Top2 hits Δ | Top3@5 Δ | Competitive recall@5 Δ | NDCG@5 Δ | Winner@5 Δ | MRR Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| archive_development | +0 | +0 | +0.0000 | +0.0028 | +0.0047 | +0.0000 | +0.0032 |
| archive_temporal_holdout | +0 | +0 | +0.0256 | -0.0077 | +0.0009 | +0.0000 | -0.0066 |
| independent_recent | -2 | +2 | +0.0061 | +0.0064 | +0.0039 | +0.0092 | -0.0033 |
| external_2026_07_15 | +0 | -1 | +0.0000 | +0.0000 | -0.0191 | +0.0000 | -0.0556 |
| all | -2 | +1 | +0.0068 | +0.0027 | +0.0028 | +0.0041 | -0.0034 |
