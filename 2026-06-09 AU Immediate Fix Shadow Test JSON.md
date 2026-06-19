# AU Immediate Fix Shadow Test

This is a validation report only. No live scoring code or matrix weights were changed.

## Data
- Result sources: `{'json': 129}`

## Context Audit

| Venue | Races | Going blank | Track profile blank | Geometry blank | Barrier all-zero | Barrier nonzero |
|---|---:|---:|---:|---:|---:|---:|
| Randwick | 19 | 19 | 19 | 0 | 19 | 0 |
| Eagle Farm | 18 | 18 | 18 | 0 | 18 | 0 |
| Canterbury | 14 | 14 | 14 | 0 | 14 | 0 |
| 2026-04-18 Randwick | 10 | 10 | 0 | 0 | 10 | 0 |
| Rosehill Gardens | 10 | 10 | 10 | 0 | 10 | 0 |
| Caulfield | 9 | 9 | 9 | 0 | 9 | 0 |
| Flemington | 9 | 9 | 9 | 0 | 9 | 0 |
| 2026-04-17 Cranbourne Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-22 Canterbury Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| 2026-04-25 Randwick Race 1-8 | 8 | 8 | 0 | 0 | 8 | 0 |
| Caulfield Heath | 8 | 8 | 8 | 0 | 8 | 0 |
| Doomben | 8 | 8 | 8 | 0 | 8 | 0 |

## All
- Races: **129**
- Baseline: Gold `8`, Good `44`, Pass `110`, Top3 win `56`, Top3 place `162/387`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 8 | 44 | 110 | 56 | 162 | 19 | 0.3733 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| existing_barrier_table | 8 | 47 | 106 | 54 | 161 | 23 | 0.3724 | 24 | G +0, Good +3, Pass -4, Win -2, Place -1 (-0.26pp), 0H +4, MRR -0.0009 |
| trial | 7 | 44 | 110 | 56 | 161 | 19 | 0.3711 | 20 | G -1, Good +0, Pass +0, Win +0, Place -1 (-0.26pp), 0H +0, MRR -0.0022 |
| geometry_canterbury | 7 | 44 | 109 | 56 | 160 | 20 | 0.3729 | 9 | G -1, Good +0, Pass -1, Win +0, Place -2 (-0.52pp), 0H +1, MRR -0.0004 |
| immediate_canterbury | 7 | 44 | 109 | 57 | 160 | 20 | 0.3718 | 24 | G -1, Good +0, Pass -1, Win +1, Place -2 (-0.52pp), 0H +1, MRR -0.0015 |
| geometry_tight | 6 | 46 | 109 | 57 | 161 | 20 | 0.3738 | 22 | G -2, Good +2, Pass -1, Win +1, Place -1 (-0.26pp), 0H +1, MRR +0.0005 |
| immediate_tight | 6 | 46 | 109 | 58 | 161 | 20 | 0.3727 | 36 | G -2, Good +2, Pass -1, Win +2, Place -1 (-0.26pp), 0H +1, MRR -0.0006 |
| comments | 8 | 44 | 109 | 56 | 161 | 20 | 0.3721 | 9 | G +0, Good +0, Pass -1, Win +0, Place -1 (-0.26pp), 0H +1, MRR -0.0012 |
| all | 6 | 48 | 104 | 54 | 158 | 25 | 0.372 | 60 | G -2, Good +4, Pass -6, Win -2, Place -4 (-1.03pp), 0H +6, MRR -0.0013 |

### Example Reranks: all / existing_barrier_table

- 2025-09-06 Randwick Race 1-10 R2: `[5, 14, 19, 15]` -> `[5, 2, 10, 19]`
  - #5 So Magnificent P1: existing_barrier:randwick_b1:+1.50
  - #10 Calido Magic P5: existing_barrier:randwick_b2:+1.50
  - #19 Graceful Ellen P13: existing_barrier:randwick_b12:-3.00
  - #15 Zumbo P2: existing_barrier:randwick_b10:-2.50
- 2025-09-06 Randwick Race 1-10 R3: `[7, 9, 10, 2]` -> `[7, 9, 10, 8]`
  - #7 Monte Supreme P1: existing_barrier:randwick_b4:+3.00
  - #9 Chidiac P2: existing_barrier:randwick_b3:+3.00
  - #10 Spirit Of Wealth P6: existing_barrier:randwick_b1:+1.50
  - #8 Island Dec P5: existing_barrier:randwick_b5:+1.50
- 2025-09-06 Randwick Race 1-10 R5: `[2, 13, 12, 11]` -> `[2, 13, 7, 12]`
  - #2 Flying Bandit P6: existing_barrier:randwick_b4:+3.00
  - #13 Shohisha P1: existing_barrier:randwick_b5:+1.50
  - #7 Time Quest P4: existing_barrier:randwick_b2:+1.50
  - #4 Highlights P9: existing_barrier:randwick_b3:+3.00
