# AU Wong Choi — Round 14: The Market Signal (2026-07-19)

The Betfair work converged on the single biggest lever found in the whole
project — and a strategic fork. All respects Kelvin's **day-before** workflow.

## The market is a far better predictor than our (odds-blind) model

Top-3 hit rate by rank signal (61 dates, 100% join):

| Rank | our MODEL | market PRICE | market VOLUME |
|---|---:|---:|---:|
| 1 | 50% | **68%** | 68% |
| 2 | 43% | 52% | 52% |
| 3 | 41% | 41% | 45% |

Price-rank and volume-rank are the same signal (the money and the price encode
the same fancy ordering). When model and market **disagree**:
- market top-2 / model ranks >4 → **53%** place (market right)
- model top-2 / market ranks >4 → **21%** place (we're usually wrong)

Our engine is completely odds-blind, so it throws away the strongest single
predictor available.

## Blending the market in ~doubles accuracy (OOS 363 races)

`score = z(model) + w · market`:

| w | pos-Good | any-2 | Miss | W-in-T3 | Top3 prec |
|---:|---:|---:|---:|---:|---:|
| 0 (model only) | 75 | 149 | 43 | 52.9% | 45.1% |
| 1.5 (exact 1/BSP) | 126 | 204 | 21 | 63.9% | 53.3% |
| 1.5 (**ordinal rank**) | 118 | 199 | 30 | 62.0% | 51.9% |

- Bigger than every prior improvement combined (pos-Good +51, W-in-T3 +11pp,
  Miss halved).
- **Day-before-robust:** using only the coarse market *rank* (which even a thin
  day-before market establishes) keeps most of the gain (gp 75→118). Exact BSP
  is an upper bound not available day-before; ordinal rank is the realistic
  floor and it is still huge.

## The strategic fork (this is the key decision)

The market is efficiently priced, so the same signal that maximizes ACCURACY
destroys BETTING VALUE:

| Goal | Model design | Payoff |
|---|---|---|
| **Accurate tips / dashboard** ("who will place") | blend market rank in | pos-Good ~doubles, W-in-T3 → 62% |
| **Betting profit** (find overlays) | keep model **odds-blind**, bet the *disagreements* | tight-rank1 +36% at BSP (Round 13); lives in model♥/market✗ spots |

Blending toward the market makes the model agree with the market → accurate but
no betting edge (you'd back efficiently-priced favourites). The +36% edge is in
the 21%-strike / high-price disagreements (Savagery Vibe: model #2, market $92,
won). **You cannot maximize both in one number.**

## Recommendation — run BOTH views (both day-before-feasible)

1. **Consensus view** (new): model blended with the day-before market rank →
   the honest "most likely placegetters" shortlist for the dashboard. Best
   accuracy the data allows.
2. **Value view** (keep current odds-blind engine): flag horses the model
   rates well above their day-before market rank → the betting-overlay radar
   (place take-SP orders per Round 13).
   The confidence-tier radar already shipped pairs naturally with this.

## What this needs (Kelvin owns the data feed)

- A **day-before market snapshot** per runner (Betfair price/rank + volume),
  captured at analysis time. Historical BSP proved the concept offline; the
  live day-before feed needs the Betfair API (auth = Kelvin) or a day-before
  Racenet market scrape.
- Then: build market-rank + volume-rank + model-vs-market-gap as engine
  inputs, run the standard walk-forward gate, and split the two views above.

This is the highest-value open direction by a wide margin — but the gain is
"become as good as the market," and the *profit* still comes from disciplined
disagreement, not from following it.
