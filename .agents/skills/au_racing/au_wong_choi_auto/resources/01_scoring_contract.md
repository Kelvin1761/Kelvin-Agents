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

## Frozen Structural Shadow Contract

- `Meeting_Structural_Shadow.csv` is a separate forward-research artefact.
- The frozen shadow may compare `performance_efficiency` and `pairwise_7d_recombine + shape_interaction` against the clean-7D baseline.
- Shadow generation must not write to Logic JSON or alter `ability_score`, `rank_score`, `final_rank_score`, official Top2, official Top3, or official Top4.
- Odds, SP, favourite rank, market movement and market ranking are prohibited shadow inputs.
- Production promotion requires the gate recorded in `resources/structural_shadow_v1.json`; a single positive meeting is insufficient.

## Frozen Dual-Objective Shadow Contract

- `Meeting_Dual_Objective_Shadow.csv` separately records `place_rating`, `coverage_7d`, and `coverage_pf` rankings.
- The checksum-verified model pack is `resources/dual_objective_shadow_v1.joblib`; metadata is recorded in `dual_objective_shadow_v1_model.json`.
- `place_rating` is evaluated primarily on Top2 place strike; `coverage_7d` and `coverage_pf` are evaluated primarily on Top4 placegetter coverage and exact trifecta inclusion.
- Formguide PF parsing may read lines that also contain Flucs text, but no Flucs, odds, SP, favourite or market value is parsed or passed to the model.
- Race Reflector automatically updates `AU_Dual_Objective_Shadow_Tracker.json/md`; rerunning a meeting replaces that batch and must not double count it.
- The promotion gate is `dual_objective_shadow_gate_v1.json`. A pass only creates a human-approval alert for a 50-race canary; it never mutates official scoring automatically.
- During canary, a rolling-50 threshold breach stops the candidate. Official production ranking remains unchanged until a separate approved implementation.