- 2025-09-06 Randwick Race 1-10 R6: `[1, 3, 4, 6]` -> `[3, 1, 4, 16]`
  - #3 Savvy Hallie P3: existing_barrier:randwick_b5:+1.50
  - #1 Within The Law P5: existing_barrier:randwick_b13:-2.50
  - #4 Memo P9: existing_barrier:randwick_b2:+1.50
  - #16 Apocalyptic P1: existing_barrier:randwick_b1:+1.50
- 2025-09-06 Randwick Race 1-10 R7: `[1, 5, 2, 10]` -> `[1, 2, 10, 5]`
  - #1 Arapaho P6: existing_barrier:randwick_b4:+3.00
  - #2 Ceolwulf P4: existing_barrier:randwick_b2:+1.50
  - #10 Birdman P5: existing_barrier:randwick_b1:+1.50
  - #5 Sir Delius P2: existing_barrier:randwick_b10:-2.50

### Example Reranks: all / trial

- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 7, 9]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 11, 3, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05
- 2025-09-13 Flemington Race 1-10 R4: `[4, 9, 10, 3]` -> `[10, 4, 9, 3]`
  - #10 Castlejohn P-1: trial:trial_extreme_l600_33.43:+3.32
- 2026-04-18 Randwick R1: `[13, 14, 10, 9]` -> `[10, 13, 14, 9]`
  - #10 Danish Prince P6: trial:trial_excellent_l600_33.65:+0.51
  - #9 Cosmeena P8: trial:trial_excellent_l600_33.84:+0.51
  - #4 Audrey's Lane P3: trial:trial_excellent_l600_33.90:+0.51
- 2026-04-18 Randwick R4: `[1, 9, 4, 11]` -> `[9, 4, 1, 11]`
  - #9 Beside The Ocean P4: trial:trial_excellent_l600_33.84:+0.53
  - #4 Tomato Toastie P8: trial:trial_excellent_l600_33.90:+0.53

### Example Reranks: all / geometry_canterbury

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_ctb:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_ctb:wide:-0.40
  - #5 Tenderize P3: geo_ctb:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 11, 12]`
  - #2 Celui P7: geo_ctb:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_ctb:low_draw+position_geometry:+0.40
  - #9 Dollar Magic P4: geo_ctb:inside+position_geometry:+0.65
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[11, 3, 8, 6]`
  - #3 Love Shuck P4: geo_ctb:low_draw+position_geometry:+0.40
  - #6 Laurel Hill P6: geo_ctb:inside+position_geometry:+0.65
  - #1 Mafia P2: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 3, 7, 1]`
  - #13 Pink Persuasion P3: geo_ctb:low_draw+position_geometry:+0.40
  - #3 Graffiti Tycoon P2: geo_ctb:inside+position_geometry:+0.65
  - #7 Salt Spray P6: geo_ctb:wide:-0.40
  - #1 Adenauer P5: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R5: `[1, 2, 9, 7]` -> `[1, 9, 2, 5]`
  - #1 Erin Jo P5: geo_ctb:low_draw+position_geometry:+0.40
  - #9 Nymphadora P8: geo_ctb:inside+position_geometry:+0.65
  - #5 Superfabulistic P2: geo_ctb:inside+position_geometry:+0.65

### Example Reranks: all / immediate_canterbury

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_ctb:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_ctb:wide:-0.40
  - #5 Tenderize P3: geo_ctb:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 9, 11]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51, geo_ctb:inside+position_geometry:+0.65
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03, geo_ctb:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_ctb:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 3, 11, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53, geo_ctb:low_draw+position_geometry:+0.40
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05, geo_ctb:inside+position_geometry:+0.65
  - #6 Laurel Hill P6: geo_ctb:inside+position_geometry:+0.65
- 2025-09-13 Flemington Race 1-10 R4: `[4, 9, 10, 3]` -> `[10, 4, 9, 3]`
  - #10 Castlejohn P-1: trial:trial_extreme_l600_33.43:+3.32
- 2026-04-18 Randwick R1: `[13, 14, 10, 9]` -> `[10, 13, 14, 9]`
  - #10 Danish Prince P6: trial:trial_excellent_l600_33.65:+0.51
  - #9 Cosmeena P8: trial:trial_excellent_l600_33.84:+0.51
  - #4 Audrey's Lane P3: trial:trial_excellent_l600_33.90:+0.51

