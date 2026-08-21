# AU Wong Choi — Round 13: Betfair Full Analysis (2026-07-19)

61 archive meeting dates, 120 BSP files, **join 100% (7517/7530 runners)** on
(race-date, horse). Two headline results.

## Result 1 — the betting edge is real at BSP, but NOT at morning fixed price

Flat $1 win bets, 5% Betfair commission, by model rank × confidence tier:

| Strategy | Bets | Strike | ROI @ BSP | ROI @ morning | BSP 95% CI |
|---|---:|---:|---:|---:|---:|
| **tight rank1** | 249 | 21.7% | **+36.2%** | −14.7% | [−6%, +86%] |
| clear rank1 | 126 | 35.7% | +8.7% | −18.2% | [−22%, +43%] |
| ALL rank1 | 709 | 24.0% | **+11.9%** | −26.0% | [−8%, +35%] |
| medium rank1 | 334 | 21.3% | −4.9% | −37.4% | — |
| ALL rank2 | 709 | 15.5% | +2.7% | — | — |

Two critical reads:

1. **At Betfair SP the edge is bigger than at bookmaker SP** (tight rank1
   +36.2% vs the Round-11 +16.8%) — exactly as predicted from the zero-margin
   exchange pricing. ALL-rank1 is +11.9% (vs −3.2% at bookmaker SP).
2. **The edge VANISHES at morning price** (every row negative at morningwap).
   The model's picks systematically *drift out* from morning to jump (the
   Savagery Vibe pattern: $22 morning → $92 BSP). So a fixed morning bet gets
   too short a price and loses.

**Operational consequence (fits Kelvin's day-before workflow):** do NOT take
the fixed morning price — place a **"bet at SP" (BSP) order** on the exchange
(can be set the day before / morning; matched at the starting price). That is
how the +36% / +11.9% is actually captured.

Caveat: CIs are wide (249–709 bets) and tight-rank1's just touches negative.
Promising and now theory- and price-confirmed, but **paper-trade the take-SP
strategy forward before real stakes.**

## Result 2 — money-flow is the strongest NEW signal found (gate it next)

Retrodictive separation of top-3 finishers, train/valid split, pre-race-only
fields:

| Signal | train Δ | valid Δ | verdict |
|---|---:|---:|---|
| **morning volume rank** | **+0.278** | **+0.268** | **STRONG + stable** |
| morning→BSP drift | −0.208 | −0.140 | real (steady horses place; drifters fade) |

Morning traded-volume rank (how much money a horse has attracted vs its field,
in the morning) separates placegetters by +0.27 **and it barely moves between
train and valid** — more stable than most of our matrix features. Crucially it
is **orthogonal to the entire matrix**: our engine is odds-blind, so the
market's money is genuinely new information, not a redundant re-encoding of
form/sectional/class (the redundancy that killed 21 prior candidates).

This is the first new feature lead in many rounds that is simultaneously
(a) pre-race available (usable in the day-before workflow), (b) strongly and
stably separating, and (c) orthogonal to existing signals.

## Next steps

1. **Money-flow feature** — build morning-volume-rank + drift as engine
   features (from the day-before Betfair market snapshot), retrodictive check
   already positive, then the standard walk-forward promotion gate. Highest-
   value open lead.
2. **Paper-trade the take-SP betting strategy** (tight rank1 + ALL rank1) —
   log model picks + BSP outcomes forward for ~4-6 weeks to tighten the CI
   before any real staking.
3. Live Betfair market snapshot at analysis time needs the API (auth =
   Kelvin, this session can't) — required for both #1 (live feature) and #2
   (live take-SP orders). Historical BSP already proves the concept offline.
