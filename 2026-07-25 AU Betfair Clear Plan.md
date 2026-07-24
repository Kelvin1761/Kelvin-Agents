# AU Wong Choi — Using Betfair / Odds: the CLEAR plan (2026-07-25)

Written to remove the confusion from earlier proposals. One core rule, three
defined uses, one decision table. No ambiguity.

## THE CORE RULE (never broken)
**The model score never changes. Odds are a SEPARATE column shown beside it.
We never merge model + odds into one number.**

Why: mixing them destroys the model's only edge. Proof — when we blended odds
into the score, the $71 winner Savagery Vibe dropped from model rank #2 to #11.
The value is in the DISAGREEMENT between an odds-blind model and the market;
averaging them erases it.

So we do NOT "balance the scoring between model and odds." There is no balance
knob in the score. The model stands alone (odds-blind, keeps improving on its
own data). Odds live in their own column. The balance is a DECISION you make
per horse, not a formula in the number.

## THREE defined uses of the odds column (all reference/decision, not scoring)

| # | Use | Rule (model rank vs market rank) | What it's for |
|---|---|---|---|
| 1 | **Confidence** | model & market both top-3 = ✅ agree | reading: high-confidence placers |
| 2 | **Overlay bet** | model top-4 BUT market > 6 | BETTING: the value bet (Savagery Vibe); +36% BSP edge lives here |
| 3 | **Blind-spot alert** | market top-2 BUT model > 5 | LEARNING: market knows something; manual review, do NOT auto-follow |

The model ranking (綜合戰力分) is exactly what it is today. The odds column just
adds a market-rank number + a zone tag (✅ / 💰overlay / ⚠blindspot) next to each
horse. Nothing in the score moves.

## How it improves performance WITHOUT becoming an odds-reader
- **Analysis performance** (who places): stays 100% the odds-blind model. The
  odds column is reference only — it does not change which horses the model
  rates. Reading the odds alone can't find overlays; you need the independent
  model to know when the market is wrong. That is why we keep building the
  model on its own (data/coverage/features) — the odds do not "improve the
  model", they improve your BETTING DECISIONS on top of it.
- **Betting performance** (making money): comes from Use #2 (overlays). Backtest
  proved tight/clear-tier model-top picks the market underrates return +36% at
  Betfair SP. That edge exists ONLY because the model is odds-blind.

## Implementation — 3 phases, clear ownership

**Phase 1 — DONE (offline proof):** historical Betfair BSP validated the overlay
edge (+36% tight-rank1, +11.9% all-rank1 at BSP). Confirmed the concept.

**Phase 2 — day-before ODDS COLUMN (free, no auth, buildable now):**
racenet live fixed-odds (already confirmed available: Selection.odds →
OddPrice.value) → `market_rank` per horse the day before → add the 3-zone column
to the report. `au_market_zones.py` already does this (BSP source now; swap in
racenet-live source). Pure display; model untouched; you get the overlay +
blind-spot flags on every card.

**Phase 3 — betting execution (needs Kelvin's Betfair API key):**
for Use #2 overlays, place "bet at Betfair SP" orders (settable the day before,
matched at the starting price — that is how the +36% is captured; morning fixed
price does NOT capture it). Paper-trade forward ~4-6 weeks first to confirm the
edge live before real stakes.

## One-line summary for Kelvin
Model = your independent opinion (never touches odds). Odds = a second column
that tells you (1) when to be confident, (2) when to bet an overlay, (3) when to
double-check a blind spot. You read both; you never blend them. The model keeps
improving on data; the odds make your betting decisions sharper.
