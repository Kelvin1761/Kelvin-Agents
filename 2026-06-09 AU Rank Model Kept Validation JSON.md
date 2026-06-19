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
| context_recompute | 9 | 51 | 112 | 60 | 172 | 17 | 0.3697 | 100 | G +1, Good +7, Pass +2, Win +4, Place +10 (+2.58pp), 0H -2, MRR -0.0036 |

### Changed Examples: all / context_recompute

- 2026-06-08 Canterbury Race 1-8 R3: `[7, 1, 8, 3]` -> `[8, 3, 1, 7]`
- 2026-06-08 Canterbury Race 1-8 R4: `[1, 6, 4, 5]` -> `[1, 4, 6, 7]`
- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 5, 10, 2]`
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 12, 5, 11]`
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[6, 11, 8, 3]`

## Canterbury
- Races: **22**
- Baseline: Gold `1`, Good `10`, Pass `18`, Top3 win `10`, Top3 place `29/66`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 1 | 10 | 18 | 10 | 29 | 4 | 0.39 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 1 | 10 | 19 | 12 | 30 | 3 | 0.4066 | 17 | G +0, Good +0, Pass +1, Win +2, Place +1 (+1.52pp), 0H -1, MRR +0.0166 |

### Changed Examples: canterbury / context_recompute

- 2026-06-08 Canterbury Race 1-8 R3: `[7, 1, 8, 3]` -> `[8, 3, 1, 7]`
- 2026-06-08 Canterbury Race 1-8 R4: `[1, 6, 4, 5]` -> `[1, 4, 6, 7]`
- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 5, 10, 2]`
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 12, 5, 11]`
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[6, 11, 8, 3]`

## Tight Turn
- Races: **47**
- Baseline: Gold `6`, Good `18`, Pass `42`, Top3 win `23`, Top3 place `66/141`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 6 | 18 | 42 | 23 | 66 | 5 | 0.4055 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 7 | 21 | 41 | 27 | 69 | 6 | 0.4143 | 34 | G +1, Good +3, Pass -1, Win +4, Place +3 (+2.13pp), 0H +1, MRR +0.0088 |

### Changed Examples: tight_turn / context_recompute

- 2026-06-08 Canterbury Race 1-8 R3: `[7, 1, 8, 3]` -> `[8, 3, 1, 7]`
- 2026-06-08 Canterbury Race 1-8 R4: `[1, 6, 4, 5]` -> `[1, 4, 6, 7]`
- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 5, 10, 2]`
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 12, 5, 11]`
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[6, 11, 8, 3]`
