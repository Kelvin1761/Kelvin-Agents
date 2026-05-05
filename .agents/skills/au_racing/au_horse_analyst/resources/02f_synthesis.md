<!-- Synthesis Framework (Step 14) — AU V4.3 7D Matrix 2026-04-29 -->
<!-- Case studies removed. Python rating_engine_v2.py handles calculation. -->
<!-- LLM role: assign dimension ticks + micro adjustments. Python computes grade. -->

### Step 14: Synthesis Framework

> Python `rating_engine_v2.py` + AU compile/orchestrator code handle grade computation.
> LLM must: (1) judge each dimension tick, (2) flag micro adjustments, (3) Python does the rest.

#### 14.A-D: Internal Reasoning (in `<thought>` only)
1. **Advantage Stacking:** Mark each Step 1-12 conclusion as tick/neutral/cross
2. **Contradiction Detection:** Resolve conflicts (pace > engine; risk > rebound; track > jockey)
3. **Scenario Dependency:** Unconditional (always valid) vs Conditional (needs pace/draw) vs High-risk (unproven)
4. **Narrative Thread:** Condense all conclusions into one coherent story

#### 14.E: AU V4.3 7-Dimension Rating Matrix

> **Dimension types:** Core > Semi-Core > Auxiliary.
> Core dimensions are gatekeepers. Any core cross = hard cap at B+.
> Base full-house is **A+**. **S-/S/S+ only come from ✅✅ conviction promotion**, never from ordinary ✅ count alone.
> **Step 6 Forgiveness** is NOT a dimension but a data filter. If forgiven, judge dimensions on traceable races.
> **Forgiveness bonus:** >=2 uncontrollable factors -> +1 auxiliary tick (not stackable with V-Rebound).
> **No standalone Gear & Distance dimension in V4.2.** Gear and distance evidence must be merged into the seven dimensions below.
> **AU-specific rule:** because AU data is thinner and racecourse variation is wider than HKJC, every dimension must state evidence confidence before assigning `✅✅`.

| Dimension | Type | Source | Strong | Weak |
|:---|:---|:---|:---|:---|
| **Fitness & Stability** | **Core** | Step 1,12 | Reliable official-race sample after forgive filter, current prep direction positive, margins closing, no unresolved vet issue | Trial-only stability, Deep Prep >=6, spell>120d no trial, 3 consecutive reliable big losses, weight flux >=20lb |
| **Sectionals & Engine** | **Core** | Step 2,8 | Class-par sectionals or PI/L400-L600 proxy excellent, no late decay, distance profile fits today | Sectionals/PI decaying, can't match Class Par or proxy benchmark, clear distance mismatch |
| **Race Shape & Position** | **Semi** | Step 7,10 | Pace confidence is Clear, engine/draw/track geometry all let the horse use ability | Pace map low confidence, pace-engine severe mismatch, tight-turn wide-draw closer, position-burnt with no improvement |
| **Jockey-Trainer Signal** | **Semi** | Step 5,11,12 | Deployment pattern + rider fit + targeted gear/spacing has independent support | Reputation-only signal, rider/horse style conflict, gear change without matching problem evidence |
| **Class & Weight** | Aux | Step 3 | Class edge survives AU class normalization and physical weight pressure | Drop-class deadweight >=60kg no record, provincial/country form over-promoted, rating saturated |
| **Track Suitability** | Aux | Step 4 | Same track family / surface / going band has enough sample and no transfer risk | Track family blind spot, first tight-turn, interstate transfer, wet/synthetic uncertainty |
| **Form Line** | Aux(opt) | Step 9 | Opponents subsequently performed same/higher class. Need >=2/N strong ratio for tick | Opponent line weak or too thin. N/A / trial-only = exclude from count |

#### AU Evidence Confidence Gate

Each dimension must be tagged internally as `High / Medium / Low / Unknown`.

| Confidence | Minimum evidence | Rating effect |
|:---|:---|:---|
| **High** | >=3 relevant official races, or >=2 official races plus one independent support anchor (trial, sire, trainer intent, class par) | May assign `✅✅` if no material contradiction |
| **Medium** | 1-2 relevant official races plus at least one support anchor | Max `✅`; use `✅✅` only for formal race evidence with class-par proof |
| **Low** | Trial-only, sire-only, interstate transfer with no comparable track family, or one unreliable race | Max `➖` for core dimensions; max `✅` for auxiliary only if supported |
| **Unknown** | Missing / N/A / no comparable evidence | `➖` and excluded from positive conviction; never `✅✅` |