### Example Reranks: all / geometry_tight

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_tight:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_tight:wide:-0.40
  - #5 Tenderize P3: geo_tight:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 11, 12]`
  - #2 Celui P7: geo_tight:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_tight:low_draw+position_geometry:+0.40
  - #9 Dollar Magic P4: geo_tight:inside+position_geometry:+0.65
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[11, 3, 8, 6]`
  - #3 Love Shuck P4: geo_tight:low_draw+position_geometry:+0.40
  - #6 Laurel Hill P6: geo_tight:inside+position_geometry:+0.65
  - #1 Mafia P2: geo_tight:inside+position_geometry:+0.65
- 2026-04-17 Cranbourne Race 1-8 R1: `[6, 5, 4, 2]` -> `[5, 6, 4, 2]`
  - #5 Price Tag P1: geo_tight:inside+position_geometry:+0.65
  - #4 Posh Diamante P3: geo_tight:low_draw+position_geometry:+0.40
  - #2 French Intrigue P-1: geo_tight:low_draw+position_geometry:+0.40
  - #8 Terracotta Rose P-1: geo_tight:inside+position_geometry:+0.65
- 2026-04-17 Cranbourne Race 1-8 R2: `[8, 3, 9, 10]` -> `[8, 3, 10, 9]`
  - #8 Boa Vista P-1: geo_tight:wide:-0.40
  - #3 Logam P1: geo_tight:inside+position_geometry:+0.65
  - #10 Theatrical Queen P2: geo_tight:low_draw+position_geometry:+0.40
  - #2 Jack The Judge P4: geo_tight:inside+position_geometry:+0.65

### Example Reranks: all / immediate_tight

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_tight:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_tight:wide:-0.40
  - #5 Tenderize P3: geo_tight:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 9, 11]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51, geo_tight:inside+position_geometry:+0.65
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03, geo_tight:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_tight:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 3, 11, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53, geo_tight:low_draw+position_geometry:+0.40
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05, geo_tight:inside+position_geometry:+0.65
  - #6 Laurel Hill P6: geo_tight:inside+position_geometry:+0.65
- 2025-09-13 Flemington Race 1-10 R4: `[4, 9, 10, 3]` -> `[10, 4, 9, 3]`
  - #10 Castlejohn P-1: trial:trial_extreme_l600_33.43:+3.32
- 2026-04-17 Cranbourne Race 1-8 R1: `[6, 5, 4, 2]` -> `[5, 6, 4, 2]`
  - #5 Price Tag P1: geo_tight:inside+position_geometry:+0.65
  - #4 Posh Diamante P3: geo_tight:low_draw+position_geometry:+0.40
  - #2 French Intrigue P-1: geo_tight:low_draw+position_geometry:+0.40
  - #8 Terracotta Rose P-1: geo_tight:inside+position_geometry:+0.65

### Example Reranks: all / comments

- 2026-06-08 Canterbury Race 1-8 R1: `[3, 4, 6, 8]` -> `[3, 4, 8, 6]`
  - #8 Satin Serenade P2: comment:pick_of_the_first_starters+trialing_well:+1.25
- 2026-06-08 Canterbury Race 1-8 R3: `[7, 1, 8, 3]` -> `[7, 8, 1, 3]`
  - #8 Wootton Way P8: comment:can't_be_ruled_out:+0.35
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[11, 8, 3, 1]`
  - #1 Mafia P2: comment:drawn_ideally+will_be_in_it:+0.90
- 2026-04-18 Randwick R6: `[15, 17, 5, 10]` -> `[15, 5, 17, 10]`
  - #5 Travolta P3: comment:looks_suited:+0.45
- 2026-05-27 Doomben Race 1-8 R6: `[2, 9, 3, 6]` -> `[2, 9, 6, 3]`
  - #6 Shot Of Whiskey P1: comment:ready_to_fire+rock_hard_fit:+1.20

### Example Reranks: all / all

- 2026-06-08 Canterbury Race 1-8 R1: `[3, 4, 6, 8]` -> `[3, 4, 8, 6]`
  - #3 Excelluna P3: geo_tight:inside+position_geometry:+0.65
  - #8 Satin Serenade P2: geo_tight:inside+position_geometry:+0.65, comment:pick_of_the_first_starters+trialing_well:+1.25
  - #6 Miss Scandal P1: geo_tight:inside+position_geometry:+0.65
  - #5 Idmiston P7: geo_tight:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_tight:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_tight:wide:-0.40
  - #5 Tenderize P3: geo_tight:wide:-0.40
  - #1 The Creator P1: geo_tight:wide:-0.40, comment:races_extremely_well:+0.55
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 9, 11]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51, geo_tight:inside+position_geometry:+0.65
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03, geo_tight:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_tight:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 3, 11, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53, geo_tight:low_draw+position_geometry:+0.40
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05, geo_tight:inside+position_geometry:+0.65, comment:drawn_ideally+will_be_in_it:+0.90
  - #6 Laurel Hill P6: geo_tight:inside+position_geometry:+0.65
