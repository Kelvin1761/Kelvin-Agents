# AU Wong Choi Auto Matrix Refactor Spec

Last updated: 2026-05-13

## Goal

Refactor AU Wong Choi Auto so that each 7D matrix section is driven by structured `Facts.md` evidence instead of shallow string heuristics.

This spec is written against the current full-auto AU mainline:

- `inject_fact_anchors.py`
- `build_au_logic.py`
- `racing_engine/engine_core.py`
- `racing_engine/matrix_mapper.py`
- `racing_engine/renderer.py`

## Hard Constraints

1. `EEM` is deprecated and must be treated as removed.
2. AU auto must not depend on any `eem_*`, `EEM`, or `energy`-named fields.
3. `Facts.md` remains the only upstream evidence source.
4. All scoring improvements should happen through:
   - better `Facts.md` digest
   - better `_data` population
   - better feature extraction
   - better matrix mapping
5. Renderer wording must reflect actual scored evidence, not decorative facts that never entered the engine.

## Current Failure Pattern

### 1. Digest layer is too thin

Current AU auto logic only extracts a small subset of horse facts:

- `recent_form`
- `career_record_line`
- `engine_line`
- `formline_line`
- `track_record_line`
- `facts_section`

This is not enough for a strong matrix.

### 2. `jockey_trainer` is severely underpowered

Current `jockey_trainer` is mostly:

- rider name tier
- trainer name tier
- a weak fit heuristic

This causes the section to cluster around low-60s and fail to separate intent-driven runners from neutral runners.

### 3. Deprecated EEM still leaks into mainline

Current AU auto still references:

- `eem_summary`
- `eem_style`
- `high_energy_drain`

But AU `Facts.md` now outputs `走位消耗摘要`, not `EEM 能量摘要`.

Result:

- health/newness logic is effectively disconnected
- field names no longer match upstream facts
- remaining EEM references are technical debt and should be removed, not patched around

## Refactor Shape

Refactor the pipeline into 4 explicit layers:

1. `Facts render layer`
   - `inject_fact_anchors.py`
   - keep human-readable output
   - add stable labels where needed

2. `Facts digest layer`
   - `build_au_logic.py`
   - parse structured fields into horse `_data`

3. `Feature scoring layer`
   - `engine_core.py`
   - compute feature scores from `_data`

4. `Matrix aggregation layer`
   - `matrix_mapper.py`
   - combine features into 7D section scores

## Section-by-Section Upgrade Plan

### 1. `stability`

#### Current weakness

Mostly driven by recent placings only.

#### Facts to digest

- `近績序列解讀`
- `生涯`
- `初出 / 二出`
- recent trial rows
- `狀態週期`
- `趨勢總評`
- `走位消耗摘要`

#### New `_data` fields

- `status_cycle`
- `trend_summary`
- `recent_trial_places`
- `recent_trial_count`
- `recent_real_run_count`
- `consumption_level`
- `consumption_weighted_score`

#### New features

- `status_cycle_score`
- `trial_readiness_score`
- `freshness_score`

#### Notes

- Early-career and debut runners should use readiness and preparation continuity instead of being punished for lack of formal sample.
- `stability` should become:
  - form continuity
  - prep continuity
  - freshness / wear profile

### 2. `sectional`

#### Current weakness

Too dependent on `engine_line` token matching.

#### Facts to digest

- `引擎`
- `跑法`
- `距離分佈`
- `今仗 Xm`
- `PI 趨勢`
- `L400 PI 趨勢`
- recent trial placings

#### New `_data` fields

- `engine_type`
- `engine_confidence`
- `running_style`
- `running_style_confidence`
- `today_distance_record`
- `best_distance_band`
- `pi_trend`
- `l400_pi_trend`
- `distance_unproven_flag`

#### New features

- `pi_trend_score`
- `l400_trend_score`
- `distance_projection_score`

#### Notes

- `sectional` should stop pretending that `今仗 ✅` is enough.
- This section should answer:
  - can the horse sustain the race shape
  - is today’s trip aligned with its proven output
  - is the late-race profile improving or fading

