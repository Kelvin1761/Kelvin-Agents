# BeanBagData/horse-analyst — angles worth testing for AU

Reviewed 2026-10-14. TAB follow-up is deferred at the user's request. This is source review, not a scored experiment; no LLM adoption, model changes, or improvement claim.

## Sources and implementation boundary

Inspected README, `analyst.py`, `prompt.py`, V325.3 prompt text, and post-race instructions through GitHub. Relevant blob SHAs:

- `analyst.py`: `986ec4667eb69b831369389bcd36305b158030e3`
- `prompt.py`: `85c37343fe659f012458c11e64ec7dd4043a8c9c`
- V325.3 text: `f2e0e34d4a37ab2d98b7050da5b1c7c2545d54ec`

`analyst.py` imports `SYSTEM_PROMPT` from `prompt.py`, labelled V325.1. The newer V325.3 text is a separate document; it is not the imported runtime prompt. The reviewed runtime streams LLM responses rather than implementing these rules as a numeric scorer. Its `_classify_silo` implements three weekday/metro groups, whereas the prompt describes seven environment types. No out-of-sample validation of the quoted rules was found in the inspected materials.

Links: [runtime](https://github.com/BeanBagData/horse-analyst/blob/main/analyst.py), [active prompt](https://github.com/BeanBagData/horse-analyst/blob/main/prompt.py), [V325.3 specification](https://github.com/BeanBagData/horse-analyst/blob/main/Horse%20Racing%20Prompt%20V325.3%20AU-KINETIC%20OMNI.txt).

## What their weighting means

The design emphasizes projected trip geometry and preparation/late-speed state over conventional form, using overrides instead of a normalized feature-weight vector. V325.3 examples: prominent stalker +15%; metro/provincial class drop 1.5×; conditional effective-weight penalty −5% to −30%; old-win decay 15% per 30 days beyond 60 days; distance reduction ≥200m assigns peaking probability 0.85; total race distance >4,800m in 45 days triggers exclusion. Two leading selections must cover opposite pace profiles. The first-five score distribution controls an abstention rule. These are prescribed constants, not verified fitted coefficients; the named HMM is a rule, not a demonstrated trained state model.

## AU comparison and independent research hypotheses

| Angle | Current AU evidence | What would be worth measuring |
|---|---|---|
| Pace-map reliability | EXP-20261013-11: prior 800m position predictor rho .451; Sportsbet SpeedPos .163, on different available samples. Pace-luck, adjusted-margin and lone-leader candidates failed dev. | **High interest:** confidence in an individual horse's predicted early position. Use history count, variance, missingness, novice share and provider disagreement; validate position errors first. Then ask whether confidence identifies risky selections after controlling existing score. No new generic leader bonus. |
| Race-load history | Health score currently uses warnings, rest interval and trial evidence; inspected engine does not expose a named 45-day cumulative-distance feature. | **Medium interest:** cumulative formal-race metres, starts and minimum recovery gap in a fixed prior window. Include history coverage. This measures workload exposure, not lactate or clinical fatigue. Separate sprint/staying cohorts and control distance/class. Never adopt 4,800m as an automatic exclusion threshold. |
| State-change sensitivity | Existing daily updates and tactical explanations cover part of this; a reproducible per-selection sensitivity measure was not identified in the inspected paths. | **High interest for reliability reporting:** compare rankings under declared going scenarios and plausible pace changes. Freeze scenarios before outcomes; retain historical snapshots. Missing leaders cannot be removed merely to manufacture an appealing scenario. Actual late scratchings trigger a genuine rebuild. |
| Alternative pace coverage in Top 4 | Engine comments mark diversity adjustments report-only. Existing constrained reranker research is a different hypothesis and does not establish pace-diversity efficacy. | **Medium interest:** scenario-conditioned coverage, preserving sufficiently competitive horses. Forcing a weak opposite-style runner into second place may sacrifice Good. Evaluate Top-4 set selection separately from ordered Top-2 selection; no mandatory swap. |
| Form portability | Existing track/PQ/class inputs cover much of it. Conditional race-shape weighting and preparation-cycle score changes have already failed or remained unresolved. | **Medium/low interest:** applicability of a particular historical performance to today's surface, distance and class. Measure novel marginal contribution, not just a cohort's standalone AUC. Do not assume every country performance is inferior. |
| Traffic/start trouble | Source coverage audit EXP-20261013-11 found Sportsbet Video/Note/Stewards fields empty in its sample. | **Data-blocked:** first prove a source supplies dated original trouble evidence. Distinguish recurrent slow starts from a single obstructed trip. No inference from missing comments. |
| Trial quality, preparation, gear | Existing AU trial/preparation work, EXP-20260902-09 and EXP-20260826-07 cover related ideas. | Existing research limits priority. Do not revive rejected encodings using a new name or different arbitrary multiplier. |
| Wind and worn lanes | Requires track orientation, historical race-time wind, surface/rail and prior-race observations. | Low priority without point-in-time data. Wind direction relative to course segments is essential; generic headwind/tailwind multipliers are inadequate. |

Local evidence references:

- `docs/experiments/EXP-20261013-11-au-pace-luck-and-speed-map.md`
- `docs/experiments/EXP-20260902-09-au-preparation-cycle.md`
- `docs/experiments/EXP-20260928-07-au-ml-top4-constrained-rerank.md`
- `docs/experiments/EXP-20260826-07-au-gear-change-signal.md`
- `docs/experiments/EXP-20260831-14-au-race-shape-revival-and-conditional-weights.md`
- `au_racing_engine/engine_core.py`: health, preparation chronology and report-only tactical/diversity logic.

## Evidence cautions

The source's favourite/market overrides conflict with AU's independent-score policy. Complete commentary can contain market proxies. Uncalibrated NLS scores are not win probabilities; normalizing only the top five discards field-tail mass. Its 90% coverage count is not automatically Shannon entropy, and a numeric entropy threshold needs a defined logarithm base and field-size normalization.

The post-race framework proposes tracing missed winners back into new rules. Such explanations can generate hypotheses but cannot validate them. Keep pre-race selections immutable, record all misses as well as wins, and test hypotheses across the fixed dev/terminal split; do not reclassify a loss into a success because it was close.

## Recommended order

1. Pace **uncertainty** diagnostic, distinct from the already-rejected pace-score candidates.
2. Ranking sensitivity reporting to known going/lineup changes, with actual saved snapshots.
3. One cumulative-workload hypothesis with completeness controls.
4. Scenario-diverse Top-4 selection only after scenario estimates are reliable.

All remain hypotheses. Any scoring candidate must use the unchanged evaluation contract, Gold/Good, locked chronological samples, leakage audit, cohort guardrails and separate ablations. No production changes or tests required for this document-only review.