- 2025-09-06 Randwick Race 1-10 R2: `[5, 14, 19, 15]` -> `[5, 2, 10, 19]`
  - #5 So Magnificent P1: existing_barrier:randwick_b1:+1.50
  - #2 Nimble Star P3: comment:main_danger:+0.55
  - #10 Calido Magic P5: existing_barrier:randwick_b2:+1.50
  - #19 Graceful Ellen P13: existing_barrier:randwick_b12:-3.00

## Canterbury
- Races: **22**
- Baseline: Gold `1`, Good `10`, Pass `18`, Top3 win `10`, Top3 place `29/66`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 1 | 10 | 18 | 10 | 29 | 4 | 0.39 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| existing_barrier_table | 1 | 10 | 18 | 10 | 29 | 4 | 0.39 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| trial | 0 | 10 | 18 | 9 | 28 | 4 | 0.3816 | 8 | G -1, Good +0, Pass +0, Win -1, Place -1 (-1.52pp), 0H +0, MRR -0.0084 |
| geometry_canterbury | 0 | 10 | 17 | 10 | 27 | 5 | 0.3877 | 9 | G -1, Good +0, Pass -1, Win +0, Place -2 (-3.03pp), 0H +1, MRR -0.0023 |
| immediate_canterbury | 0 | 10 | 17 | 10 | 27 | 5 | 0.3854 | 12 | G -1, Good +0, Pass -1, Win +0, Place -2 (-3.03pp), 0H +1, MRR -0.0046 |
| geometry_tight | 0 | 10 | 17 | 10 | 27 | 5 | 0.3877 | 9 | G -1, Good +0, Pass -1, Win +0, Place -2 (-3.03pp), 0H +1, MRR -0.0023 |
| immediate_tight | 0 | 10 | 17 | 10 | 27 | 5 | 0.3854 | 12 | G -1, Good +0, Pass -1, Win +0, Place -2 (-3.03pp), 0H +1, MRR -0.0046 |
| comments | 1 | 10 | 18 | 9 | 29 | 4 | 0.381 | 3 | G +0, Good +0, Pass +0, Win -1, Place +0 (+0.00pp), 0H +0, MRR -0.0090 |
| all | 0 | 10 | 17 | 9 | 27 | 5 | 0.385 | 13 | G -1, Good +0, Pass -1, Win -1, Place -2 (-3.03pp), 0H +1, MRR -0.0050 |

### Example Reranks: canterbury / trial

- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 7, 9]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 11, 3, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05
- 2026-04-22 Canterbury Race 1-8 R2: `[3, 1, 4, 9]` -> `[1, 3, 4, 9]`
  - #1 Cheeky Sort P5: trial:trial_excellent_l600_33.86:+0.61
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 7, 3, 10]`
  - #3 Graffiti Tycoon P2: trial:trial_excellent_l600_33.56:+0.61
  - #10 In A Tizzy P4: trial:trial_excellent_l600_33.90:+0.61
- 2026-04-22 Canterbury Race 1-8 R5: `[1, 2, 9, 7]` -> `[2, 9, 1, 8]`
  - #2 Shotgun Bella P3: trial:trial_excellent_l600_33.65:+0.52
  - #9 Nymphadora P8: trial:trial_excellent_l600_33.56:+0.52
  - #8 Angel City P9: trial:trial_excellent_l600_33.78:+0.52

### Example Reranks: canterbury / geometry_canterbury

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_ctb:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_ctb:wide:-0.40
  - #5 Tenderize P3: geo_ctb:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 11, 12]`
  - #2 Celui P7: geo_ctb:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_ctb:low_draw+position_geometry:+0.40
  - #9 Dollar Magic P4: geo_ctb:inside+position_geometry:+0.65
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[11, 3, 8, 6]`
  - #3 Love Shuck P4: geo_ctb:low_draw+position_geometry:+0.40
  - #6 Laurel Hill P6: geo_ctb:inside+position_geometry:+0.65
  - #1 Mafia P2: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 3, 7, 1]`
  - #13 Pink Persuasion P3: geo_ctb:low_draw+position_geometry:+0.40
  - #3 Graffiti Tycoon P2: geo_ctb:inside+position_geometry:+0.65
  - #7 Salt Spray P6: geo_ctb:wide:-0.40
  - #1 Adenauer P5: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R5: `[1, 2, 9, 7]` -> `[1, 9, 2, 5]`
  - #1 Erin Jo P5: geo_ctb:low_draw+position_geometry:+0.40
  - #9 Nymphadora P8: geo_ctb:inside+position_geometry:+0.65
  - #5 Superfabulistic P2: geo_ctb:inside+position_geometry:+0.65