### 3. `race_shape`

#### Current weakness

Mostly uses pace string + barrier + broad style text.

#### Facts to digest

- race speed map block
- `predicted_pace`
- `leaders / pressers / mid_pack / closers`
- `跑位軌跡`
- `走位跑法`
- `走位消耗`
- `track_bias`
- `戰術劇本`
- `預計走法`

#### New `_data` fields

- `predicted_pace`
- `pace_confidence`
- `style_bucket`
- `style_bucket_confidence`
- `last_two_run_shapes`
- `last_two_consumption_levels`
- `barrier_bucket`
- `pace_style_match`

#### New features

- `pace_pressure_score`
- `barrier_efficiency_score`
- `style_match_score`
- `traffic_risk_score`

#### Notes

- This section should explicitly avoid using finishing positions as pace evidence.
- `走位消耗摘要` should feed shape cost and traffic risk, not health only.

### 4. `jockey_trainer`

#### Current weakness

This is the weakest section in the AU matrix.

Current logic:

- rider tier
- trainer tier
- weak generic fit heuristic

Missing:

- horse-specific intent
- rider switch quality
- rider/trainer pattern context
- trial/deployment evidence

#### Facts to digest

- header rider/trainer
- trial rows
- tactical plan
- gear change language if available
- stable pattern clues already present in trend/status/tactical text

#### New `_data` fields

- `current_jockey`
- `current_trainer`
- `trial_rider_names`
- `latest_trial_rider`
- `latest_trial_win_flag`
- `trial_depth`
- `gear_change_summary`
- `tactical_aggression_flag`
- `rider_upgrade_flag`
- `rider_downgrade_flag`
- `stable_intent_flag`
- `horse_specific_intent_notes`

#### New features

- `rider_tier_score`
- `trainer_tier_score`
- `trial_rider_alignment_score`
- `intent_signal_score`
- `rider_change_quality_score`

#### Scoring logic target

`jockey_trainer` should become a blend of:

- rider quality
- trainer quality
- horse-specific execution intent

Recommended matrix formula:

- `rider_tier_score`: 0.24
- `trainer_tier_score`: 0.22
- `trial_rider_alignment_score`: 0.20
- `intent_signal_score`: 0.20
- `rider_change_quality_score`: 0.14

#### Interpretation rules

Positive signs:

- top rider retained after promising run
- top rider booked for lightly-raced improver
- race-day rider also rode latest winning/positive trial
- tactical plan implies deliberate forward use from suitable draw
- strong stable plus suitable rider plus clean prep

Negative signs:

- neutral rider with no intent markers
- downgrade rider on horse needing tactical precision
- mismatch between expected shape and rider profile
- no deployment clues and no horse-specific support

#### Why this matters

This section should no longer ask "is this a famous name?"

It should ask:

- does this booking mean something for this horse, today, in this setup

### 5. `class_weight`

#### Current weakness

`class_score` wants `class_move`, but AU digest does not populate it.

#### Facts to digest

- table `班次` column
- `生涯`
- today weight
- `今仗 Xm`
- same-distance record

#### New `_data` fields

- `class_move`
- `today_weight`
- `same_distance_starts`
- `same_distance_places`
- `career_stage`

#### New features

- `class_move_score`
- `weight_burden_score`
- `distance_class_fit_score`

#### Notes

- This section should evaluate class pressure in context, not just raw kilograms.

### 6. `track`

#### Current weakness

Current implementation is broad string matching.

#### Facts to digest

- `同場`
- `同程`
- `同場同程`
- `好地 / 軟地 / 重地`
- today going

#### New `_data` fields

- `venue_record`
- `distance_record`
- `venue_distance_record`
- `good_record`
- `soft_record`
- `heavy_record`
- `today_going`

#### New features

- `venue_affinity_score`
- `going_affinity_score`
- `venue_distance_confirmation_score`

#### Notes

- Split venue and going so the engine can distinguish:
  - likes Warwick Farm
  - likes soft
  - has already done both together

