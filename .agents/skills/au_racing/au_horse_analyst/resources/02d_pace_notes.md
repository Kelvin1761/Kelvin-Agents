<!-- Pace & Positional Notes (AU V4.3 Lightweight) -->
<!-- Replaces full 02d_eem_pace.md (archived 2026-04-25) -->

### Steps 7/10: Pace & Positional Notes

> Active Python Facts Engine `inject_fact_anchors.py` generates the official Speed Map from EEM/video + settled-position evidence.
> `au_speed_map_generator.py` is fallback only and must never treat Last10 finishing positions as running-style evidence.
> LLM must judge pace confidence and track-geometry transfer before assigning Race Shape ticks.

#### 0. Pace Confidence Gate

Assign one label before judging `race_shape`:

| Label | Evidence | Matrix cap |
|:---|:---|:---|
| `PACE_CONFIDENCE: Clear` | Leader map, run styles, draw, and jockey intent all point the same way | `race_shape` may reach ✅✅ |
| `PACE_CONFIDENCE: Mixed` | Two plausible pace scripts or leader hierarchy unclear | max ✅ |
| `PACE_CONFIDENCE: Low` | Heavy scratchings, debut-heavy race, unclear run styles, or same-stable unknown | max ➖ unless horse has unconditional positional edge |

If pace confidence is Mixed/Low, do not use race shape to cover a weak core engine.

#### 1. Leader Dominance Hierarchy
When exactly 2 potential leaders exist, do NOT auto-default to contested fast pace. Assess:
- **Factor A — Route Specialist:** Same venue+distance >=2 wins/placings while leading?
- **Factor B — Current Form:** Recent winner/stable vs opponent poor/class jump/debut?
- **Factor C — Jockey Authority:** Top-5 pace-controlling jockey vs passive/apprentice?
- **Verdict:** >=2/3 dominant -> `DOMINANCE_GAP = Clear` -> predict Soft Lead / Crawl
- **Verdict:** Even -> `DOMINANCE_GAP = Unclear` -> maintain Contested / Genuine

#### 2. Small Field Override (<=6 runners)
When mass scratchings reduce field to <6:
1. Class weight reduced (Class Pressure greatly weakened)
2. Position weight increased (tactics override 5-8 point rating gaps)
3. If core leader scratched -> must reassess pace shape
4. Lowest-rated horse positional uplift -> may outperform

#### 3. Course Geometry Transfer
Before upgrading a draw/pace setup, check whether the horse has proof on a comparable track family:
- **Tight-turn / short straight:** Moonee Valley, Caulfield, Canterbury-style profiles punish wide closers and long-stride horses.
- **Long straight / big track:** Flemington/Randwick-style profiles are more forgiving for sustained closers.
- **Straight sprint:** draw bias, wind, and lane pattern matter more than normal bend-position logic.
- **First time on a new geometry:** cap race-shape at ➖ unless the horse has class/sectional proof that travels.

#### 4. Scratchings & Map Rebuild
If leaders or on-pace runners are scratched:
1. Rebuild leader count and dominance gap.
2. Reclassify backmarkers: some become mid-pack if field size collapses.
3. Reassess inside gates: barrier 1-2 can become either perfect trail or traffic trap.
4. Do not keep the old pace label if the field shape changed materially.

#### 5. Same-Stable Deployment
Same trainer 2+ horses in same race, assess "sacrificial leader" dynamic:
- If same-stable leaders won't compete -> pace drops from Genuine to Soft Lead / Moderate
- This amplifies leader advantage (including stablemate pressers)
