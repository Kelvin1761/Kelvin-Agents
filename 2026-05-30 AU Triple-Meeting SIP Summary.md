# 2026-05-30 AU Triple-Meeting SIP / Improvement Themes Summary

## Scope
- Meetings covered:
  - `2026-05-30 Caulfield Race 1-9`
  - `2026-05-30 Eagle Farm Race 1-9`
  - `2026-05-30 Rosehill Gardens Race 1-10`
- Source reports:
  - `2026-05-30 Caulfield Race 1-9_Reflector_Report.md`
  - `2026-05-30 Eagle Farm Race 1-9_Reflector_Report.md`
  - `2026-05-30 Rosehill Gardens Race 1-10_Reflector_Report.md`
- Deep backtest basis:
  - AU archive recomputed review over `47` meetings / `417` races
  - Shadow candidates tested:
    - `bundle_recommended`
    - `class_venue_weight_soft`

## Meeting Snapshot
- Caulfield: `Gold 1 / Good 1 / Pass 1 / 1 Hit 2 / Miss 4`
- Eagle Farm: `Gold 0 / Good 1 / Pass 2 / 1 Hit 0 / Miss 6`
- Rosehill Gardens: `Gold 0 / Good 1 / Pass 1 / 1 Hit 5 / Miss 3`

## Cross-Meeting Read
- Across the 3 meetings, the dominant issue was still **clean model failure**.
  - `20` races were tagged `偏向 clean model failure`
  - `8` races were tagged `帶有可寬恕元素或非純模型錯誤`
- Rosehill was the healthiest profile.
  - The model often had signal but under-ranked the eventual placegetters.
- Eagle Farm was the weakest profile.
  - Misses were broader and more structural, not just tie-break drift.
- Caulfield sat in the middle.
  - There were real hits, but late-card and pace-context misses remained obvious.

## Combined SIP Themes
Recurring meeting-level suggestions across all 3 reports:

1. `加強騎師 / 練馬師 / 人馬配搭權重` — `18` mentions
2. `加強班次 / 路程 / form line interpretation` — `17` mentions
3. `細化檔位 / 步速 / 場地偏差 context` — `16` mentions
4. `加強段速 / 試閘 / 速度訊號` — `7` mentions

## Theme Interpretation
### Tier 1: Most repeatable meeting-level pressure points
- `jockey_trainer`
  - Most visible at Eagle Farm and Rosehill.
  - Suggests some winners / placegetters had human-placement or intent signals that current ranking did not promote enough.
- `class_distance`
  - Strong across Rosehill and parts of Caulfield / Eagle Farm.
  - Suggests the engine still under-reads ladder context, race shape suitability, or the practical strength of prior form lines.
- `draw_pace`
  - Strongest at Caulfield, still present in Rosehill.
  - Looks more like context ordering failure than total signal absence.

### Tier 2: Secondary but still relevant
- `sectional`
  - Present, but clearly behind the top 3 themes in frequency.
  - Best treated as a supporting calibration lane, not the first SIP to approve.

## Deep Backtest Result
Archive baseline inferred from the recomputed review:

- Meetings: `47`
- Races: `417`
- Champion: `93`
- Gold: `16`
- Good: `80`
- Pass: `158`
- Order Issue: `163`
- MRR: `0.3687`
- Avg Top4 Hits: `1.609`

### Candidate 1: `bundle_recommended`
- Description: `調整 AU 6D 內部 factor balance（sectional / jockey-fit / class / formline）`
- Result vs baseline:
  - Champion: `+1`
  - Gold: `-3`
  - Good: `-5`
  - Pass: `-2`
  - Order Issue: `+2`
  - MRR: `-0.0038`
  - Avg Top4 Hits: `+0.012`
- Read:
  - This is **not a clean global upgrade**.
  - It improves some outright winners, but loses too much on broader quality labels and ordering consistency.
  - Best treated as a shadow-only candidate for narrower profiling, not a mainline approval.

### Candidate 2: `class_venue_weight_soft`
- Description: `柔性加入 AU class ladder + venue depth + 負磅 context`
- Result vs baseline:
  - Champion: `-25`
  - Gold: `+2`
  - Good: `-10`
  - Pass: `-15`
  - Order Issue: `+2`
  - MRR: `-0.0428`
  - Avg Top4 Hits: `-0.038`
- Read:
  - This is a **clear reject** as a global SIP.
  - Even if it helps a few showcase races, the full archive degradation is too large.

## Approval View
### Safe conclusions now
- Do **not** approve `class_venue_weight_soft` as live logic.
- Do **not** approve `bundle_recommended` as a full global rollout yet.

### Best next SIP direction
1. Prioritize a **focused jockey-trainer / intent context shadow test**.
2. Pair that with a **targeted class-distance interpretation shadow test** rather than broad class-venue rebalance.
3. Keep `draw_pace` as a metro-meeting tie-break refinement lane, especially for Caulfield-style cards.
4. Treat `sectional` as a secondary calibration stream, not the lead SIP.

## Practical Recommendation
- If you want the next change to be conservative:
  - Start with a narrow `jockey_trainer` shadow variant.
- If you want the next change to attack the biggest cross-meeting blind spot:
  - Run a dedicated `class_distance + form line interpretation` experiment.
- If you want to optimize specifically for this 2026-05-30 triple-header style:
  - Combine `jockey_trainer`, `class_distance`, and `draw_pace` as a temporary review basket, but keep it out of mainline until a new archive backtest passes.
