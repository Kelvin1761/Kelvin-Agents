# AU Class x Weight Improvement Plan

Date: 2026-05-21

## Current Baseline

Benchmark command:

```bash
python3 .agents/skills/au_racing/au_reflector/scripts/au_review_auto_weighting.py \
  --base-dir Archive_Race_Analysis/AU_Racing \
  --mode recomputed \
  --json
```

Current recomputed 395-race baseline:

| Metric | Result |
|---|---:|
| Champion | 67 / 395 = 17.0% |
| Gold | 14 / 395 = 3.5% |
| Good | 62 / 395 = 15.7% |
| Minimum / Pass | 133 / 395 = 33.7% |
| Order Issue | 147 / 395 = 37.2% |
| Avg Top4 Hits | 1.501 |

This should be the control baseline for all class/weight work.

## What We Know

The current mainline is Python-only, but class data is only partially connected.

The `facts_section` replay bug was fixed first. After that fix, `class_score` no longer collapses to `60 + class_move` for every horse. The old archive replay had 4,772 / 4,772 horses matching the simple formula. After the fix, only 1,226 / 4,772 match it, so deeper class rules are now active.

The user hypothesis that class and weight should be treated as an interaction is directionally correct. However, a blunt multiplication is dangerous because weight can be a positive signal for proven high-class horses and a false comfort signal for low-class/light horses.

## Data Audit Findings

Archive coverage check:

| Item | Coverage |
|---|---:|
| Facts files | 451 |
| Facts record rows | 58,182 |
| Official race rows | 36,684 |
| Trial rows | 21,498 |
| Formguide past-run lines with prize money | 122,341 / 122,341 = 100.0% |
| Formguide past-run lines with raw class token | 0 / 122,341 = 0.0% |
| Facts `L600/RT` coverage | 0 / 58,182 = 0.0% |

Important implication:

`Facts.md` table column `類型` is not reliable raw past-race class. In the archive it is effectively `Maiden/SW` for every official row. That means current archive data cannot support clean "last 6 race class vs today class" calibration from raw class labels.

What we do have reliably:

| Signal | Usefulness |
|---|---|
| Current race class | Good. Extractor writes race header class, e.g. `BM72`, `Group`, `Listed`. |
| Past race prize money | Strong proxy. Present in Formguide lines. |
| Past venue | Good proxy. Present in Facts/Formguide. |
| Past class move | Usable but derived. Already present as `↑升班`, `↓降班`, etc. |
| Past RT/L600 | Intended, but currently not populated into archive Facts. |
| Raw past race class | Not available in current markdown archive. |

## Failed / Weak Shadow Tests So Far

These were tested against the current recomputed baseline.

| Variant | Champion | Good | Pass | Order Issue | Verdict |
|---|---:|---:|---:|---:|---|
| Baseline | 67 | 62 | 133 | 147 | Control |
| Global class-only class_weight | 71 | 56 | 137 | 153 | Pass up, Good/order worse. Too blunt. |
| Low-class/light shield | 67 | 62 | 132 | 144 | Order slightly better, Pass worse. Too weak. |
| History proxy global | 68 | 58 | 136 | 156 | Pass up, Good/order worse. Not safe. |
| History proxy formline only | 68 | 59 | 134 | 152 | Still hurts Good/order. Not safe. |

Conclusion: do not implement a class/weight scoring change yet without improving data quality or adding a narrower tested interaction.

## Why Current Class/Weight Is Still Weak

Current `class_weight` is additive:

```python
0.66 * class_score + 0.34 * weight_score
```

This loses the key racing logic:

| Case | Desired interpretation |
|---|---|
| High class + high weight + proven recent performance | Weight should not be heavily punished. It may confirm class. |
| Low class + light weight + weak recent performance | Light weight should not be trusted as an edge. |
| Rising class + high weight | Negative interaction. Low margin for error. |
| Dropping class + manageable weight | Positive interaction, but only if recent performance is not stale. |
| Metro target + provincial last-run class/proxy | Needs a class-depth discount unless RT/prize/formline supports it. |

Our current score has some of these rules inside `_weight_score()` and `_class_score()`, but the final matrix still treats class and weight as separate additive features.

## Recommended Test-First Plan

### Phase 1 - Data Plumbing Before Scoring

