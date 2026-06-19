# AU Wong Choi Auto Validation Rules

- Every horse must contain `python_auto`.
- Every `python_auto` must contain all feature and matrix scores.
- `ability_score` must equal the clean static 7D weighted matrix total.
- Post-7D modifiers and rank 4-6 watchlist fields are report-only and must not alter `ability_score`, `rank_score`, or `final_rank_score`.
- Rendered reports must not contain `[FILL]`, `PLACEHOLDER`, or generic stock phrases.
