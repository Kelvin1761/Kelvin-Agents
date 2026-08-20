# HKJC Auto Scoring Contract

## Official Matrix

Auto uses the versioned 7D Wong Choi matrix as the only official ability
source. Standard runners and debut runners have separate locked outer-weight
sets; both are persisted in `python_auto_run_contract`.

| Key | Display | Weight |
|---|---:|---:|
| `sectional` | 段速 | 0.1285 |
| `trainer_signal` | 騎練訊號 | 0.2362 |
| `stability` | 狀態與穩定性 | 0.0983 |
| `race_shape` | 檔位與走位（不含步速） | 0.2737 |
| `class_advantage` | 級數優勢 | 0.1428 |
| `horse_health` | 馬匹健康 / 新鮮感 | 0.0404 |
| `form_line` | 賽績線 | 0.0801 |

Debut runners use this separate locked formula:

| Key | Weight |
|---|---:|
| `trainer_signal` | 0.30 |
| `horse_health` | 0.30 |
| `race_shape` | 0.20 |
| `stability` | 0.15 |
| `class_advantage` | 0.05 |
| `sectional` | 0.00 |
| `form_line` | 0.00 |

## Matrix Mapping Calibration

- `sectional` uses `speed_score` 100%. `track_going_score` remains in the public 12-score audit layer but is not used by the current Matrix because the available HKJC going input had near-constant/no useful ranking signal.
- `race_shape` remains the primary venue/position conversion dimension. It uses `race_shape_context_score` 100% (with neutral-safe `draw_score` fallback only when the context score is unavailable); distance and carried weight must not be displayed under this dimension.
- `form_line` uses `formline_strength_score` 100%. `margin_trend_score` was removed from this dimension after the 2026-07-08 backtest because it duplicated per-run margin credit already represented in stability. Same-distance evidence belongs to distance suitability, not the race-line dimension.
- `class_advantage` uses class/ratings and weight conversion: `class_score` 75%, `weight_score` 25%. Distance evidence must not be displayed under class advantage.
- `stability` uses `form_score` 50%, `consistency_score` 40%, `trackwork_trend_score` 10%. `trackwork_trend_score` is a derived readiness signal from `trackwork_digest`, so trackwork momentum lives with state/stability rather than sectional speed.
- `trainer_signal` uses `jockey_score` 55% and `trainer_score` 45%; `confidence_score` is a data reliability signal, not a positive trainer/jockey edge.
- Jockey and trainer scorers use materialized two-season master statistics for continuous ratings on live/current or future meetings. Historical/archive scoring must receive a matching `point_in_time` ratings/prior object built from results strictly before the meeting date; otherwise the engine neutralizes the aggregate source and uses the tier/neutral fallback. This prevents full-season jockey/trainer, combination and distance statistics from leaking future results into replay. `resources/05_jockey_trainer_tiers.json` remains the fallback for known names; fully unknown names remain neutral 60.
- `horse_health` uses `risk_score` 61.1% and `weight_score` 38.9%. `confidence_score` remains display/audit information and does not create a health advantage.
- Archived normalized-sectional and older 65/35 going blends are research history only. They must not be described as current production scoring.

## Feature Scores

Each horse must have these 12 scores, all clipped to 0-100:

`form_score`, `speed_score`, `class_score`, `jockey_score`, `trainer_score`, `draw_score`, `distance_score`, `track_going_score`, `weight_score`, `consistency_score`, `risk_score`, `confidence_score`.

Derived matrix-only support signals such as `formline_strength_score`,
`margin_trend_score`, `same_distance_signal_score`, `trackwork_trend_score`,
and `race_shape_context_score` may appear inside matrix reasoning/components
without expanding the 12-score public feature list.

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

Grade is display-only. Ranking and Top 4 use numeric `ability_score`.

## Pick Status

- `MODEL_TOP_PICK`: rank <= 2, ability >= 70, confidence >= 55
- `WATCH`: ability >= 70 but rank/confidence gate blocks top-pick status
- `NO_PICK`: all other horses