Goal: stop losing useful class-depth evidence before it reaches the engine.

Tasks:

1. Inspect live Racenet `forms` payload fields for past-run `eventClass`, `handicapClass`, `racePrizeMoney`, `last600`, `rtRating`, margin, and pace fields.
2. If raw fields exist, patch `au_race_extractor/scripts/extractor.py` to write them into Formguide past-run lines in a backward-compatible way.
3. Patch `.agents/scripts/inject_fact_anchors.py` only if needed so Facts rows preserve the new fields.
4. Add an audit gate that reports raw class / prize / RT / L600 coverage after extraction.

Acceptance gate:

| Gate | Required |
|---|---|
| Existing archive benchmark unchanged unless re-extracted | Yes |
| New extraction sample has raw class or richer proxy fields | Yes |
| No scorer change yet | Yes |

### Phase 2 - Shadow Class-Depth Features

Goal: compute new features without changing rankings.

Candidate features:

| Feature | Data source | Purpose |
|---|---|---|
| `past_prize_depth_6` | Formguide prize money | Compare last 6 official races against today prize/class. |
| `venue_depth_6` | Venue tier | Penalize provincial-to-metro jump unless compensated. |
| `past_class_label_6` | Only if extractor can get it | True class normalization. |
| `class_weight_interaction` | class_score, weight_score, class_move, RT/prize | Replace additive logic later if it wins. |
| `low_class_light_trust_penalty` | class_score + weight + recent result | Stop overtrusting light-weight weak-class runners. |

Acceptance gate:

Run 395-race shadow scoring and require:

| Metric | Minimum to proceed |
|---|---|
| Good | Must not drop below 62 |
| Pass | Must improve by at least +4 races, or improve Order Issue by at least -8 with no Good loss |
| Order Issue | Must not worsen |
| Champion | Should not drop by more than -2 |

### Phase 3 - Class x Weight Interaction

Only after Phase 2 passes, implement a narrow interaction, not raw multiplication.

Initial formula direction:

```text
base = 0.62 * class_score + 0.28 * weight_score + 0.10 * class_depth_score

interaction_adjustment:
  + proven_high_class_high_weight
  + drop_class_manageable_weight
  - rise_class_high_weight
  - low_class_light_unproven
  - provincial_to_metro_unproven
```

Important rule:

Do not let light weight lift a horse unless at least one of these is true:

| Requirement | Why |
|---|---|
| Recent top-3 or close margin | Proves current form. |
| RT/L600 above race-class par | Proves speed. |
| Prize/class depth comparable to today | Proves grade compatibility. |
| Strong follow-up formline | Proves race strength. |

### Phase 4 - Recomputed Benchmark and Rendered Check

Run both:

```bash
python3 .agents/skills/au_racing/au_reflector/scripts/au_review_auto_weighting.py \
  --base-dir Archive_Race_Analysis/AU_Racing \
  --mode recomputed \
  --json
```

And, where relevant, compare against rendered artifacts because rendered baseline previously had:

| Metric | Rendered artifact baseline |
|---|---:|
| Good | 62 / 395 = 15.7% |
| Pass | 141 / 395 = 35.7% |
| Champion | 73 / 395 = 18.5% |

The target is not only to beat recomputed Pass 133. A useful mainline improvement should move toward or beyond rendered Pass 141 without sacrificing Good.

## Priority Recommendation

Do not tune class/weight weights first.

Priority order:

1. Fix or enrich extraction of past-run class-depth fields.
2. Add shadow `class_depth_score` from prize/venue/raw class where available.
3. Test narrow class x weight interaction.
4. Only then change the live `class_weight` formula.

This is more likely to improve analysis performance than moving the current additive weights, because current data is too thin and several proxy-only shadow tests already hurt Good/order quality.

## Phase 1 Implementation Update

Implemented on 2026-05-21:

| Change | Status |
|---|---|
| `au_race_extractor/scripts/extractor.py` now appends machine-readable `margin:` and `PF[...]` tokens to past-run Formguide lines when Racenet provides those fields. | Done |
| `PF[...]` includes `Last600`, `Runner Time`, race-time delta, runner pace label, race pace label, and RT-style L600 delta where available. | Done |
| Pace labels are sanitized from `V. Slow` to `V Slow` so the existing Facts parser reads the full label. | Done |
| `inject_fact_anchors.py` round-trip parser test confirms it can read the new tokens. | Done |
| Added `au_extraction_feature_audit.py` to quantify Formguide/Facts feature coverage. | Done |