**Low-confidence override:** if a horse's Top 2 case relies on two or more Low/Unknown dimensions, it cannot be promoted above A- unless both core dimensions are High or Medium with no cross.

#### Top 2 Ability Discipline (No Odds)

`final_rating` remains a single grade. The purpose is to identify the two horses most likely to run to true ability and finish top three. Race-shape upside can improve a grade, but it must not hide core ability defects.

| Dimension | Must prove | Common false positive to reject |
|:---|:---|:---|
| Fitness & Stability | Official-race reliability, forgiven bad runs removed, prep direction, margin trend | Treating trial form or raw last-start placing as stable ability |
| Sectionals & Engine | Class-par sectionals or proxy, L400/L600 trend, engine type, distance fit, no late decay | One fast split from one unreliable race becoming ✅✅ |
| Race Shape & Position | Pace confidence, track geometry, draw, running style, scratchings | Upgrading a weak engine purely because of a good draw or soft lead |
| Jockey-Trainer Signal | Deployment pattern, rider fit, targeted gear with independent support | Reputation-only signal or one gear change without matching problem evidence |
| Class & Weight | Metro/provincial/country normalization, benchmark level, physical weight pressure | Drop in class with deadweight automatically becoming ✅ |
| Track Suitability | Track family, surface/going sample size, venue transfer, wet/synthetic proof, health recovery | <=2 similar-surface starts treated as proven suitability |
| Form Line | Subsequent same/higher-class performance from key opponents | One isolated good opponent line used as repeated proof |

**Top 2 tiebreak discipline:** Within the same `final_rating`, rank by core ticks first, then ✅✅ conviction, then fewer crosses, fewer core crosses, lower race-shape risk, and only then total tick strength.

#### Gear & Distance Merge Rules (V4.2)

`Gear & Distance` is no longer an independent matrix row. Route the evidence as follows:

| Evidence | Merge into | Rule |
|:---|:---|:---|
| Best distance / same-distance record / distance W-P-L / sire distance projection | **Sectionals & Engine** | Good sectionals cannot be ✅✅ if today's distance profile is clearly wrong. Distance unknown normally caps this dimension at ✅ or ➖ depending on evidence strength. |
| Distance jump >=400m / first try at extreme trip / breathing risk | **Sectionals & Engine** + fine-tune/flag | If it undermines the engine, mark sectional down. Use `DISTANCE_JUMP` fine-tune only if the risk was not already fully priced into the matrix score. |
| Targeted gear change / first gear for a confirmed issue / elite stable gear premium | **Jockey-Trainer Signal** | Gear can support a deployment signal only when there is independent evidence. Gear alone is usually ➖, not ✅. |
| Gear positive already used for `jockey_trainer` ✅ | **No fine-tune repeat** | Do not also use `GEAR_POSITIVE`. Same event cannot create both a matrix tick and micro-upgrade. |
| Distance specialism already used for `sectional` ✅ | **No fine-tune repeat** | `DISTANCE_SPECIALIST` style logic can only upgrade if it adds evidence beyond the matrix reasoning. |

#### Track Family Rules (AU-only)

AU course variation is wider than HKJC, so `Track Suitability` must judge comparable conditions, not just venue name.

| Evidence layer | Stronger proof | Weaker proof / cap |
|:---|:---|:---|
| Venue | Same venue + same distance | Different venue = cannot claim venue specialist |
| Geometry | Similar turn radius / straight / tight-turn profile | First tight-turn or first straight sprint = max ➖ unless class/sectional proof is strong |
| Direction / state | Same state and direction with no travel stress | First interstate / East-West transfer = risk unless prior transfer success |
| Surface | Same Good/Soft/Heavy/Synthetic band | Synthetic/inner trial to turf = Low confidence |
| Weather | Stable going band | Forecast near Good/Soft or Soft/Heavy boundary = mark sensitivity |

`Track Suitability ✅✅` requires High confidence and at least two layers of comparable proof. Same surface alone is never enough.

#### Tick Discipline

