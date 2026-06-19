# AU Immediate Fix Shadow Test

This is a validation report only. No live scoring code or matrix weights were changed.

## Data
- Result sources: `{'historical_csv': 347}`

## Context Audit

| Venue | Races | Going blank | Track profile blank | Geometry blank | Barrier all-zero | Barrier nonzero |
|---|---:|---:|---:|---:|---:|---:|
| Randwick | 182 | 182 | 182 | 0 | 182 | 0 |
| Flemington | 141 | 141 | 141 | 0 | 140 | 1 |
| ** Rosehill Gardens | 18 | 18 | 0 | 0 | 18 | 0 |
| Eagle Farm | 18 | 18 | 18 | 0 | 18 | 0 |
| Doomben | 17 | 17 | 17 | 0 | 17 | 0 |
| ** Randwick | 10 | 10 | 0 | 0 | 10 | 0 |
| 2026-04-11 Randwick Race 1-10 | 10 | 10 | 0 | 0 | 10 | 0 |
| 2026-04-18 Randwick | 10 | 10 | 0 | 0 | 10 | 0 |
| Rosehill Gardens | 10 | 10 | 10 | 0 | 10 | 0 |
| Caulfield | 9 | 9 | 9 | 0 | 9 | 0 |
| ** Ballarat | 8 | 8 | 0 | 0 | 8 | 0 |
| ** Cranbourne | 8 | 8 | 0 | 0 | 8 | 0 |
| ** Sandown Lakeside | 8 | 8 | 0 | 0 | 8 | 0 |
| ** Warwick Farm | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-15 Warwick Farm Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-16 Pakenham Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-17 Cranbourne Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-22 Canterbury Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-23 Pakenham Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-25 Flemington Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-25 Randwick Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-29 Caulfield Heath Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| Ballarat | 8 | 8 | 8 | 0 | 8 | 0 |
| Caulfield Heath | 8 | 8 | 8 | 0 | 8 | 0 |
| Geelong | 8 | 8 | 8 | 0 | 8 | 0 |
| Gold Coast | 8 | 8 | 8 | 0 | 8 | 0 |
| Pakenham | 8 | 8 | 8 | 0 | 8 | 0 |
| Sale | 8 | 8 | 8 | 0 | 8 | 0 |
| Sandown Lakeside | 8 | 8 | 8 | 0 | 8 | 0 |
| ** Hawkesbury | 7 | 7 | 0 | 0 | 7 | 0 |
| 2026-04-24 Cranbourne Race 1-7 | 7 | 7 | 0 | 0 | 7 | 0 |
| Gosford | 7 | 7 | 7 | 0 | 7 | 0 |
| Warwick Farm | 7 | 0 | 0 | 0 | 7 | 0 |
| Canterbury | 6 | 6 | 6 | 0 | 6 | 0 |

## All
- Races: **347**
- Baseline: Gold `14`, Good `136`, Pass `294`, Top3 win `176`, Top3 place `444/1041`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 14 | 136 | 294 | 176 | 444 | 53 | 0.4313 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| existing_barrier_table | 10 | 122 | 283 | 162 | 415 | 64 | 0.4024 | 295 | G -4, Good -14, Pass -11, Win -14, Place -29 (-2.79pp), 0H +11, MRR -0.0289 |
| trial | 13 | 134 | 295 | 176 | 442 | 52 | 0.4126 | 119 | G -1, Good -2, Pass +1, Win +0, Place -2 (-0.19pp), 0H -1, MRR -0.0187 |
| geometry_canterbury | 14 | 136 | 294 | 176 | 444 | 53 | 0.4313 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| immediate_canterbury | 13 | 134 | 295 | 176 | 442 | 52 | 0.4126 | 119 | G -1, Good -2, Pass +1, Win +0, Place -2 (-0.19pp), 0H -1, MRR -0.0187 |
| geometry_tight | 14 | 136 | 294 | 176 | 444 | 53 | 0.4313 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| immediate_tight | 13 | 134 | 295 | 176 | 442 | 52 | 0.4126 | 119 | G -1, Good -2, Pass +1, Win +0, Place -2 (-0.19pp), 0H -1, MRR -0.0187 |
| comments | 14 | 136 | 294 | 176 | 444 | 53 | 0.4313 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| all | 9 | 116 | 283 | 161 | 408 | 64 | 0.3935 | 304 | G -5, Good -20, Pass -11, Win -15, Place -36 (-3.46pp), 0H +11, MRR -0.0378 |

### Example Reranks: all / existing_barrier_table