### Example Reranks: canterbury / immediate_canterbury

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_ctb:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_ctb:wide:-0.40
  - #5 Tenderize P3: geo_ctb:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 9, 11]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51, geo_ctb:inside+position_geometry:+0.65
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03, geo_ctb:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_ctb:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 3, 11, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53, geo_ctb:low_draw+position_geometry:+0.40
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05, geo_ctb:inside+position_geometry:+0.65
  - #6 Laurel Hill P6: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R2: `[3, 1, 4, 9]` -> `[1, 3, 4, 9]`
  - #1 Cheeky Sort P5: trial:trial_excellent_l600_33.86:+0.61, geo_ctb:low_draw+position_geometry:+0.40
  - #3 Cold Gin P3: geo_ctb:inside+position_geometry:+0.65
  - #4 Events P1: geo_ctb:inside+position_geometry:+0.65
  - #5 Mariemac P6: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 3, 10, 7]`
  - #13 Pink Persuasion P3: geo_ctb:low_draw+position_geometry:+0.40
  - #3 Graffiti Tycoon P2: trial:trial_excellent_l600_33.56:+0.61, geo_ctb:inside+position_geometry:+0.65
  - #10 In A Tizzy P4: trial:trial_excellent_l600_33.90:+0.61, geo_ctb:low_draw+position_geometry:+0.40
  - #7 Salt Spray P6: geo_ctb:wide:-0.40

### Example Reranks: canterbury / geometry_tight

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_tight:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_tight:wide:-0.40
  - #5 Tenderize P3: geo_tight:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 11, 12]`
  - #2 Celui P7: geo_tight:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_tight:low_draw+position_geometry:+0.40
  - #9 Dollar Magic P4: geo_tight:inside+position_geometry:+0.65
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[11, 3, 8, 6]`
  - #3 Love Shuck P4: geo_tight:low_draw+position_geometry:+0.40
  - #6 Laurel Hill P6: geo_tight:inside+position_geometry:+0.65
  - #1 Mafia P2: geo_tight:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 3, 7, 1]`
  - #13 Pink Persuasion P3: geo_tight:low_draw+position_geometry:+0.40
  - #3 Graffiti Tycoon P2: geo_tight:inside+position_geometry:+0.65
  - #7 Salt Spray P6: geo_tight:wide:-0.40
  - #1 Adenauer P5: geo_tight:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R5: `[1, 2, 9, 7]` -> `[1, 9, 2, 5]`
  - #1 Erin Jo P5: geo_tight:low_draw+position_geometry:+0.40
  - #9 Nymphadora P8: geo_tight:inside+position_geometry:+0.65
  - #5 Superfabulistic P2: geo_tight:inside+position_geometry:+0.65

### Example Reranks: canterbury / immediate_tight

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_tight:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_tight:wide:-0.40
  - #5 Tenderize P3: geo_tight:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 9, 11]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51, geo_tight:inside+position_geometry:+0.65
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03, geo_tight:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_tight:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 3, 11, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53, geo_tight:low_draw+position_geometry:+0.40
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05, geo_tight:inside+position_geometry:+0.65
  - #6 Laurel Hill P6: geo_tight:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R2: `[3, 1, 4, 9]` -> `[1, 3, 4, 9]`
  - #1 Cheeky Sort P5: trial:trial_excellent_l600_33.86:+0.61, geo_tight:low_draw+position_geometry:+0.40
  - #3 Cold Gin P3: geo_tight:inside+position_geometry:+0.65
  - #4 Events P1: geo_tight:inside+position_geometry:+0.65
  - #5 Mariemac P6: geo_tight:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 3, 10, 7]`
  - #13 Pink Persuasion P3: geo_tight:low_draw+position_geometry:+0.40
  - #3 Graffiti Tycoon P2: trial:trial_excellent_l600_33.56:+0.61, geo_tight:inside+position_geometry:+0.65
  - #10 In A Tizzy P4: trial:trial_excellent_l600_33.90:+0.61, geo_tight:low_draw+position_geometry:+0.40
  - #7 Salt Spray P6: geo_tight:wide:-0.40

### Example Reranks: canterbury / comments

- 2026-06-08 Canterbury Race 1-8 R1: `[3, 4, 6, 8]` -> `[3, 4, 8, 6]`
  - #8 Satin Serenade P2: comment:pick_of_the_first_starters+trialing_well:+1.25
