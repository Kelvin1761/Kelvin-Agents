# AU Wong Choi Auto Validation Rules

- Every horse must contain `python_auto`.
- Every `python_auto` must contain all feature and matrix scores.
- `ability_score` must equal the clean static six-dimension weighted matrix total, plus the gated wet-form feature where applicable.
- `pure_7d_score` / `base_7d_score` are legacy field names for that six-dimension base score.
- Post-matrix modifiers and rank 4-6 watchlist fields are report-only and must not alter `ability_score`, `rank_score`, or `final_rank_score`.
- Rendered reports must not contain `[FILL]`, `PLACEHOLDER`, or generic stock phrases.