- 2025-08-02 Flemington Race 1-9 R1: `[2, 4, 1, 3]` -> `[2, 1, 4, 3]`
  - #2 Crossbow P1: existing_barrier:flemington_b5:+2.00
  - #1 Hillier P2: existing_barrier:flemington_b4:+2.50
  - #4 Exit P3: existing_barrier:flemington_b1:+1.00
  - #7 Fenestella P4: existing_barrier:flemington_b2:+0.50
- 2025-08-02 Flemington Race 1-9 R2: `[7, 6, 2, 4]` -> `[6, 2, 4, 7]`
  - #6 Bold Soul P1: existing_barrier:flemington_b7:+1.50
  - #2 Changingoftheguard P2: existing_barrier:flemington_b6:+3.00
  - #4 Wyclif P5: existing_barrier:flemington_b5:+2.00
  - #7 Muktamil P3: existing_barrier:flemington_b8:-1.50
- 2025-08-02 Flemington Race 1-9 R3: `[6, 10, 2, 15]` -> `[10, 2, 6, 18]`
  - #10 Prevailed P4: existing_barrier:flemington_b7:+1.50
  - #2 Capper Thirtynine P2: existing_barrier:flemington_b10:+1.00
  - #6 De Bergerac P1: existing_barrier:flemington_b8:-1.50
  - #18 Oak Park Rebel P8: existing_barrier:flemington_b6:+3.00
- 2025-08-02 Flemington Race 1-9 R4: `[2, 8, 6, 5]` -> `[2, 5, 4, 6]`
  - #2 Losesomewinmore P1: existing_barrier:flemington_b4:+2.50
  - #5 Veloce Carro P6: existing_barrier:flemington_b5:+2.00
  - #4 Mr Exclusive P10: existing_barrier:flemington_b6:+3.00
  - #6 Call To Glory P2: existing_barrier:flemington_b1:+1.00
- 2025-08-02 Flemington Race 1-9 R5: `[9, 1, 12, 14]` -> `[18, 9, 12, 14]`
  - #18 Maisy P3: existing_barrier:flemington_b5:+2.00
  - #12 Catani Gardens P7: existing_barrier:flemington_b1:+1.00
  - #14 Federer P2: existing_barrier:flemington_b2:+0.50
  - #1 Aztec State P5: existing_barrier:flemington_b9:-0.50

### Example Reranks: all / trial

- 2025-08-02 Flemington Race 1-9 R5: `[9, 1, 12, 14]` -> `[1, 9, 12, 14]`
  - #1 Aztec State P5: trial:trial_excellent_l600_33.84:+0.53
- 2025-08-02 Flemington Race 1-9 R6: `[7, 8, 6, 9]` -> `[7, 9, 8, 6]`
  - #9 Green Fly P4: trial:trial_excellent_l600_33.90:+0.53
- 2025-08-02 Flemington Race 1-9 R7: `[9, 2, 3, 10]` -> `[9, 2, 1, 3]`
  - #1 Joyful Fortune P10: trial:trial_excellent_l600_33.84:+0.53
- 2025-08-02 Flemington Race 1-9 R9: `[5, 17, 1, 4]` -> `[1, 5, 17, 4]`
  - #1 Stylish P1: trial:trial_excellent_l600_33.84:+0.51
- 2025-08-09 Randwick Race 1-10 R1: `[3, 2, 7, 1]` -> `[3, 2, 1, 7]`
  - #1 Tenderize P8: trial:trial_excellent_l600_33.90:+0.51

### Example Reranks: all / immediate_canterbury

- 2025-08-02 Flemington Race 1-9 R5: `[9, 1, 12, 14]` -> `[1, 9, 12, 14]`
  - #1 Aztec State P5: trial:trial_excellent_l600_33.84:+0.53
- 2025-08-02 Flemington Race 1-9 R6: `[7, 8, 6, 9]` -> `[7, 9, 8, 6]`
  - #9 Green Fly P4: trial:trial_excellent_l600_33.90:+0.53
- 2025-08-02 Flemington Race 1-9 R7: `[9, 2, 3, 10]` -> `[9, 2, 1, 3]`
  - #1 Joyful Fortune P10: trial:trial_excellent_l600_33.84:+0.53
- 2025-08-02 Flemington Race 1-9 R9: `[5, 17, 1, 4]` -> `[1, 5, 17, 4]`
  - #1 Stylish P1: trial:trial_excellent_l600_33.84:+0.51