### 7. `form_line`

#### Current weakness

Mostly uses the headline `綜合評估`.

#### Facts to digest

- opponent table rows
- `後續比賽Class`
- `對手後續成績`
- `強度評估`

#### New `_data` fields

- `formline_rating_headline`
- `formline_higher_class_win_count`
- `formline_same_class_win_count`
- `formline_lower_class_win_count`
- `formline_strong_opponent_count`
- `formline_weak_opponent_count`

#### New features

- `opponent_progression_score`
- `headline_formline_score`
- `same_distance_formline_fit_score`

#### Notes

- `form_line` should become more evidence-driven than headline-driven.

## Mandatory EEM Removal

### Remove from AU auto engine

- `eem_summary`
- `eem_style`
- `high_energy_drain`
- any provenance string or note mentioning EEM

### Replace with

- `consumption_summary`
- `consumption_level`
- `consumption_weighted_score`
- `running_style`
- `running_style_confidence`

### Files to clean

- `.agents/scripts/inject_fact_anchors.py`
- `.agents/skills/au_racing/au_wong_choi/resources/00_pipeline_and_execution.md`
- `.agents/skills/au_racing/au_wong_choi/resources/engine_directives.md`
- `.agents/skills/au_racing/au_wong_choi_auto/scripts/build_au_logic.py`
- `.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py`
- `.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/renderer.py`

## Recommended `_data` Contract Additions

Minimum next contract for AU auto:

- `status_cycle`
- `trend_summary`
- `tactical_plan`
- `consumption_level`
- `consumption_weighted_score`
- `engine_type`
- `engine_confidence`
- `running_style`
- `running_style_confidence`
- `pi_trend`
- `l400_pi_trend`
- `class_move`
- `today_weight`
- `venue_record`
- `distance_record`
- `venue_distance_record`
- `good_record`
- `soft_record`
- `heavy_record`
- `trial_rider_names`
- `latest_trial_rider`
- `latest_trial_win_flag`
- `trial_depth`
- `gear_change_summary`
- `rider_upgrade_flag`
- `rider_downgrade_flag`
- `stable_intent_flag`
- `formline_higher_class_win_count`
- `formline_same_class_win_count`
- `formline_lower_class_win_count`

## File-by-File Refactor Order

### Phase 1: stop invalid dependencies

1. remove AU auto `EEM` references
2. rename health/shape evidence to `consumption`-based fields
3. make provenance truthful

### Phase 2: expand digest layer

1. upgrade `build_au_logic.py`
2. expand `_parse_horse_sections`
3. populate richer `_data`

### Phase 3: rebuild feature scoring

1. split monolithic string heuristics into smaller feature functions
2. add section-specific features listed above
3. keep neutral fallbacks explicit when evidence is absent

### Phase 4: remap matrix formulas

1. increase `jockey_trainer` feature diversity
2. reduce over-reliance on generic rider/trainer tiers
3. ensure each matrix section is visibly driven by different evidence

### Phase 5: renderer truthfulness

1. only show matrix anchor lines that actually fed the score
2. align "Python 判讀" with scored components
3. stop implying deep facts digestion when only headline fields were used

## Priority Recommendation

If doing this incrementally, the best order is:

1. remove EEM remnants
2. rebuild `jockey_trainer`
3. rebuild `race_shape`
4. rebuild `class_weight`
5. deepen `sectional`
6. deepen `track`
7. deepen `form_line`
8. revisit `stability`

Reason:

- `jockey_trainer` is the flattest and weakest discriminator right now
- `race_shape` is the next most likely to move rankings materially
- `class_weight` currently leaves obvious facts unused

## Success Criteria

The refactor is successful when:

1. no AU auto mainline file depends on `EEM`
2. `jockey_trainer` no longer clusters around 60-66 for most runners
3. each matrix section cites distinct scored evidence
4. renderer output can be traced back to populated `_data` fields
5. `Facts.md` improvements materially change ranking outcomes through the engine, not just the prose
