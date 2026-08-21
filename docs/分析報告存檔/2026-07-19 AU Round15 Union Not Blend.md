# AU Wong Choi — Round 15: Union, Not Blend (2026-07-19)

Kelvin's question: does the consensus/market view compromise the odds and miss
horses like Savagery Vibe? **Yes — if you BLEND into one number. No — if you
UNION two shortlists.** Data-backed answer below.

## The blend DOES lose Savagery Vibe (Kelvin was right)

Eagle Farm 05-30 R9, Savagery Vibe ($71 winner):
- model rank **2** (value view) → blended-rank **11** (consensus view).
Blending averages the model and the market into one score, which destroys the
very disagreement that made Savagery Vibe findable. A blended re-rank is an
ACCURACY tool only — never a bet list.

## The fix: UNION the two shortlists (preserves disagreement)

`shortlist = model top-2  ∪  market top-3` (~3.8 horses), archive-wide (697 races):

| Shortlist | placegetters covered (of 3) |
|---|---:|
| model top-3 alone | 1.33 |
| market top-3 alone | 1.60 |
| **UNION (model top2 ∪ market top3)** | **1.79** |

- Covers MORE placegetters than either source alone, in ~4 horses.
- **Model-top2 / market-hated WINNERS (Savagery Vibe type): 28 in archive,
  kept by union = 28 (100%).** Every longshot the model uniquely catches is
  retained, because model top-2 is always included.

## So the architecture (no compromise)

Keep the disagreement as first-class; never average it away:

1. **Value / bet radar (unchanged odds-blind engine):** model top picks. When
   the model rates a horse well ABOVE its market rank → overlay (Savagery Vibe,
   take-SP bet, +36% BSP edge). This is untouched — Savagery Vibe stays #2.
2. **Rescue layer (market, day-before rank):** horses the market fancies that
   the model ranks >4 — the 53%-place group we currently miss. Add these to the
   shortlist (union), do NOT let them demote the model's own picks.
3. **Consensus/blend number:** optional dashboard readout of "most likely
   placegetters" — high accuracy, but explicitly labelled NOT the bet list.

The union shortlist IS the confidence-radar (already shipped) widened by market
rescue. Savagery Vibe is caught by (1); She's Got Pizzazz type is caught by (2);
neither is lost.

## Takeaway

The market's value is in RESCUING horses the model missed, not in OVERRIDING
horses the model uniquely likes. Union adds the first without paying the second.
Needs the day-before market rank per runner (Betfair API / day-before Racenet).
