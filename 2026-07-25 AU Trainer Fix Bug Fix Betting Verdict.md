# AU Wong Choi — 練馬師修復 / bug 修復 / 投注策略定案 (2026-07-25)

## #2 練馬師池修復 — SHIPPED
**Root cause:** `_trainer_score` looked the trainer up in a hand-curated
57-name CSV; anything outside fell to a flat neutral 60. Jockeys are 0% missing
(pool is concentrated, 60 names ≈ all rides) but the trainer pool is far wider,
so 22–72% of runners had no trainer signal — worsening (2026-07: 72%). This was
the single biggest coverage hole in the whole matrix.

**Fix:** unlisted trainers are now scored from their OWN last-year official
record (`trainer_ly`, already extracted but previously used only for narrative
text), empirical-Bayes shrunk toward the 30% field place-rate norm
(k=40, scale=34, capped ±9). Verified behaviour:

| unlisted trainer | 練馬師分 |
|---|---:|
| strong (60 rides, 45% place) | 63.1 |
| mid (30 rides, 30%) | 60.0 |
| weak (50 rides, 12%) | 56.6 |
| thin sample (<10 rides) | 60.0 (untouched) |

Monotonic, bounded, thin samples stay neutral. Tests:
`tests/test_trainer_empirical_fill.py`. Curated analyst tiers are never
overridden — the fill only applies where there was previously no signal at all.

## #1 結構性問題 + BUG FIXED
**Real bug found and fixed:** `_load_jockey_trainer_combo_stats()` read the
Drive-hosted CSV **unguarded** — when macOS revoked CloudStorage access
(PermissionError), the exception propagated and **crashed the entire scoring
run**. This was the cause of the 5 failing `test_auto_outputs` tests seen
earlier. Optional enrichment must never take the engine down; it now degrades
with a warning and scores without combo stats. **All 39 AU tests now pass**
(previously 5 failed).

**Structural observation:** `engine_core.py` is 4,987 lines / `renderer.py`
1,494 — large but coherently organised by feature scorer. The signal map
(`resources/06_signal_map.md` + `test_signal_map.py`) already locks the ranking
equation, which is the important structural guard. No further restructuring
attempted this round (behaviour-preserving refactors of a 5k-line scorer carry
more risk than benefit while everything is green).

## #4 Betting strategy — Kelvin's current approach is backwards (data)
Kelvin's strategy: take the top-2 picks, bet PLACE when place odds > 2 (both if
> 3). Backtested at Betfair place-market BSP, 5% commission, 710 races:

| strategy | bets | strike | ROI |
|---|---:|---:|---:|
| **Kelvin: rank1 place, odds > 2** | 335 | 30.1% | **−11.3%** |
| **Kelvin: rank1 place, odds > 3** | 167 | 18.0% | **−23.5%** |
| rank1 place, ALL | 706 | 49.6% | −5.8% |
| **rank1 place, market ALSO likes it (mkt top-3)** | 483 | **61.5%** | **−0.3%** |
| rank2 place, clear-tier + market likes | 69 | 60.9% | +1.9% |
| **WIN rank1 overlay (market rank > 6)** | 79 | 6.3% | **+58.9%** |
| **WIN rank2 overlay (market rank > 6)** | 125 | 4.0% | **+44.2%** |

**Why Kelvin's filter hurts: selecting for HIGH place odds is adverse
selection.** A top pick priced above 2.0 to place has only a 30% strike (vs
49.6% for all top picks) — the market prices it long *because it is genuinely
weaker*, and the market is better calibrated than our model at the short end.
Filtering for long odds systematically keeps the races where our model is wrong.

**Better strategies (both data-backed):**
1. **For place betting — invert the filter:** back the top pick to place only
   when the market ALSO rates it top-3 (61.5% strike, break-even at BSP, and
   clearly profitable at bookmaker place odds if you can beat BSP). Kelvin's
   "spotting horses that place" goal is best served by agreement, not by
   chasing price.
2. **For profit — WIN bets on overlays:** model top-2 that the market ranks
   outside its top 6 (+59% / +44% ROI, 79–125 bets). Low strike (4–6%) so it
   needs bankroll discipline and take-SP execution, but it is where the
   model's independent edge actually converts to money.

Caveat: overlay samples are 79–125 bets with wide variance; paper-trade before
sizing up. But the sign is consistent with every earlier finding (the edge lives
in model-vs-market disagreement, not in the model's confident picks).
