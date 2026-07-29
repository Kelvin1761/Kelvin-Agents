# HKJC 初出馬 Matrix 簡化 Gate

- Coverage: 130 races / 26 debut races / 44 debut runners
- Temporal holdout: 39 races；其中 debut 10 races
- Recommendation: **PROMOTE_SHARED_7D**

| Slice | 0-hit Δ | Top3@5 Δ | 全部前三@5 Δ | NDCG@5 Δ | Winner@5 Δ | MRR Δ |
|---|---:|---:|---:|---:|---:|---:|
| all | +0 | +0.0026 | +0.0077 | +0.0048 | +0.0076 | +0.0030 |
| development | +0 | +0.0000 | +0.0000 | +0.0015 | +0.0000 | +0.0007 |
| temporal_holdout | +0 | +0.0085 | +0.0256 | +0.0125 | +0.0256 | +0.0086 |
| debut_all | +0 | +0.0129 | +0.0385 | +0.0242 | +0.0384 | +0.0154 |
| debut_development | +0 | +0.0000 | +0.0000 | +0.0087 | +0.0000 | +0.0041 |
| debut_temporal_holdout | +0 | +0.0333 | +0.1000 | +0.0490 | +0.1000 | +0.0334 |

Shared 7D candidate 只移除 debut outer-weight 特例；初出馬本身嘅 feature neutralisation、試閘、健康及 confidence 邏輯全部保留。
