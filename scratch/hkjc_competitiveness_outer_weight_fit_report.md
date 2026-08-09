# HKJC Competitiveness Outer-Weight Fit

- Coverage: 13 meetings / 130 races
- Selected regularization: 0.25
- Recommendation: **HOLD**

| Dimension | Current | Learned | Δ |
|---|---:|---:|---:|
| sectional | 0.1849 | 0.1229 | -0.0620 |
| trainer_signal | 0.2209 | 0.2120 | -0.0089 |
| stability | 0.0919 | 0.1465 | +0.0546 |
| race_shape | 0.2560 | 0.1923 | -0.0637 |
| class_advantage | 0.1335 | 0.1807 | +0.0472 |
| horse_health | 0.0378 | 0.0655 | +0.0277 |
| form_line | 0.0749 | 0.0800 | +0.0051 |

| Slice | 0-hit Δ | Top2 hits Δ | Top3@5 Δ | Competitive recall@5 Δ | NDCG@5 Δ | Winner@5 Δ | MRR Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| development | +2 | -4 | +0.0220 | +0.0284 | -0.0061 | +0.0000 | -0.0218 |
| temporal_holdout | +0 | +0 | +0.0684 | +0.0521 | +0.0234 | +0.0513 | +0.0046 |
| all | +2 | -4 | +0.0359 | +0.0355 | +0.0028 | +0.0154 | -0.0139 |
