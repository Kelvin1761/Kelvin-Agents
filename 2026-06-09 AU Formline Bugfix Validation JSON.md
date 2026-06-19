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
| Canterbury | 14 | 6 | 6 | 14 | 0 | 0 | 14 | 0 |
| Caulfield | 9 | 9 | 9 | 9 | 0 | 0 | 9 | 0 |
| Caulfield Heath | 8 | 8 | 8 | 8 | 0 | 0 | 8 | 0 |
| Doomben | 8 | 8 | 8 | 8 | 0 | 0 | 8 | 0 |
| Eagle Farm | 18 | 18 | 18 | 18 | 0 | 0 | 18 | 0 |
| Flemington | 9 | 9 | 9 | 9 | 0 | 0 | 9 | 0 |
| Randwick | 19 | 19 | 19 | 19 | 0 | 0 | 19 | 0 |
| Rosehill Gardens | 10 | 10 | 10 | 10 | 0 | 0 | 10 | 0 |

## All
- Races: **129**
- Baseline: Gold `7`, Good `46`, Pass `110`, Top3 win `56`, Top3 place `163/387`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 7 | 46 | 110 | 56 | 163 | 19 | 0.3727 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 8 | 50 | 110 | 57 | 168 | 19 | 0.3681 | 97 | G +1, Good +4, Pass +0, Win +1, Place +5 (+1.29pp), 0H +0, MRR -0.0046 |

### Changed Examples: all / context_recompute

- 2025-09-06 Randwick Race 1-10 R2: `[5, 14, 19, 15]` -> `[5, 14, 16, 1]`
- 2025-09-06 Randwick Race 1-10 R5: `[2, 13, 12, 11]` -> `[13, 2, 12, 7]`
- 2025-09-06 Randwick Race 1-10 R6: `[1, 3, 4, 6]` -> `[1, 3, 16, 2]`
- 2025-09-06 Randwick Race 1-10 R7: `[1, 5, 2, 10]` -> `[5, 10, 2, 1]`
- 2025-09-06 Randwick Race 1-10 R9: `[17, 6, 15, 5]` -> `[17, 6, 5, 15]`

## Canterbury
- Races: **22**
- Baseline: Gold `0`, Good `12`, Pass `18`, Top3 win `10`, Top3 place `30/66`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 0 | 12 | 18 | 10 | 30 | 4 | 0.387 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 0 | 10 | 19 | 11 | 29 | 3 | 0.3961 | 12 | G +0, Good -2, Pass +1, Win +1, Place -1 (-1.52pp), 0H -1, MRR +0.0091 |

### Changed Examples: canterbury / context_recompute

- 2026-04-22 Canterbury Race 1-8 R1: `[2, 6, 3, 5]` -> `[2, 3, 6, 5]`
- 2026-04-22 Canterbury Race 1-8 R2: `[3, 1, 4, 9]` -> `[1, 3, 4, 9]`
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 7, 4, 11]`
- 2026-04-22 Canterbury Race 1-8 R4: `[2, 1, 6, 7]` -> `[2, 1, 3, 6]`
- 2026-04-22 Canterbury Race 1-8 R6: `[4, 10, 3, 5]` -> `[4, 10, 5, 3]`

## Tight Turn
- Races: **47**
- Baseline: Gold `5`, Good `20`, Pass `42`, Top3 win `23`, Top3 place `67/141`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 5 | 20 | 42 | 23 | 67 | 5 | 0.4041 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| context_recompute | 6 | 21 | 41 | 26 | 68 | 6 | 0.4134 | 30 | G +1, Good +1, Pass -1, Win +3, Place +1 (+0.71pp), 0H +1, MRR +0.0093 |

### Changed Examples: tight_turn / context_recompute

- 2026-04-17 Cranbourne Race 1-8 R1: `[6, 5, 4, 2]` -> `[5, 6, 4, 2]`
- 2026-04-17 Cranbourne Race 1-8 R2: `[8, 3, 9, 10]` -> `[8, 10, 3, 2]`
- 2026-04-17 Cranbourne Race 1-8 R3: `[10, 2, 11, 1]` -> `[10, 2, 3, 11]`
- 2026-04-17 Cranbourne Race 1-8 R4: `[2, 8, 3, 6]` -> `[2, 8, 6, 3]`
- 2026-04-17 Cranbourne Race 1-8 R6: `[7, 8, 6, 3]` -> `[7, 6, 3, 2]`
