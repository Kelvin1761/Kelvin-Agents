# 2026-05-30 AU Pace / Profile Shadow Test Results

## Tested Variants
- `soft_profile_cap`
- `pace_clear_only_rerank`
- `near_miss_hard_context_promotion`
- `combined`

## Baseline
- Archive: `316` races
  - Champion `24.4%`
  - Gold `4.1%`
  - Good `20.9%`
  - Pass `38.9%`
  - Top3 Place `42.6%`
  - `0-hit` races: `48`
- 2026-05-30 target meetings: `28` races
  - Champion `25.0%`
  - Gold `3.6%`
  - Good `14.3%`
  - Pass `21.4%`
  - Top3 Place `32.1%`
  - `0-hit` races: `8`

## Variant Results

### `soft_profile_cap`
- Archive:
  - Gold `+0.9`
  - Good `+0.6`
  - Pass `-0.6`
  - Top3 Place `-0.2`
  - `0-hit` races `+3`
- 05-30:
  - Good `-3.6`
  - Pass `+0.0`
  - Top3 Place `+0.0`
- Verdict:
  - Not safe.
  - It trims some false positives, but it also increases archive `0-hit` races and hurts the live 05-30 target set.

### `pace_clear_only_rerank`
- Archive:
  - No measurable change
- 05-30:
  - Pass `+7.1`
  - Top3 Place `+2.4`
  - Good `-3.6`
  - `0-hit` races `+0`
- 05-30 meeting effect:
  - Caulfield: no change
  - Eagle Farm: Pass `22.2% -> 33.3%`, Top3 Place `22.2% -> 25.9%`
  - Rosehill Gardens: Pass `10.0% -> 20.0%`, Top3 Place `30.0% -> 33.3%`
- Verdict:
  - Promising only on the 05-30 card.
  - Cannot be approved from this test alone.

### `near_miss_hard_context_promotion`
- Archive:
  - No measurable change
- 05-30:
  - No measurable change
- Verdict:
  - Current thresholds are too weak or too narrow.

### `combined`
- Archive:
  - Same overall behaviour as `soft_profile_cap`
  - Gold `+0.9`, Good `+0.6`, Pass `-0.6`, Top3 Place `-0.2`, `0-hit` races `+3`
- 05-30:
  - Same main effect as `pace_clear_only_rerank`
  - Pass `+7.1`, Top3 Place `+2.4`, Good `-3.6`
- Verdict:
  - Not approvable.
  - Target improvement exists, but archive cost is not acceptable.

## Critical Limitation
`pace_clear_only_rerank` could not be fairly validated on archive races because the current archive logic snapshots do not contain usable high-confidence pace states:

- Archive pace confidence counts:
  - `Clear`: `0`
  - `Mixed`: `257`
  - `Low`: `59`

The main reason is that most archived AU speed maps were generated with:
- `Unknown venue`

That pushes pace confidence away from `Clear`, so the historical test cannot yet answer whether venue-aware clear pace projections genuinely improve the engine across the archive.

## Decision Read
- `soft_profile_cap`: reject for now
- `near_miss_hard_context_promotion`: reject for now
- `combined`: reject for now
- `pace_clear_only_rerank`: hold for further validation, not approval yet

## What This Means
The only idea showing live-card upside is `pace_clear_only_rerank`, but the archive is currently not in a state that can validate it properly.

So the honest decision after testing is:
- Do **not** approve any variant into mainline yet.
- If pace is the next lane to explore, first rebuild or regenerate archive pace maps with venue-aware speed-map metadata, then rerun the same shadow test.
