# AU Wong Choi — Ordering / Favourite / Maiden Review (2026-07-17, round 3)

> Follow-up to the evidence-enrichment adoption. Addresses Kelvin's four
> observations: (1) placegetters caught in top-4 but not top-2; (2) missed
> market favourites; (3) lightly-raced maidens with strong trials; (4)
> optional Racenet data expansion. All tests on the refreshed (post-adoption)
> archive, expanding-date walk-forward, canonical metrics.

## 1. Ordering: top-4 catches, top-2 misses — real, but not arithmetic-fixable

- 45.4% of races have ≥2 placegetters inside the model top-4; only 19.2% have
  them as picks 1+2 → **40.1% of races are ordering opportunities**.
- Within the top-4, actual placegetters beat non-placegetters on
  class_weight (+0.67), race_shape (+0.49), jockey_trainer (+0.36) and lose
  on stability (−1.83) — the stability-heavy weights that pick the shortlist
  hurt ordering inside it.
- **Two-stage shortlist re-rank tested (honest per-fold direction learning +
  parameter selection): FAIL** — OOS positional Good −1.10pp, 3/5 folds
  (`scratch/au_shortlist_rerank_test.py`). The matrix deltas do not carry
  reliable ordering signal out-of-sample; per-fold selection kept choosing the
  largest tilt and overfitting train.
- Conclusion: fixing ordering needs **new features**, not re-weighted old ones
  — head-to-head 賽績線 comparisons, last-start beaten margins, and sectional
  differentials between shortlist horses are the natural candidates (they live
  in Facts text and would need engine feature engineering + archive re-score).

## 2. Missed market favourites — diagnosed; same root cause as the maiden issue

SP used for diagnosis only (never as a model input). 710 races with SP:

- Favourite finishes top-3 **67.0%** (wins 34.8%). The model already has the
  favourite in its own top-3 **69.6%** of the time.
- The failure slice: favourite finishes top-3 but model ranks it >3 —
  **133 races (18.7%)**, mostly ranks 4–5 (81 of 133).
- Feature profile of those missed placing favourites vs our top-2:
  **trial_score +4.2, jockey_score +3.4, rating +1.4** versus
  **consistency −11.0, stability −9.9, form −9.1, sectional −6.7**.

Reading: the market is backing **lightly-raced horses with strong trials and
top stables/jockeys**; the engine punishes the missing racing history as if it
were evidence of weakness. This is exactly observation (3).

## 3. Trial-backed stability compensation — tested, FAIL / HOLD

Trigger: `formal_count ≤ 2` and `trial_score > 60` (1,048 horses across the
archive — real support, unlike the 2026-07-16 strict recency gate).
Action: `mx_stability += β·(trial_score−60)`, capped.

- Per-fold selected (β=0.6, cap=8): Gold +4, Miss −1, Top3 +0.8pp,
  W-in-T3 +1.1pp — but positional Good −1.38pp → **FAIL**.
- Conservative fixed variants (β=0.2/0.4, cap=4): neutral (gp −0.8…0.0pp,
  small gold/miss gains). No variant clears +1.5pp
  (`scratch/au_trial_backed_stability_test.py`).

The compensation improves shortlist quality but degrades exact top-2 ordering
— consistent with §1: the archive's current features cannot order the
front of the field better than ability_score already does.

## 4. SHIPPED instead: confidence-tiered betting radar (no scoring change)

Since top-2 precision cannot honestly be lifted by arithmetic, the betting
radar now adapts to measured confidence (`ensure_verdict` in
`racing_engine/renderer.py`, archive-calibrated on 710 races):

| Tier (top1−top3 ability gap) | Races | ≥2 placers in Top2 | in Top4 | in Top5 | Winner in Top2 | in Top5 |
|---|---:|---:|---:|---:|---:|---:|
| tight (<2 pts) | 249 | **13%** | 55% | **72%** | 37% | 71% |
| medium (2–5) | 335 | 21% | 61% | 75% | 37% | 73% |
| clear (≥5) | 126 | 25% | 65% | 78% | **51%** | 80% |

- **tight** → radar widens to Top-5 (rank 5 upgraded to WATCH), report shows
  「分數擠迫 — 圍捕：Top 5 同級睇待」.
- **medium/clear** → standard Top-2 + Top-4 radar; clear races flagged as
  strong Top-2 signals.
- Verdict JSON now carries `confidence_tier` / `top1_top3_gap` /
  `radar_size` / `radar` for the dashboard. Tests:
  `tests/test_confidence_radar.py`.

## 5. Racenet data expansion — deferred deliberately

The bottleneck is **feature information content, not sample size**: 710 races
were enough to prove the current matrix carries no OOS ordering signal, and
the J/T empirical-fill failure was about per-name ride counts (would need a
results database several times larger — a slow-accumulation job, not a
one-session scrape). Racenet extraction is high-risk (fragile site, blocking
danger flagged by Kelvin) and is only worth spending that risk budget on when
a candidate specifically needs the data. Recommended instead: let the daily
pipeline accumulate results organically, and extract new meetings through the
existing extractor flow at its natural pace.

## Next candidates (priority order)

1. **Head-to-head ordering features** (賽績線 rematch strength, last-start
   beaten margin vs shortlist rivals, sectional differentials) — engine
   feature engineering + archive re-score; targets the 40% ordering
   opportunity, the missed-favourite slice, and positional Good directly.
2. Maiden/lightly-raced handling revisit **after** ordering features land
   (trial evidence needs a comparative frame, not a stability bonus).
3. pace_figure coverage grows organically; revisit pace_perf weighting when
   material.
