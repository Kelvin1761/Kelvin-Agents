# AU Wong Choi — Simplify + retune: honest holdout verdict (2026-07-24)

Kelvin's thesis: strip the micro-adjustments (AU has many vs HKJC) and re-tune
weights → cleaner model, easier to upgrade, hopefully better. Tested rigorously.

## Missing-data (缺數據假象) audit — Kelvin's worry is real

Default-60 (missing) rate per feature, 710-race archive:

| feature | % default | | feature | % default |
|---|---:|---|---|---:|
| pace_figure | 66.9% | | jockey_horse_fit | 18.0% |
| trainer | 40.0% | | weight | 6.2% |
| trial | 24.9% | | form | 5.8% |
| class | 22.5% | | rating/jockey/consistency/sectional/pace_map/track | ≤5% |

The heavily-defaulted features (pace_figure, trainer, trial, class, fit) are a
genuine noise source: a default 60 is treated as "average" but in a
field-relative sense it distorts when rivals have real values (the blindspot
winners' pace_figure=default artifact).

## The decisive test — per-fold optimism vs honest holdout

Per-fold re-optimization looked great (full+retuned g2 +8, miss -4). But that is
**optimization overfitting** — each fold got custom weights. The honest test
(tune ONE weight set on the earliest 60% of dates, evaluate on the unseen latest
40%) reverses it:

| HOLDOUT (316 races, never in tuning) | gp | g2 | top1 | wT3 | miss |
|---|---:|---:|---:|---:|---:|
| current (full, current weights) | 65 (20.6%) | 118 | 23.4% | 50.6% | 39 |
| full + retuned weights | 63 (19.9%) | 116 | 22.8% | 50.3% | 39 |
| **lean (weak features dropped) + retuned** | 61 (19.3%) | 114 | 23.1% | 50.6% | 37 |

- **Re-tuning weights: no honest OOS gain** — current weights already generalise
  well (confirms the earlier "weights well-tuned" finding; the +8 was overfit).
- **Removing the micro-adjustments: slightly WORSE** (gp −1.3pp, g2 −4, +2 fewer
  misses). The weak features collectively carry a little real signal.

## Honest answer to "will removing micro-adjustments improve performance?"

**No — a cleaner AU model performs slightly worse, not better** (~1.3pp gp / 4
g2 on 316 races ≈ 4 races). Kelvin's "remove 3 was better" was a per-fold
artifact. The micro-adjustments are not free noise; they net-contribute a bit.

## What this means for the clean-up decision

Two honest options, Kelvin's call (he said "a slight miss is fine" for a cleaner
model):
1. **Near-free clean-up (recommended):** neutralise weight_score (done —
   direction fix), remove `class_score` (validated 5/5 free), and retire the
   `form_line` dimension (already weight 0 = dead). ~0 performance cost, real
   maintainability win.
2. **Aggressive lean (also drop sectional + trial):** costs ~1.3pp gp / 4 g2 on
   holdout. Only worth it if maintainability is valued above that.

## The genuinely constructive direction for 缺數據假象

The fix for missing-data noise is NOT removal (removing loses signal) but better
MISSING-DATA HANDLING: when a feature is default for a horse, exclude it from the
field-relative comparison / down-weight it for that horse, instead of treating 60
as a real value. That targets the artifact without discarding the signal where it
exists. This is the next real experiment (a per-horse confidence/coverage weight),
distinct from feature removal.
