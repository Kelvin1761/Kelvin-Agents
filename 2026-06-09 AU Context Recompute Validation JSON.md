# AU Context Recompute Validation

This report validates the context extraction rebuild by re-running the full Python engine from Logic + Facts. It does not write back meeting outputs.

## Data
- Result sources: `{'json': 129}`
- Recompute errors: `0`

## Context Audit

| Venue | Before races | Before going blank | Before profile blank | After races | After going blank | After profile blank | After barrier all-zero | Legacy barrier nonzero |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-04-17 Cranbourne Race 1-8 | 8 | 8 | 0 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-18 Randwick | 10 | 10 | 0 | 10 | 0 | 0 | 10 | 0 |
| 2026-04-22 Canterbury Race 1-8 | 8 | 8 | 0 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-25 Randwick Race 1-8 | 8 | 8 | 0 | 8 | 0 | 0 | 8 | 0 |
| Canterbury | 14 | 14 | 14 | 14 | 0 | 0 | 14 | 0 |
| Caulfield | 9 | 9 | 9 | 9 | 0 | 0 | 9 | 0 |
| Caulfield Heath | 8 | 8 | 8 | 8 | 0 | 0 | 8 | 0 |
| Doomben | 8 | 8 | 8 | 8 | 0 | 0 | 8 | 0 |
| Eagle Farm | 18 | 18 | 18 | 18 | 0 | 0 | 18 | 0 |
| Flemington | 9 | 9 | 9 | 9 | 0 | 0 | 9 | 0 |
| Randwick | 19 | 19 | 19 | 19 | 0 | 0 | 19 | 0 |
| Rosehill Gardens | 10 | 10 | 10 | 10 | 0 | 0 | 10 | 0 |

## All
- Races: **129**
- Baseline: Gold `8`, Good `44`, Pass `110`, Top3 win `56`, Top3 place `162/387`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 8 | 44 | 110 | 56 | 162 | 19 | 0.3733 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 8 | 51 | 112 | 59 | 171 | 17 | 0.3722 | 100 | G +0, Good +7, Pass +2, Win +3, Place +9 (+2.33pp), 0H -2, MRR -0.0011 |

### Changed Examples: all / context_recompute

- 2026-06-08 Canterbury Race 1-8 R3: `[7, 1, 8, 3]` -> `[8, 3, 1, 7]`
- 2026-06-08 Canterbury Race 1-8 R4: `[1, 6, 4, 5]` -> `[1, 4, 6, 7]`
- 2026-06-08 Canterbury Race 1-8 R5: `[3, 4, 8, 5]` -> `[3, 4, 8, 6]`
- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[10, 8, 5, 2]`
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 12, 11, 9]`

## Canterbury
- Races: **22**
- Baseline: Gold `1`, Good `10`, Pass `18`, Top3 win `10`, Top3 place `29/66`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 1 | 10 | 18 | 10 | 29 | 4 | 0.39 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 0 | 10 | 19 | 11 | 29 | 3 | 0.4051 | 16 | G -1, Good +0, Pass +1, Win +1, Place +0 (+0.00pp), 0H -1, MRR +0.0151 |

### Changed Examples: canterbury / context_recompute

- 2026-06-08 Canterbury Race 1-8 R3: `[7, 1, 8, 3]` -> `[8, 3, 1, 7]`
- 2026-06-08 Canterbury Race 1-8 R4: `[1, 6, 4, 5]` -> `[1, 4, 6, 7]`
- 2026-06-08 Canterbury Race 1-8 R5: `[3, 4, 8, 5]` -> `[3, 4, 8, 6]`
- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[10, 8, 5, 2]`
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 12, 11, 9]`

## Tight Turn
- Races: **47**
- Baseline: Gold `6`, Good `18`, Pass `42`, Top3 win `23`, Top3 place `66/141`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 6 | 18 | 42 | 23 | 66 | 5 | 0.4055 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 5 | 22 | 41 | 26 | 68 | 6 | 0.4272 | 35 | G -1, Good +4, Pass -1, Win +3, Place +2 (+1.42pp), 0H +1, MRR +0.0217 |

### Changed Examples: tight_turn / context_recompute

- 2026-06-08 Canterbury Race 1-8 R3: `[7, 1, 8, 3]` -> `[8, 3, 1, 7]`
- 2026-06-08 Canterbury Race 1-8 R4: `[1, 6, 4, 5]` -> `[1, 4, 6, 7]`
- 2026-06-08 Canterbury Race 1-8 R5: `[3, 4, 8, 5]` -> `[3, 4, 8, 6]`
- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[10, 8, 5, 2]`
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 12, 11, 9]`
