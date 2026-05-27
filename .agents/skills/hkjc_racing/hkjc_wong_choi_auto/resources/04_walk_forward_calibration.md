# HKJC Auto Walk-Forward Calibration

## Scope

Validation for the calibrated Auto 7D weights and matrix mapping after adding HKJC Chinese jockey/trainer name support.

Meetings:

- 2026-04-12 Sha Tin
- 2026-04-19 Sha Tin
- 2026-04-26 Sha Tin
- 2026-05-03 Sha Tin
- 2026-05-06 Sha Tin
- 2026-05-09 Sha Tin
- 2026-04-15 Happy Valley
- 2026-04-22 Happy Valley
- 2026-04-29 Happy Valley

Total sample: dynamic walk-forward coverage based on all matched meetings currently present under `Archive_Race_Analysis`.

## Result

| Model | Gold | Good | Min Threshold | Single | Champion | Top3 Has Champion | Order Issue |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current 0.12 | 5 | 17 | 34 | 80 | 19 | 46 | 32 |
| Original-style trainer 0.21 | 4 | 16 | 34 | 77 | 21 | 44 | 34 |
| Balanced 0.16 | 5 | 18 | 35 | 81 | 22 | 47 | 31 |
| Tier-calibrated 0.16 | 5 | 19 | 36 | 80 | 21 | 47 | 30 |
| Track-going strict verdict | 5 | 19 | 36 | 80 | 22 | 47 | 30 |

## Decision

Latest mainline decision after dedup walk-forward review (`131` unique races / `13` unique meetings):

- `race_shape`: 0.2560
- `trainer_signal`: 0.2209
- `stability`: 0.0919
- `sectional`: 0.1849
- `class_advantage`: 0.1335
- `horse_health`: 0.0378
- `form_line`: 0.0749

This replaced the older mixed-sample calibration after the reflector dedup pass removed duplicate race leakage. The updated weights preserved `good` and `min-threshold` while lifting `champion`, reducing `order_issue`, and improving `MRR` on the clean benchmark.

A second component-weight pass checked every matrix section. `sectional` improved with a component change: `speed_score` 75% / `track_going_score` 25% became `speed_score` 65% / `track_going_score` 35%. A later semantic/performance pass also replaced the `stability` support tail from `confidence_score` 10% to derived `trackwork_trend_score` 10%, which kept headline hit metrics flat while slightly improving winner-rank quality.

| Model | Gold | Good | Min Threshold | Single | Champion | Top3 Has Champion | Avg Winner Rank | MRR | Avg Pick1 Finish | Avg Top4 Hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Pre-cleanup calibrated | 4 | 18 | 36 | 81 | 24 | 46 | 4.648 | 0.4392 | 4.802 | 2.088 |
| Semantic cleanup only | 3 | 19 | 38 | 80 | 23 | 50 | 4.593 | 0.4410 | 6.044 | 2.044 |
| Recalibrated cleanup | 4 | 24 | 39 | 80 | 27 | 51 | 4.527 | 0.4678 | 5.044 | 1.989 |
| Recalibrated + sectional 65/35 | 4 | 24 | 40 | 80 | 27 | 51 | 4.516 | 0.4682 | 4.912 | 2.022 |
| Live + stability trackwork 10% | 4 | 24 | 40 | 80 | 27 | 51 | 4.505 | 0.4684 | 4.912 | 2.022 |

The first calibration reduced `trainer_signal` because the scorer had near-zero variance on HKJC Chinese names. After adding Chinese jockey/trainer mapping, the combined Sha Tin + Happy Valley grid search found that `trainer_signal` 0.16 is the best stable range. A later tier-table pass moved obvious missing names into `resources/05_jockey_trainer_tiers.json` and reduced `race_shape` to 0.20, improving Good, Minimum Threshold, and Order Issue while keeping Gold and Top3 Has Champion flat.

The track-going strict verdict pass keeps generic draw/bias `上名率` text out of `track_going_score`. This prevents a draw-stat line from becoming an automatic going/track-suitability bonus. On the 91-race sample it kept Gold, Good, Minimum Threshold, Single, Top3 Has Champion, and Order Issue flat while improving Champion from 21 to 22.

Sensitivity snapshot across the 91-race mixed-venue sample:

| Weights | Gold | Good | Min Threshold | Single | Champion | Top3 Has Champion | Order Issue |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current 0.12 / 0.26 race shape | 5 | 17 | 34 | 80 | 19 | 46 | 32 |
| Original-style 0.21 / 0.17 race shape | 4 | 16 | 34 | 77 | 21 | 44 | 34 |
| Balanced 0.16 / 0.22 race shape | 5 | 18 | 35 | 81 | 22 | 47 | 31 |
| Tier-calibrated 0.16 / 0.20 race shape | 5 | 19 | 36 | 80 | 21 | 47 | 30 |
| Tier + strict track-going verdict | 5 | 19 | 36 | 80 | 22 | 47 | 30 |

## Guardrails

- Do not add leader score, pace score, on-pace score, or backmarker score to Auto V1.
- `confidence_score` remains a reliability support signal, not a direct trainer/jockey edge. After the stability semantic cleanup, its live matrix role stays in `horse_health` only.
- Tier-table additions must pass mixed-venue walk-forward validation. Avoid broad name boosts that only improve coverage while reducing position KPIs.
- Keep future race-shape improvements in Classic/LLM SIPs unless deterministic walk-forward evidence proves an Auto-safe feature.

## Tier Coverage Check

After adding `resources/05_jockey_trainer_tiers.json`:

| Signal | Before | After |
|---|---:|---:|
| `jockey_score = 60` | 55.2% | 49.4% |
| `trainer_score = 60` | 65.1% | 48.9% |
| `trainer_signal = 60` | 37.8% | 27.3% |

## Reproduction

```bash
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/walk_forward_auto_backtest.py \
  Archive_Race_Analysis/2026-04-12_ShaTin \
  Archive_Race_Analysis/2026-04-19_ShaTin \
  Archive_Race_Analysis/2026-04-26_ShaTin \
  Archive_Race_Analysis/2026-05-03_ShaTin \
  2026-05-06_ShaTin \
  2026-05-09_ShaTin \
  Archive_Race_Analysis/2026-04-15_HappyValley \
  Archive_Race_Analysis/2026-04-22_HappyValley \
  Archive_Race_Analysis/2026-04-29_HappyValley
```

## Future Review Protocol

For any future Auto weighting or matrix-mapping change after the form-line realignment pass, do not rely only on stored `python_auto.feature_scores`.

Reason:

- Current `form_line` now depends on hidden derived signals such as `formline_strength`, `margin_trend`, and `same_distance` evidence.
- A feature-only replay can miss those hidden components and give a false sense of improvement/regression.

Use the full review harness instead:

```bash
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/review_auto_weighting.py
```

That script re-scores each archived `Race_*_Logic.json` directly through the live engine, then compares the current formula set against the prior calibrated baseline using matched actual results.

Current live ranking behavior uses `ability_score` as the base order, with a draw micro tie-break applied only when the #3 and #4 horses are within the trigger gap. Walk-forward review should therefore treat that tie-break as part of the live baseline rather than as a separate cosmetic post-process.
