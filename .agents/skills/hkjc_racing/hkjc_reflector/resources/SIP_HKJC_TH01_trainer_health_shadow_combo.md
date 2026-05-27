# SIP-HKJC-TH01: Trainer + Health Context Shadow Combo

## Status

Approved for shadow-candidate tracking.

Not yet baked into HKJC Horse Analyst resources or HKJC Wong Choi Auto production logic.

## Problem

Current live HKJC Auto is still too willing to rank "obvious" class horses highly even when two quieter pre-race risk layers are under-modeled:

- jockey / trainer / distance-context fit
- health / freshness / body-weight / medical stability context

This creates a recurring failure mode:

- winner anchor is often still visible
- place structure is weaker than it should be
- false negatives come from horses with steadier trainer-health profiles than their headline rank implies

2026-05-24 Sha Tin did not justify a hard draw-first correction. ML-style walk-forward review showed that draw-only overlays improve winner finding in some slices but damage minimum-threshold place structure too often.

## Approved Direction

Use a combined `Trainer Signal Context + Horse Health Context` shadow model as the next promoted SIP direction.

This is a pre-race feature-context overlay, not a market-based patch and not a pace-leader rewrite.

## Validation Summary

### Combined 131-race review

Baseline `current_live`:

- champion: `29`
- min-threshold: `60`
- good: `34`
- order_issue: `50`
- MRR: `0.4277`

Approved combo target:

- champion: `32`
- min-threshold: `65`
- good: `35`
- order_issue: `47`
- MRR: `0.4394`

### Interpretation

- This is the most balanced tested direction found in the current reflector sweep.
- It improves champion finding and minimum-threshold place structure together.
- It does not rely on a fragile draw-only or pace-only hard boost.

### Robustness notes

Paired race-level bootstrap on archive sample (`120` historical races):

- champion delta mean: `+0.0167` per race
- min-threshold delta mean: `+0.0417` per race
- good delta mean: `+0.0167` per race
- MRR delta mean: `+0.0095`

Paired race-level bootstrap on combined sample (`131` races):

- champion delta mean: `+0.0229` per race
- min-threshold delta mean: `+0.0382` per race
- good delta mean: `+0.0076` per race
- MRR delta mean: `+0.0117`

These are not "perfectly decisive" confidence intervals, but they are materially cleaner than draw-only candidates, which showed stronger winner uplift while damaging `min-threshold`.

## What The Combo Actually Does

### 1. Trainer Signal Context overlay

Use pre-race historical priors to adjust `jockey_score` / `trainer_score` before matrix aggregation:

- current jockey-horse history
- jockey-trainer combo history
- jockey-distance priors
- trainer-distance priors
- mild penalty for jockey-change situations with weaker historical profile

### 2. Horse Health Context overlay

Use pre-race stability signals to adjust `risk_score` before matrix aggregation:

- medical flags / recovery evidence
- days since last run
- body-weight span and trend
- trackwork health / blank days / swimming / risk flags

## Why This Direction Was Approved

### Rejected as primary bake direction

`candidate_draw_context`

Reason:

- improved winners too aggressively
- damaged minimum-threshold place structure on historical sample
- likely overfits positional shortcuts instead of improving true ranking quality

### Retained as secondary observation

`candidate_outer_weights_retune`

Reason:

- useful upside
- not as stable as the trainer-health combo
- should stay behind TH01 unless future meetings confirm it

## Scope

This proposal is for HKJC Auto shadow testing and later production bake consideration.

Primary code areas if baked later:

- `hkjc_wong_choi_auto/scripts/racing_engine/features/trainer.py`
- health / risk feature computation path in Auto engine
- pre-race matrix feature transform layer used by reflector candidate validation

## Non-Goals

This SIP does **not**:

- use market odds
- add pace prediction back into Auto
- add leader-count logic
- hard-bake draw bonuses as primary ranking driver

## Recommended Rollout

### Phase 1: Shadow only

- Track TH01 against `current_live` for next `2-3` HKJC meetings
- keep same KPI gate:
  - champion
  - min-threshold
  - good
  - order_issue
  - MRR

### Phase 2: Bake candidate

Promote only if:

- min-threshold does not regress on the next shadow sample
- champion uplift remains non-negative
- no obvious new order-instability pattern emerges

## Meeting Anchor

Decision approved after 2026-05-24 Sha Tin review, but justified by combined historical walk-forward evidence rather than that meeting alone.