- 2026-06-08 Canterbury Race 1-8 R3: `[7, 1, 8, 3]` -> `[7, 8, 1, 3]`
  - #8 Wootton Way P8: comment:can't_be_ruled_out:+0.35
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[11, 8, 3, 1]`
  - #1 Mafia P2: comment:drawn_ideally+will_be_in_it:+0.90

### Example Reranks: canterbury / all

- 2026-06-08 Canterbury Race 1-8 R1: `[3, 4, 6, 8]` -> `[3, 4, 8, 6]`
  - #3 Excelluna P3: geo_tight:inside+position_geometry:+0.65
  - #8 Satin Serenade P2: geo_tight:inside+position_geometry:+0.65, comment:pick_of_the_first_starters+trialing_well:+1.25
  - #6 Miss Scandal P1: geo_tight:inside+position_geometry:+0.65
  - #5 Idmiston P7: geo_tight:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_tight:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_tight:wide:-0.40
  - #5 Tenderize P3: geo_tight:wide:-0.40
  - #1 The Creator P1: geo_tight:wide:-0.40, comment:races_extremely_well:+0.55
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 9, 11]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51, geo_tight:inside+position_geometry:+0.65
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03, geo_tight:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_tight:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 3, 11, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53, geo_tight:low_draw+position_geometry:+0.40
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05, geo_tight:inside+position_geometry:+0.65, comment:drawn_ideally+will_be_in_it:+0.90
  - #6 Laurel Hill P6: geo_tight:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R2: `[3, 1, 4, 9]` -> `[1, 3, 4, 9]`
  - #1 Cheeky Sort P5: trial:trial_excellent_l600_33.86:+0.61, geo_tight:low_draw+position_geometry:+0.40
  - #3 Cold Gin P3: geo_tight:inside+position_geometry:+0.65
  - #4 Events P1: geo_tight:inside+position_geometry:+0.65
  - #5 Mariemac P6: geo_tight:inside+position_geometry:+0.65

## Tight Turn
- Races: **47**
- Baseline: Gold `6`, Good `18`, Pass `42`, Top3 win `23`, Top3 place `66/141`

| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 6 | 18 | 42 | 23 | 66 | 5 | 0.4055 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| existing_barrier_table | 6 | 18 | 42 | 23 | 66 | 5 | 0.4055 | 0 | G +0, Good +0, Pass +0, Win +0, Place +0 (+0.00pp), 0H +0, MRR +0.0000 |
| trial | 5 | 18 | 42 | 22 | 65 | 5 | 0.398 | 9 | G -1, Good +0, Pass +0, Win -1, Place -1 (-0.71pp), 0H +0, MRR -0.0075 |
| geometry_canterbury | 5 | 18 | 41 | 23 | 64 | 6 | 0.4044 | 9 | G -1, Good +0, Pass -1, Win +0, Place -2 (-1.42pp), 0H +1, MRR -0.0011 |
| immediate_canterbury | 5 | 18 | 41 | 23 | 64 | 6 | 0.3998 | 13 | G -1, Good +0, Pass -1, Win +0, Place -2 (-1.42pp), 0H +1, MRR -0.0057 |
| geometry_tight | 4 | 20 | 41 | 24 | 65 | 6 | 0.4069 | 22 | G -2, Good +2, Pass -1, Win +1, Place -1 (-0.71pp), 0H +1, MRR +0.0014 |
| immediate_tight | 4 | 20 | 41 | 24 | 65 | 6 | 0.4023 | 25 | G -2, Good +2, Pass -1, Win +1, Place -1 (-0.71pp), 0H +1, MRR -0.0032 |
| comments | 6 | 18 | 42 | 22 | 66 | 5 | 0.4013 | 3 | G +0, Good +0, Pass +0, Win -1, Place +0 (+0.00pp), 0H +0, MRR -0.0042 |
| all | 4 | 20 | 41 | 23 | 65 | 6 | 0.4021 | 26 | G -2, Good +2, Pass -1, Win +0, Place -1 (-0.71pp), 0H +1, MRR -0.0034 |

### Example Reranks: tight_turn / trial

- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 7, 9]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 11, 3, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05
- 2026-04-22 Canterbury Race 1-8 R2: `[3, 1, 4, 9]` -> `[1, 3, 4, 9]`
  - #1 Cheeky Sort P5: trial:trial_excellent_l600_33.86:+0.61
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 7, 3, 10]`
  - #3 Graffiti Tycoon P2: trial:trial_excellent_l600_33.56:+0.61
  - #10 In A Tizzy P4: trial:trial_excellent_l600_33.90:+0.61
- 2026-04-22 Canterbury Race 1-8 R5: `[1, 2, 9, 7]` -> `[2, 9, 1, 8]`
  - #2 Shotgun Bella P3: trial:trial_excellent_l600_33.65:+0.52
  - #9 Nymphadora P8: trial:trial_excellent_l600_33.56:+0.52
  - #8 Angel City P9: trial:trial_excellent_l600_33.78:+0.52

