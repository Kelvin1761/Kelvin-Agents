# HKJC Auto Scoring Contract

## Official Matrix

Auto uses the existing 7D Wong Choi matrix as the only official 0-100 ability
and Grade source. Official ordering uses the full-field ranking contract below.

All runners, including debut runners, use the same official outer weights.
Debut uncertainty and trial/readiness evidence are handled inside the feature
scores; there is no separate debut-only outer-weight formula.

| Key | Display | Weight |
|---|---:|---:|
| `sectional` | 段速與場地適性 | 0.1849 |
| `trainer_signal` | 騎練訊號 | 0.2309 |
| `stability` | 狀態與穩定性 | 0.1019 |
| `race_shape` | 檔位與走位（不含步速） | 0.2260 |
| `class_advantage` | 級數優勢 | 0.1435 |
| `horse_health` | 馬匹健康 / 新鮮感 | 0.0378 |
| `form_line` | 賽績線 | 0.0749 |

## Matrix Mapping Calibration

- `sectional` first maps `speed_score` 65% and `track_going_score` 35%, then—only when exact course/distance/class reference evidence exists—blends 5% of the full-field normalized sectional score. The normalized score combines L400 60% and total-time delta 40%, is recency-weighted, and shrinks by sample count. Missing evidence leaves the original dimension unchanged.
- `race_shape` remains the primary venue/position conversion dimension. It uses `race_shape_context_score` 100% (with neutral-safe `draw_score` fallback only when the context score is unavailable); distance and carried weight must not be displayed under this dimension.
- `form_line` uses `formline_strength_score` 100%. `margin_trend_score` was removed from this dimension after the 2026-07-08 backtest because it duplicated per-run margin credit already represented in stability. Same-distance evidence belongs to distance suitability, not the race-line dimension.
- `class_advantage` uses class/ratings and weight conversion: `class_score` 75%, `weight_score` 25%. Distance evidence must not be displayed under class advantage.
- `stability` uses `form_score` 50%, `consistency_score` 40%, `trackwork_trend_score` 10%. `trackwork_trend_score` is a derived readiness signal from `trackwork_digest`, so trackwork momentum lives with state/stability rather than sectional speed.
- `trainer_signal` uses `jockey_score` 55% and `trainer_score` 45%; `confidence_score` is a data reliability signal, not a positive trainer/jockey edge.
- Jockey and trainer scorers use materialized two-season master statistics for continuous ratings on live/current or future meetings. Historical/archive scoring must receive a matching `point_in_time` ratings/prior object built from results strictly before the meeting date; otherwise the engine neutralizes the aggregate source and uses the tier/neutral fallback. This prevents full-season jockey/trainer, combination and distance statistics from leaking future results into replay. `resources/05_jockey_trainer_tiers.json` remains the fallback for known names; fully unknown names remain neutral 60.
- `horse_health` uses `risk_score` 55%, `weight_score` 35%, and `confidence_score` 10%. Confidence therefore remains a low-weight reliability support signal.
- 2026-07-30 full-archive gate（25 meetings／245 valid races）將 `race_shape` 減 0.03，平均分配予 `trainer_signal`、`stability`、`class_advantage` 各 0.01。改動以全場矩陣重排驗證，並非 Top2/Top3 邊界 swap；Top2 hits、Top3@5、competitive recall、NDCG@5、Winner@5 及 MRR 全部整體上升。
- 2026-08-01 high-quality data gate（24 meetings／244 races；另加 2026-07-15 獨立日）只正式採用 5% 班程標準化段速 blend：全 archive Top2 +1、holdout Top2 +1、0/1-hit 弱場 Top2 +1、help/harm 1/0、獨立日全指標不變。15% 評分高位候選因獨立日 NDCG / Winner@5 明顯倒退而否決，評分歷史只保留作結構化 context / shadow research。

## Feature Scores

Each horse must have these 12 scores, all clipped to 0-100:

`form_score`, `speed_score`, `class_score`, `jockey_score`, `trainer_score`, `draw_score`, `distance_score`, `track_going_score`, `weight_score`, `consistency_score`, `risk_score`, `confidence_score`.

Derived matrix-only support signals such as `formline_strength_score`, `margin_trend_score`, `same_distance_signal_score`, and `trackwork_trend_score` may appear inside matrix reasoning/components without expanding the 12-score public feature list.

`track_going_score` must not treat generic draw/bias hit-rate text (`上名率`) as automatic going support. It can reward explicit positive verdicts such as `✅有利` or a non-empty same-course-distance record, and it can penalize explicit adverse/weak records.

## Grade

- `S+`: 96+
- `S`: 92-95.99
- `S-`: 88-91.99
- `A+`: 84-87.99
- `A`: 80-83.99
- `A-`: 76-79.99
- `B+`: 72-75.99
- `B`: 68-71.99
- `B-`: 64-67.99
- `C+`: 60-63.99
- `C`: 56-59.99
- `C-`: 52-55.99
- `D`: 48-51.99
- `E`: below 48

Grade is display-only. Ranking and Top 4 use the full-field `rank_score` below;
`ability_score` remains the explainable Matrix total.

## Full-field Ranking Contract

- Version: `HKJC_MATRIX_ANCHORED_LAMBDARANK_V1`
- Ranking score: 70% Matrix within-race rank percentile + 30% LambdaRank within-race rank percentile；只用極微 Matrix ability epsilon 解決完全同分
- ML inputs: seven absolute Matrix dimensions plus the same seven within-race z-scores
- `ability_score` and Grade remain unchanged Matrix outputs
- Official rank, Top 2, Top 4 and `model_pick_status` follow `rank_score`
- No odds, market, horse identity, post-race result, incident field, manual swap or micro tie-break
- Model artifact is checksum-pinned and fails closed if missing or incompatible
- `--matrix-only` restores legacy Matrix-only ordering for emergency rollback

Promotion decision: the 161-race chronological walk-forward reduced 0-hit
25.47%→24.22%, reduced 1-hit 52.17%→50.31%, raised Winner Top 2
41.61%→42.86%, kept Winner Top 3 unchanged, and moved ten eventual
placegetters from model Rank 3 into Top 2. The nine-race 2026-07-15 block lost
one Top-3-at-5 capture but raised Winner Top 3 from 3/9 to 5/9 and improved
log-loss; the user approved promotion after reviewing this sample-size trade-off.

## Stability Residual Research Shadow

`--stability-residual-shadow` is an explicit opt-in research monitor. It loads
the checksum-pinned `HKJC_STABILITY_RESIDUAL_SHADOW_V1` artifact only after
mainline Auto scoring succeeds and writes separate CSV/JSON diagnostics. Its
probability/rank is not an official ability source and must not alter Matrix
scores, `ability_score`, Grade, Top 4, verdict, pick status or betting advice.

## Pick Status

- `MODEL_TOP_PICK`: rank <= 2, ability >= 70, confidence >= 55
- `WATCH`: ability >= 70 but rank/confidence gate blocks top-pick status
- `NO_PICK`: all other horses