- 2025-08-09 Randwick Race 1-10 R1: `[3, 2, 7, 1]` -> `[3, 2, 1, 7]`
  - #1 Tenderize P8: trial:trial_excellent_l600_33.90:+0.51

### Example Reranks: all / immediate_tight

- 2025-08-02 Flemington Race 1-9 R5: `[9, 1, 12, 14]` -> `[1, 9, 12, 14]`
  - #1 Aztec State P5: trial:trial_excellent_l600_33.84:+0.53
- 2025-08-02 Flemington Race 1-9 R6: `[7, 8, 6, 9]` -> `[7, 9, 8, 6]`
  - #9 Green Fly P4: trial:trial_excellent_l600_33.90:+0.53
- 2025-08-02 Flemington Race 1-9 R7: `[9, 2, 3, 10]` -> `[9, 2, 1, 3]`
  - #1 Joyful Fortune P10: trial:trial_excellent_l600_33.84:+0.53
- 2025-08-02 Flemington Race 1-9 R9: `[5, 17, 1, 4]` -> `[1, 5, 17, 4]`
  - #1 Stylish P1: trial:trial_excellent_l600_33.84:+0.51
- 2025-08-09 Randwick Race 1-10 R1: `[3, 2, 7, 1]` -> `[3, 2, 1, 7]`
  - #1 Tenderize P8: trial:trial_excellent_l600_33.90:+0.51

### Example Reranks: all / all

- 2025-08-02 Flemington Race 1-9 R1: `[2, 4, 1, 3]` -> `[2, 1, 4, 3]`
  - #2 Crossbow P1: existing_barrier:flemington_b5:+2.00
  - #1 Hillier P2: existing_barrier:flemington_b4:+2.50, trial:trial_excellent_l600_33.84:+0.60
  - #4 Exit P3: existing_barrier:flemington_b1:+1.00
  - #7 Fenestella P4: existing_barrier:flemington_b2:+0.50
- 2025-08-02 Flemington Race 1-9 R2: `[7, 6, 2, 4]` -> `[6, 2, 4, 7]`
  - #6 Bold Soul P1: existing_barrier:flemington_b7:+1.50
  - #2 Changingoftheguard P2: existing_barrier:flemington_b6:+3.00
  - #4 Wyclif P5: existing_barrier:flemington_b5:+2.00
  - #7 Muktamil P3: existing_barrier:flemington_b8:-1.50
- 2025-08-02 Flemington Race 1-9 R3: `[6, 10, 2, 15]` -> `[10, 2, 6, 18]`
  - #10 Prevailed P4: existing_barrier:flemington_b7:+1.50
  - #2 Capper Thirtynine P2: existing_barrier:flemington_b10:+1.00
  - #6 De Bergerac P1: existing_barrier:flemington_b8:-1.50
  - #18 Oak Park Rebel P8: existing_barrier:flemington_b6:+3.00
- 2025-08-02 Flemington Race 1-9 R4: `[2, 8, 6, 5]` -> `[2, 5, 4, 6]`
  - #2 Losesomewinmore P1: existing_barrier:flemington_b4:+2.50
  - #5 Veloce Carro P6: existing_barrier:flemington_b5:+2.00
  - #4 Mr Exclusive P10: existing_barrier:flemington_b6:+3.00
  - #6 Call To Glory P2: existing_barrier:flemington_b1:+1.00
- 2025-08-02 Flemington Race 1-9 R5: `[9, 1, 12, 14]` -> `[18, 9, 12, 1]`
  - #18 Maisy P3: existing_barrier:flemington_b5:+2.00
  - #12 Catani Gardens P7: existing_barrier:flemington_b1:+1.00
  - #1 Aztec State P5: existing_barrier:flemington_b9:-0.50, trial:trial_excellent_l600_33.84:+0.53
  - #14 Federer P2: existing_barrier:flemington_b2:+0.50

## Canterbury
- Races: **0**
- Baseline: Gold `0`, Good `0`, Pass `0`, Top3 win `0`, Top3 place `0/0`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| existing_barrier_table | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| trial | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| geometry_canterbury | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| immediate_canterbury | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| geometry_tight | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| immediate_tight | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| comments | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| all | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |

## Tight Turn
- Races: **0**
- Baseline: Gold `0`, Good `0`, Pass `0`, Top3 win `0`, Top3 place `0/0`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| existing_barrier_table | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| trial | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| geometry_canterbury | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| immediate_canterbury | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| geometry_tight | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| immediate_tight | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| comments | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| all | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