### Example Reranks: tight_turn / geometry_canterbury

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_ctb:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_ctb:wide:-0.40
  - #5 Tenderize P3: geo_ctb:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 11, 12]`
  - #2 Celui P7: geo_ctb:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_ctb:low_draw+position_geometry:+0.40
  - #9 Dollar Magic P4: geo_ctb:inside+position_geometry:+0.65
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[11, 3, 8, 6]`
  - #3 Love Shuck P4: geo_ctb:low_draw+position_geometry:+0.40
  - #6 Laurel Hill P6: geo_ctb:inside+position_geometry:+0.65
  - #1 Mafia P2: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 3, 7, 1]`
  - #13 Pink Persuasion P3: geo_ctb:low_draw+position_geometry:+0.40
  - #3 Graffiti Tycoon P2: geo_ctb:inside+position_geometry:+0.65
  - #7 Salt Spray P6: geo_ctb:wide:-0.40
  - #1 Adenauer P5: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R5: `[1, 2, 9, 7]` -> `[1, 9, 2, 5]`
  - #1 Erin Jo P5: geo_ctb:low_draw+position_geometry:+0.40
  - #9 Nymphadora P8: geo_ctb:inside+position_geometry:+0.65
  - #5 Superfabulistic P2: geo_ctb:inside+position_geometry:+0.65

### Example Reranks: tight_turn / immediate_canterbury

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_ctb:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_ctb:wide:-0.40
  - #5 Tenderize P3: geo_ctb:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 9, 11]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51, geo_ctb:inside+position_geometry:+0.65
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03, geo_ctb:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_ctb:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 3, 11, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53, geo_ctb:low_draw+position_geometry:+0.40
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05, geo_ctb:inside+position_geometry:+0.65
  - #6 Laurel Hill P6: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R2: `[3, 1, 4, 9]` -> `[1, 3, 4, 9]`
  - #1 Cheeky Sort P5: trial:trial_excellent_l600_33.86:+0.61, geo_ctb:low_draw+position_geometry:+0.40
  - #3 Cold Gin P3: geo_ctb:inside+position_geometry:+0.65
  - #4 Events P1: geo_ctb:inside+position_geometry:+0.65
  - #5 Mariemac P6: geo_ctb:inside+position_geometry:+0.65
- 2026-04-22 Canterbury Race 1-8 R3: `[13, 7, 11, 3]` -> `[13, 3, 10, 7]`
  - #13 Pink Persuasion P3: geo_ctb:low_draw+position_geometry:+0.40
  - #3 Graffiti Tycoon P2: trial:trial_excellent_l600_33.56:+0.61, geo_ctb:inside+position_geometry:+0.65
  - #10 In A Tizzy P4: trial:trial_excellent_l600_33.90:+0.61, geo_ctb:low_draw+position_geometry:+0.40
  - #7 Salt Spray P6: geo_ctb:wide:-0.40