- **✅✅** = conviction, not "slightly better than ✅". Use only when the dimension has multiple independent data anchors and no material contradiction.
- **Sectionals & Engine:** strong sectionals + distance fit are both required for ✅✅. If sectionals are strong but distance is unproven, max ✅.
- **Race Shape & Position:** pace confidence must be Clear for ✅✅. If speed map is Mixed/Low, max ✅ even if draw looks good.
- **Jockey-Trainer Signal:** reputation alone is not a signal. No deployment pattern, no clear rider/horse fit, and no targeted gear evidence = ➖.
- **Track Suitability:** same surface sample <=2 normally max ➖ unless there is same track-family proof from comparable conditions.
- **Form Line:** one strong opponent line may justify ✅, but ✅✅ needs repeated same/higher-class subsequent performance.
- **Class & Weight:** drop in class with deadweight, or class rise with major weight relief, must be judged as separate forces; do not auto-tick both.

#### Grade Lookup Table

> V4.2 base grade table. S-tier promotion is handled after base grade by ✅✅ conviction logic.

| Grade | Condition |
|:---|:---|
| **A+** | 2 core + 2 semi + >=2 aux ticks + zero crosses. Full ordinary package; may promote to S-tier only via ✅✅. |
| **A** | 2 core + zero crosses |
| **A-** | 1 core + (1 semi or neutral) + crosses <=1 |
| **B+** | 1 core + crosses=2; or 2 semi + crosses <=1 |
| **B** | 1 semi + >=2 aux ticks + crosses <=2 |
| **B-** | No core/semi ticks but >=3 aux ticks + crosses <=2 |
| **C+** | crosses=3 but >=1 core/semi tick to rescue |
| **C** | crosses=3, no core/semi ticks |
| **C-** | crosses=4 |
| **D** | crosses >=5 or zero ticks of any kind |

#### S-Tier Conviction Promotion

Promotion only applies after base grade + micro adjustment reaches **A+**:

| Double-Strong evidence | Promotion |
|:---|:---|
| >=1 core ✅✅ | +1 step per core ✅✅, max two core steps |
| >=2 semi-core ✅✅ | +1 step |
| +1 step | A+ -> S- |
| +2 steps | A+ -> S |
| +3 steps | A+ -> S+ |

S-tier still needs hard proof and scenario guards from Python (`apply_s_grade_guards`, wet/recency/trial caps). If a S-tier promotion relies only on soft shape or reputation, downgrade the underlying dimension before promotion.

**Tiebreaker:** Same grade -> compare tick count (more ticks wins); if tied -> compare cross count (fewer crosses wins).

#### Micro Adjustments (after base grade, before overrides)

> **Dual-Track System:** Channel A (below) + Channel B (factor interactions from archived matrix).
> Same factor cannot count in both channels. Net cap: +/-2 grades total (A: +/-1, B: +/-1).

**Upgrade factors (any one triggers, only if not already counted in matrix):**
- Pace-engine match (Step 10+7): today's pace strongly suits this horse's running style beyond the race-shape tick
- Jockey-horse synergy (Step 11): high engine match + golden combo strike rate beyond the jockey-trainer tick
- Weight/class edge (Step 3): class jump but >=4.5kg lighter / apprentice weight drop >=3kg beyond class-weight tick
- Positive gear change (Step 5): first gear targeting confirmed issue, similar change worked on others, and not already used for jockey-trainer ✅
- Trainer-track specialisation (Step 12): >=30% win rate at this specific track (search-confirmed), not already the main jockey-trainer reason
- Win streak momentum (Step 12): 3-streak within 90d = +1; 2-streak within 60d = +0.5 (needs support and not already the stability tick)
- Last win correction (Step 12): Wins + >=2/3 of same venue/distance/surface = +0.5; G2+ from lower class = +0.25, not already the stability/sectional reason

**Downgrade factors (any one triggers):**
- Fatal draw: tight-turn venue + outside draw 10+ + pace can't help cut in
- Inside trap (SIP-R14-3): barrier 1-2 + non-leader + >=10 runners = -0.5
- Interstate adjustment: first interstate + negative variables (weight/draw)
- Distance jump >=400m: breathing risk + no exemption, only if not already fully reflected in Sectionals & Engine
- Post-win regression: last win + significant weight increase + age >=7
- Deadweight: >=60kg, never placed at this weight. (Exempt: confirmed leader + crawl/moderate pace)
- Engine-pace reversal: today's pace severely disadvantages running style
- Jockey-horse mismatch: rider style conflicts with horse character
- Unresolved contradiction: cap at B

**Override rules -> see `02g_override_chain.md` (4 rules: P0 risk cap, P1 core wall, P2 rating dominance, P3 iron legs floor).**
