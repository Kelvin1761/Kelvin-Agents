# AU Wong Choi Auto Scoring Contract

- 7D matrix:
  - `stability`
  - `sectional`
  - `race_shape`
  - `jockey_trainer`
  - `class_weight`
  - `track`
  - `form_line`
- Output namespace per horse:
  - `python_auto.pure_7d_score`
  - `python_auto.final_rank_score`
  - `python_auto.ability_score`
  - `python_auto.adjustment_breakdown`
  - `python_auto.grade`
  - `python_auto.feature_scores`
  - `python_auto.matrix_scores`
  - `python_auto.matrix`
  - `python_auto.matrix_reasoning`
  - `python_auto.core_logic`
  - `python_auto.advantages`
  - `python_auto.disadvantages`
  - `python_auto.score_provenance`

## Clean 7D Ranking Contract

- Official ranking uses the static 7D weighted score only:
  - `ability_score = pure_7d_score = final_rank_score`
  - `base_7d_score` is the same clean official 7D score.
- Dynamic weights, soft race-shape, wetproof cap, barrier bias, diversity bonus, place tightening, market-free rank adjustment, odds/flucs, timing, excuse/run-shape and gear evidence are report-only unless a future full-history ablation explicitly promotes them.
- `adjustment_breakdown` may include legacy/report-only simulated values for audit, but those values must not alter `ability_score`, `rank_score`, `final_rank_score`, Top2, Top3, or Top4.
- Rank 4-6 danger watchlist is report-only. It can surface context such as near-Top3 score gap, stability, class/weight, jockey/trainer/trial support, distance fit, timing, excuse/run-shape, gear and market background, but it must not rerank horses.
- This mirrors the useful HKJC auto pattern: feature evidence can be rich, sourced and explainable, but final ranking remains one clean matrix score.