### Example Reranks: tight_turn / geometry_tight

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_tight:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_tight:wide:-0.40
  - #5 Tenderize P3: geo_tight:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 11, 12]`
  - #2 Celui P7: geo_tight:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_tight:low_draw+position_geometry:+0.40
  - #9 Dollar Magic P4: geo_tight:inside+position_geometry:+0.65
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[11, 3, 8, 6]`
  - #3 Love Shuck P4: geo_tight:low_draw+position_geometry:+0.40
  - #6 Laurel Hill P6: geo_tight:inside+position_geometry:+0.65
  - #1 Mafia P2: geo_tight:inside+position_geometry:+0.65
- 2026-04-17 Cranbourne Race 1-8 R1: `[6, 5, 4, 2]` -> `[5, 6, 4, 2]`
  - #5 Price Tag P1: geo_tight:inside+position_geometry:+0.65
  - #4 Posh Diamante P3: geo_tight:low_draw+position_geometry:+0.40
  - #2 French Intrigue P-1: geo_tight:low_draw+position_geometry:+0.40
  - #8 Terracotta Rose P-1: geo_tight:inside+position_geometry:+0.65
- 2026-04-17 Cranbourne Race 1-8 R2: `[8, 3, 9, 10]` -> `[8, 3, 10, 9]`
  - #8 Boa Vista P-1: geo_tight:wide:-0.40
  - #3 Logam P1: geo_tight:inside+position_geometry:+0.65
  - #10 Theatrical Queen P2: geo_tight:low_draw+position_geometry:+0.40
  - #2 Jack The Judge P4: geo_tight:inside+position_geometry:+0.65

### Example Reranks: tight_turn / immediate_tight

- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_tight:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_tight:wide:-0.40
  - #5 Tenderize P3: geo_tight:wide:-0.40
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 9, 11]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51, geo_tight:inside+position_geometry:+0.65
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03, geo_tight:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_tight:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 3, 11, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53, geo_tight:low_draw+position_geometry:+0.40
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05, geo_tight:inside+position_geometry:+0.65
  - #6 Laurel Hill P6: geo_tight:inside+position_geometry:+0.65
- 2026-04-17 Cranbourne Race 1-8 R1: `[6, 5, 4, 2]` -> `[5, 6, 4, 2]`
  - #5 Price Tag P1: geo_tight:inside+position_geometry:+0.65
  - #4 Posh Diamante P3: geo_tight:low_draw+position_geometry:+0.40
  - #2 French Intrigue P-1: geo_tight:low_draw+position_geometry:+0.40
  - #8 Terracotta Rose P-1: geo_tight:inside+position_geometry:+0.65
- 2026-04-17 Cranbourne Race 1-8 R2: `[8, 3, 9, 10]` -> `[8, 3, 10, 9]`
  - #8 Boa Vista P-1: geo_tight:wide:-0.40
  - #3 Logam P1: geo_tight:inside+position_geometry:+0.65
  - #10 Theatrical Queen P2: geo_tight:low_draw+position_geometry:+0.40
  - #2 Jack The Judge P4: geo_tight:inside+position_geometry:+0.65

### Example Reranks: tight_turn / comments

- 2026-06-08 Canterbury Race 1-8 R1: `[3, 4, 6, 8]` -> `[3, 4, 8, 6]`
  - #8 Satin Serenade P2: comment:pick_of_the_first_starters+trialing_well:+1.25
- 2026-06-08 Canterbury Race 1-8 R3: `[7, 1, 8, 3]` -> `[7, 8, 1, 3]`
  - #8 Wootton Way P8: comment:can't_be_ruled_out:+0.35
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[11, 8, 3, 1]`
  - #1 Mafia P2: comment:drawn_ideally+will_be_in_it:+0.90

### Example Reranks: tight_turn / all

- 2026-06-08 Canterbury Race 1-8 R1: `[3, 4, 6, 8]` -> `[3, 4, 8, 6]`
  - #3 Excelluna P3: geo_tight:inside+position_geometry:+0.65
  - #8 Satin Serenade P2: geo_tight:inside+position_geometry:+0.65, comment:pick_of_the_first_starters+trialing_well:+1.25
  - #6 Miss Scandal P1: geo_tight:inside+position_geometry:+0.65
  - #5 Idmiston P7: geo_tight:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R6: `[10, 8, 2, 5]` -> `[8, 10, 2, 5]`
  - #8 Louie's Legacy P5: geo_tight:inside+position_geometry:+0.65
  - #2 Forbidden Riff P4: geo_tight:wide:-0.40
  - #5 Tenderize P3: geo_tight:wide:-0.40
  - #1 The Creator P1: geo_tight:wide:-0.40, comment:races_extremely_well:+0.55
- 2026-06-08 Canterbury Race 1-8 R7: `[18, 7, 19, 2]` -> `[18, 2, 9, 11]`
  - #2 Celui P7: trial:trial_excellent_l600_33.94:+0.51, geo_tight:inside+position_geometry:+0.65
  - #9 Dollar Magic P4: trial:trial_extreme_l600_32.66:+1.03, geo_tight:inside+position_geometry:+0.65
  - #11 Memoria P5: geo_tight:low_draw+position_geometry:+0.40
- 2026-06-08 Canterbury Race 1-8 R8: `[11, 8, 3, 6]` -> `[8, 3, 11, 1]`
  - #8 Tuscany P5: trial:trial_extreme_l600_32.80:+1.05
  - #3 Love Shuck P4: trial:trial_excellent_l600_33.98:+0.53, geo_tight:low_draw+position_geometry:+0.40
  - #1 Mafia P2: trial:trial_extreme_l600_33.28:+1.05, geo_tight:inside+position_geometry:+0.65, comment:drawn_ideally+will_be_in_it:+0.90
  - #6 Laurel Hill P6: geo_tight:inside+position_geometry:+0.65
- 2026-04-17 Cranbourne Race 1-8 R1: `[6, 5, 4, 2]` -> `[5, 6, 4, 2]`
  - #5 Price Tag P1: geo_tight:inside+position_geometry:+0.65
  - #4 Posh Diamante P3: geo_tight:low_draw+position_geometry:+0.40
  - #2 French Intrigue P-1: geo_tight:low_draw+position_geometry:+0.40
  - #8 Terracotta Rose P-1: geo_tight:inside+position_geometry:+0.65
