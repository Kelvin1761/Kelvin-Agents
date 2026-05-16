# SIP-HKJC-RS01: Position Conversion Overlay

## Status

Proposal only. Do not bake into Horse Analyst resources until reviewed and walk-forward validated.

## Problem

Classic pace prediction is too brittle when it tries to forecast the whole race shape: leader count, fast/slow tempo, or collapse scenarios can swing the analysis too aggressively from uncertain evidence.

Recent Sha Tin C-rail reviews show the failure mode is usually more local:

- A horse with usable early or tactical position can convert draw/rail/distance into a low-consumption trip.
- A high-rated horse can lose too much if its running style, draw, and rail configuration create a poor position conversion.
- Longshot winners such as 2026-05-09 Sha Tin R4 and race-shape misses such as R7 are better explained by trip conversion than by a confident pre-race global pace call.

## Proposed Principle

Replace hard pace prediction upgrades with a horse-level `Position Conversion Overlay`.

This is not a pace score and not a leader score. It answers one narrower question:

> Can this horse reliably secure a tactically useful position for today's rail, distance, draw, and known running style without paying an excessive early cost?

## Inputs

Use only evidence already visible in Logic/Facts:

- Historical in-running position windows from the last 3-6 starts.
- Running-style confidence: front / handy / midfield / backmarker / flexible.
- Draw-position fit: inner/outer preference, historical draw performance, and whether today's draw matches preferred trip.
- Rail and distance geometry: especially Sha Tin C/C+3, ST 1200m, ST 1400m, ST 1600m, and ST 1000m straight-course exceptions.
- Recent intent evidence: last-start comments, gear changes, jockey instructions when available, and whether recent runs show intentional forward/midfield placement.

Do not use:

- Market odds.
- Global pace prediction as a scoring input.
- Synthetic leader count.
- On-pace/backmarker numeric scores in Auto.

## Overlay Bands

### Positive Overlay

Trigger when at least two are true:

- Running style has medium/high confidence and matches today's draw-distance setup.
- Historical position window shows repeated low-consumption forward/handy/midfield placement.
- Draw-position fit says today's draw supports the horse's preferred route.
- Rail/distance setup rewards that route, for example Sha Tin C/C+3 with a horse able to hold forward or cover-saving midfield.

Effect:

- Classic LLM may lift race-shape / trip confidence by one cautious notch.
- Cannot override major health, class, or speed negatives by itself.

### Negative Overlay

Trigger when at least two are true:

- Horse is consistently backmarker or positionally slow in a rail/distance setup that punishes that style.
- Draw-position fit says today's gate forces the horse away from its preferred route.
- Recent position window shows repeated high or extreme consumption.
- C/C+3 rail plus bend-start sprint/mile makes the expected route cost materially higher.

Effect:

- Classic LLM should cap final confidence unless there is strong compensating speed/class evidence.
- For top picks, require explicit explanation of how the horse avoids the trip cost.

### Neutral Overlay

Use when running-style confidence is low, data is sparse, or signals conflict.

Effect:

- No upgrade or downgrade.
- State that trip conversion is unresolved rather than inventing a pace scenario.

## Why Not Simple Leader Score

A simple leader score would recreate the same failure mode as pace prediction: it rewards an assumed role before proving whether the horse can actually convert that role today.

The better version is a conversion overlay:

- It can identify a likely leader, but only as one evidence item.
- It also handles handy/midfield horses that win through cover and low consumption.
- It penalizes positional mismatch without needing to declare the race "fast" or "slow".

## Validation Plan

Backtest on known Sha Tin C/C+3 meetings:

- 2026-04-19 Sha Tin
- 2026-04-26 Sha Tin
- 2026-05-03 Sha Tin
- 2026-05-06 Sha Tin
- 2026-05-09 Sha Tin

Pass criteria:

- Improves or preserves Top3 minimum-threshold hit rate.
- Reduces top-pick false positives caused by poor trip conversion.
- Does not reduce single-hit rate by more than one race per 50-race sample.
- Each promoted longshot must have explicit position-conversion evidence, not just "could lead".

## Implementation Target

Classic HKJC Horse Analyst resources only:

- `03_engine_pace_context.md`
- `04_engine_corrections.md`
- `10a_track_sha_tin_turf.md`
- `06_rating_aggregation.md`

Do not implement in HKJC Wong Choi Auto V1 because Auto's contract forbids pace prediction, leader count, on-pace score, and backmarker score.
