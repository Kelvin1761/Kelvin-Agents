# AU Context Recompute Validation

This report validates the context extraction rebuild by re-running the full Python engine from Logic + Facts. It does not write back meeting outputs.

## Data
- Result sources: `{'historical_csv': 347}`
- Recompute errors: `0`

## Context Audit

| Venue | Before races | Before going blank | Before profile blank | After races | After going blank | After profile blank | After barrier all-zero | Legacy barrier nonzero |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ** Ballarat | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| ** Cranbourne | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| ** Hawkesbury | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| ** Randwick | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 0 |
| ** Rosehill Gardens | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 |
| ** Sandown Lakeside | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| ** Warwick Farm | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-04-11 Randwick Race 1-10 | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 0 |
| 2026-04-15 Warwick Farm Race 1-8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-04-16 Pakenham Race 1-8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-04-17 Cranbourne Race 1-8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-04-18 Randwick | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 0 |
| 2026-04-22 Canterbury Race 1-8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-04-23 Pakenham Race 1-8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-04-24 Cranbourne Race 1-7 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-04-25 Flemington Race 1-8 | 8 | 8 | 0 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-25 Randwick Race 1-8 | 8 | 8 | 0 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-29 Caulfield Heath Race 1-8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| Ballarat | 8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| Canterbury | 14 | 14 | 14 | 0 | 0 | 0 | 0 | 0 |
| Caulfield | 9 | 9 | 9 | 0 | 0 | 0 | 0 | 0 |
| Caulfield Heath | 8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| Doomben | 17 | 17 | 17 | 0 | 0 | 0 | 0 | 0 |
| Eagle Farm | 18 | 18 | 18 | 0 | 0 | 0 | 0 | 0 |
| Flemington | 141 | 141 | 141 | 139 | 0 | 0 | 139 | 0 |
| Geelong | 8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| Gold Coast | 8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| Gosford | 7 | 7 | 7 | 0 | 0 | 0 | 0 | 0 |
| Kensington | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Pakenham | 8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| Randwick | 182 | 182 | 182 | 162 | 0 | 0 | 162 | 0 |
| Rosehill Gardens | 10 | 10 | 10 | 0 | 0 | 0 | 0 | 0 |
| Sale | 8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| Sandown Lakeside | 8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| Warwick Farm | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## All
- Races: **347**
- Baseline: Gold `14`, Good `136`, Pass `294`, Top3 win `176`, Top3 place `444/1041`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 14 | 136 | 294 | 176 | 444 | 53 | 0.4313 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 13 | 136 | 294 | 164 | 443 | 53 | 0.4061 | 296 | G -1, Good +0, Pass +0, Win -12, Place -1 (-0.10pp), 0H +0, MRR -0.0252 |

### Changed Examples: all / context_recompute

- 2025-08-02 Flemington Race 1-9 R1: `[2, 4, 1, 3]` -> `[2, 3, 4, 1]`
- 2025-08-02 Flemington Race 1-9 R2: `[7, 6, 2, 4]` -> `[7, 6, 8, 4]`
- 2025-08-02 Flemington Race 1-9 R3: `[6, 10, 2, 15]` -> `[6, 2, 10, 15]`
- 2025-08-02 Flemington Race 1-9 R4: `[2, 8, 6, 5]` -> `[2, 8, 3, 6]`
- 2025-08-02 Flemington Race 1-9 R6: `[7, 8, 6, 9]` -> `[7, 6, 2, 8]`

## Canterbury
- Races: **0**
- Baseline: Gold `0`, Good `0`, Pass `0`, Top3 win `0`, Top3 place `0/0`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |

## Tight Turn
- Races: **0**
- Baseline: Gold `0`, Good `0`, Pass `0`, Top3 win `0`, Top3 place `0/0`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
