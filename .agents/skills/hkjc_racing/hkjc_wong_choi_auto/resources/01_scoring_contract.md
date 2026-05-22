# HKJC Auto Scoring Contract

## Official Matrix

Auto uses the existing 7D Wong Choi matrix as the only official ability source:

| Key | Display | Weight |
|---|---:|---:|
| `sectional` | 段速與場地適性 | 0.20 |
| `trainer_signal` | 騎練訊號 | 0.18 |
| `stability` | 狀態與穩定性 | 0.14 |
| `race_shape` | 檔位與走位（不含步速） | 0.26 |
| `class_advantage` | 級數優勢 | 0.10 |
| `horse_health` | 馬匹健康 / 新鮮感 | 0.07 |
| `form_line` | 賽績線 | 0.05 |

## Matrix Mapping Calibration

- `sectional` is a speed conversion dimension: `speed_score` 65%, `track_going_score` 35%. Missing or unclear going evidence must stay neutral 60, so the track term acts as a suitability modifier rather than a standalone edge.
- `race_shape` remains the primary venue/position conversion dimension. In Auto V1 deterministic output it uses `draw_score` 100%; distance and carried weight must not be displayed under this dimension.
- `form_line` uses only race-line evidence: `formline_strength_score` 70%, `margin_trend_score` 30%. Same-distance evidence belongs to distance suitability, not the race-line dimension.
- `class_advantage` uses class/ratings and weight conversion: `class_score` 75%, `weight_score` 25%. Distance evidence must not be displayed under class advantage.
- `stability` uses `form_score` 50%, `consistency_score` 40%, `trackwork_trend_score` 10%. `trackwork_trend_score` is a derived readiness signal from `trackwork_digest`, so trackwork momentum lives with state/stability rather than sectional speed.
- `trainer_signal` uses only `jockey_score` and `trainer_score`; `confidence_score` is a data reliability signal, not a positive trainer/jockey edge.
- Jockey and trainer scorers must support HKJC Chinese names via `resources/05_jockey_trainer_tiers.json`. If names cannot be mapped, return neutral 60 rather than inventing an edge.
- `confidence_score` keeps a low-weight support role in `horse_health` only, so missing/complete data changes reliability without overpowering race evidence.

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
- `B+`: 74-79.99
- `B`: 68-73.99
- `C`: 60-67.99
- `D`: below 60

Grade is display-only. Ranking and Top 4 use numeric `ability_score`.

## Pick Status

- `MODEL_TOP_PICK`: rank <= 2, ability >= 70, confidence >= 55, no major/fatal risk
- `WATCH`: ability >= 70 but confidence/risk gate blocks top-pick status
- `NO_PICK`: all other horses
