# HKJC Auto Scoring Contract

## Official Matrix

Auto uses the versioned 7D Wong Choi matrix as the only official ability
source. Standard runners and debut runners have separate locked outer-weight
sets; both are persisted in `python_auto_run_contract`.

| Key | Display | Weight |
|---|---:|---:|
| `sectional` | 段速 | 0.1285 |
| `trainer_signal` | 騎練訊號 | 0.2469 |
| `stability` | 狀態與穩定性 | 0.1090 |
| `race_shape` | 檔位與走位（不含步速） | 0.2417 |
| `class_advantage` | 級數優勢 | 0.1534 |
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
- `race_shape` remains the primary venue/position conversion dimension. It uses
  `race_shape_context_score` 100% (with neutral-safe `draw_score` fallback only
  when the context score is unavailable); distance and carried weight must not
  be displayed under this dimension. Standard Happy Valley runners use the
  user-accepted experimental V3 formula
  `draw + 0.45 × (PIT individual HV-turf performance − 60)`. Historical
  fit/trip stay visible but have zero live weight, and field tempo is withheld.
  Sha Tin and debut runners retain the prior venue formula. Operations can
  restore Happy Valley V2 with
  `WC_HKJC_HV_RACE_SHAPE_PROFILE=legacy_v2`; the selected profile is persisted
  in `python_auto_run_contract`.
- Before official whole-field ranking, every runner uses the same robust
  race-shape rule: retain the live outer weight (24.17% since EXP-20261009-04), but cap each runner's
  `race_shape` deviation from the same-race median at +/-10 points. This is a
  symmetric whole-field correction: it does not lock Top 2, protect any rank,
  or target named horses. It is persisted as `race_shape_robustness=winsor10`.
  Operations can restore the unbounded formula with
  `WC_HKJC_RACE_SHAPE_ROBUSTNESS=legacy_unbounded`; every prediction also
  persists `race_shape_legacy_unbounded` as an immutable rollback shadow.
- The live `draw_score` first applies the generic positional prior, then the
  promoted `pre_race_draw_context_v2` correction for non-debut turf runners.
  The correction is strict point-in-time and keyed by
  `venue × rail × distance-band × draw-group`; Sha Tin A and Happy Valley A
  are therefore separate populations and can never share a cell. It compares
  each rail cell with its same-venue distance parent, shrinks with 60
  pseudo-runners, requires 100 prior runners and 20 prior races, and caps at
  ±4 draw points. AWT, debut runners and insufficient cells are exact no-ops.
- `form_line` uses `formline_strength_score` 100%. `margin_trend_score` was removed from this dimension after the 2026-07-08 backtest because it duplicated per-run margin credit already represented in stability. Same-distance evidence belongs to distance suitability, not the race-line dimension.
- `class_advantage` uses class/ratings and weight conversion: `class_score` 75%, `weight_score` 25%. Distance evidence must not be displayed under class advantage.
- Same-distance performance enters only through the separately displayed, capped `distance_suitability_adjustment`; `distance_score` remains a diagnostic reference scale and must not be silently folded back into `class_score`.
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

Grade is display-only. Ranking and Top 4 use the numeric whole-field score below.

## Official Whole-Field Ranking

The displayed 7D `ability_score` is the sole official auditable ranking
signal. Official rank and Top 4 sort directly by that robust 7D score, with
horse number used only to resolve an exact tie. The within-race percentile is
display-only and is derived from the same 7D score. There is no second-stage
blend, hidden overlay, environment switch, or complete-strength shadow.

## Pick Status

- `MODEL_TOP_PICK`: rank <= 2, ability >= 70, confidence >= 55
- `WATCH`: ability >= 70 but rank/confidence gate blocks top-pick status
- `NO_PICK`: all other horses

## Prospective And Rollback Shadow Contract

Auto may persist research candidates
under `python_auto.shadow_profiles` and `python_auto_shadow_verdicts`; those
namespaces must never replace `ability_score`, `rank`, `python_auto_verdict`, or
the official Top 4.

Frozen 2026-09-28 profiles:

- `weight_refit_t02`: standard runners only; transfer 0.02 from `race_shape`
  to `stability`.
- `race_shape_v3_hv` and `race_shape_v3_hv_t02`: retained for settlement of
  immutable snapshots created before the 2026-09-29 experimental activation.
- `race_shape_v2_legacy_hv`: current Happy Valley rollback comparator. It uses
  the pre-V3 formula in shadow while V3 is live, and never restores the removed
  predicted-running-style signal.
- `race_shape_st_draw70`: Sha Tin turf standard runners only;
  `70% draw + 15% historical fit + 15% trip`. Sha Tin AWT, Happy Valley and
  debut runners are exact no-ops. This is forward evidence only and cannot
  promote itself.
- `trainer_recency_st_early90`: September-December Sha Tin turf standard
  runners only. It swaps only the trainer master-rating base for a strict-PIT
  90-day half-life aggregate; jockey, combo, distance, change, outer 7D weights
  and every other dimension remain unchanged. Historical regular-season
  testing rejected 90/180-day always-on use, so this season-phase restriction
  is post-hoc and may collect prospective evidence only.
- `pre_race_draw_context_v2`: promoted to the official draw/race-shape path on
  2026-10-07 after the locked development gate passed and the terminal window
  kept Gold and Good unchanged while improving champion and NDCG point
  estimates. Older immutable snapshots retain this name as their frozen
  candidate for settlement.
- `pre_race_draw_context_v1_generic`: rollback comparator created at V2
  promotion. It removes the live PIT rail correction and reconstructs the old
  generic draw formula without changing any other dimension.
- `race_shape_legacy_unbounded`: whole-field rollback comparator created when
  the symmetric winsor10 rule became user-accepted experimental live on
  2026-10-08. It preserves the uncapped race-shape score while keeping every
  other live adjustment fixed. After at least 80 active races, the monitor
  recommends (but never automatically activates) rollback only if legacy gains
  at least two Gold or two Good races and the other primary metric is
  non-negative.
- `reverse_bias_intraday_v1`: separate meeting-level prospective shadow. For
  target race N it may read only completed races `< N` from the same surface,
  and needs at least two such races. Only when shrunk early-position and draw
  signals both indicate a reverse regime may it keep official picks 1-3 and
  replace official pick 4 with the highest-ranked qualifying outer-draw
  scenario horse outside Top 4. Draw is only a proxy for lane; actual lane is
  not observed. This snapshot never edits scores, ranks, Logic, the official
  Top 4, or the immutable pre-race manifest. It is settled into a separate
  ledger and remains blocked from review until at least 80 active races; review
  can never auto-promote it.

Results settlement must read the immutable pre-race snapshot, verify its
manifest hashes, and join official results after scoring. No shadow profile may
promote or roll back the model by itself.
