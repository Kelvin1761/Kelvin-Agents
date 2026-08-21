# AU Wong Choi — Day-Before Market Data: Source Plan (2026-07-24)

Goal: operationalize the market signal (Round 14/15) in Kelvin's **day-before**
workflow, without compromising the odds-blind value radar (union, not blend).

## Two jobs, two price types

| Job | Needs | Price type |
|---|---|---|
| **Rescue/accuracy (union view)** — add the market fancies the model missed | market **RANK** only (ordinal) | bookmaker fixed odds are fine (rank = rank) |
| **Betting execution (overlay bets)** — the +36% take-SP edge | exchange price + money flow | **Betfair only** (edge needs zero-margin + BSP orders) |

## Source assessment (probed 2026-07-24)

| Source | Day-before odds? | Backtestable? | Auth | Best for |
|---|---|---|---|---|
| **Racenet** (existing pipeline) | YES — `Odd.price` / `Selection.odds` (bookmaker fixed) live on form-guide | NO (historical pages don't keep the day-before snapshot) | none | **rescue/accuracy rank** — build now |
| **Betfair historical BSP** | n/a (race-day) | YES — already proved the feature (gp 75→118) | none | offline validation (done) |
| **Betfair live API** | YES — exchange price + morning volume | forward only | **Kelvin** | **betting execution + money-flow feature** |
| Sportsbet | possible (bookmaker) | no | scraper TBD | fallback rank source; no AU racing scraper exists yet |

## Build sequence

1. **Racenet day-before market-rank collector (no auth, build now).** Extend
   the racenet pipeline to snapshot per-runner fixed odds at analysis time →
   `market_rank`. Feeds the **union shortlist** (model top-2 ∪ market top-3)
   and the **rescue layer** immediately. Validated in proxy by the BSP
   ordinal-rank blend (gp 75→118); confirm live racenet rank ≈ Betfair rank on
   the first few live meetings.
2. **Betfair API (set up together, Kelvin auth).** Unlocks: (a) exchange price
   for the take-SP overlay bets (+36% BSP edge), (b) morning traded-volume =
   the money-flow feature (Round 13, Δ+0.27 stable). This session cannot run
   the OAuth; Kelvin authorizes, then we wire the provider (tennis-wong-choi
   already has a `BetfairProvider` stub to extend).
3. **Forward paper-trade log.** From when collection starts: record model
   picks, market rank, and (Betfair) BSP outcome, to tighten the +36% CI
   before real stakes.

## Guardrail (Round 15)

The market is a RESCUE layer, never an override. Odds-blind value radar stays
unchanged (Savagery Vibe keeps rank #2). Union preserves disagreement; never
collapse model+market into one bet-list number.