Validation commands:

```bash
python3 -m py_compile \
  .agents/skills/au_racing/au_race_extractor/scripts/extractor.py \
  .agents/scripts/inject_fact_anchors.py \
  .agents/skills/au_racing/au_reflector/scripts/au_extraction_feature_audit.py

python3 .agents/skills/au_racing/au_reflector/scripts/au_extraction_feature_audit.py \
  --base-dir Archive_Race_Analysis/AU_Racing \
  --json
```

Current archive audit after the code change still shows 0% new-token coverage because archived Formguides have not been re-extracted. That is expected. The change affects newly extracted meetings and any archive folders we explicitly re-extract/rebuild.

## Phase 2 Shadow Test Update

Implemented on 2026-05-21:

| Change | Status |
|---|---|
| Ran a temporary prize-depth shadow harness to test current race prize vs past-run prize money as a class-depth proxy. | Done; harness removed after production integration |
| Production engine stayed unchanged during the shadow phase. | Yes |
| 395-race recomputed baseline rechecked after extraction patch. | Unchanged |

The temporary shadow harness and generated shadow reports were removed after the guarded rank-only prize-depth signal was baked into production.

Benchmark control after Phase 1:

| Metric | Result |
|---|---:|
| Champion | 67 |
| Gold | 14 |
| Good | 62 |
| Pass | 133 |
| Order Issue | 147 |

Prize-depth shadow results:

| Variant | Champion | Gold | Good | Pass | Order Issue | Decision |
|---|---:|---:|---:|---:|---:|---|
| baseline | 67 | 14 | 62 | 133 | 147 | Control |
| prize_depth_soft | 69 | 17 | 66 | 133 | 154 | Reject: order worsens |
| prize_weight_guard_soft | 70 | 17 | 69 | 135 | 154 | Reject: order worsens |
| prize_weight_guard_med | 71 | 17 | 67 | 136 | 152 | Promising, but order worsens |
| prize_positive_only_tiny | 72 | 14 | 66 | 139 | 150 | Best pass gain, but order +3 |
| prize_positive_only_soft | 71 | 14 | 69 | 137 | 149 | Best balance, but order +2 |
| prize_penalty_only_soft | 68 | 14 | 65 | 133 | 155 | Reject |

Conclusion:

Prize-depth is a real signal. It improves Champion, Good, Pass, MRR, and Avg Top4 Hits in the positive-only variants. However, it still worsens Order Issue slightly, which means it should not be promoted directly into live scoring yet.

Next refinement:

Test a constrained version that only uses prize-depth as a tie-break / confidence boost inside already-close score bands, rather than a free rerank delta. The goal is to keep the `prize_positive_only_soft` Good/Pass gain while preventing low-ranked horses from jumping into unstable 3rd/4th ordering positions.

## Production Integration Update

Implemented on 2026-05-22:

| Change | Status |
|---|---|
| Added positive-only `class_depth_rank_bonus` to AU production `RacingEngine`. | Done |
| Bonus affects `rank_score` only. `ability_score` and grade remain unchanged. | Done |
| Bonus is based on current prize vs latest / median last-3 past-run prize. | Done |
| Bonus is gated by baseline section quality: stability, form_line, and class_weight must all be at least 55. | Done |
| Bonus provenance is exposed via `class_depth_rank_bonus` and `class_depth_rank_bonus_detail`. | Done |

Production benchmark after integration:

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Champion | 67 | 71 | +4 |
| Gold | 14 | 14 | 0 |
| Good | 62 | 68 | +6 |
| Pass | 133 | 135 | +2 |
| MRR | 0.3046 | 0.3126 | +0.0080 |
| Order Issue | 147 | 149 | +2 |
| Avg Top4 Hits | 1.501 | 1.522 | +0.021 |

Decision:

Keep the production integration for now. It does not fully reproduce the best shadow Pass result, but it improves Champion, Good, Pass, MRR, and Avg Top4 Hits with only a small Order Issue tradeoff. The next improvement should target reducing Order Issue, not increasing prize-depth strength.
