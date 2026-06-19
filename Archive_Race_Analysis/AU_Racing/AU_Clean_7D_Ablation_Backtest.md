# AU Clean 7D Ablation Backtest

Shadow test only. This report does not change the live AU ranking engine.

## Recommendation

- Pure Static 7D passes the directional clean gate: accept small Gold sacrifice for lower 0-hit, better Good/Pass, better Winner Top5, and cleaner future upgrade path.
- Kensington gate: PASS - #4 Existential Bob watchlist level High; reasons=near_top3_score,stable_enough,class_weight_ok,jt_or_trial_support,market_context_live,excuse_shape_context.
- HKJC lesson applied: keep final ranking as one official matrix score; use rich data as sourced feature evidence or report-only watchlist, not post-score rerank noise.

## Overall Metrics

| Variant | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Current Live | 336 | 22.3% | 4.2% | 17.6% | 38.1% | 51.8% | 69.3% | 42.9% | 46 | 162 | 114 | 14 |
| Pure Static 7D | 336 | 22.0% | 3.3% | 18.2% | 38.7% | 51.8% | 70.5% | 43.1% | 43 | 163 | 119 | 11 |
| Dynamic 7D Only | 336 | 20.5% | 3.3% | 17.9% | 38.1% | 51.2% | 70.5% | 42.9% | 43 | 165 | 117 | 11 |
| Dynamic 7D + Safety Caps | 336 | 19.9% | 3.6% | 17.9% | 38.1% | 52.1% | 70.2% | 43.2% | 41 | 167 | 116 | 12 |
| Current Minus Noisy Modifiers | 336 | 17.0% | 2.1% | 11.6% | 25.0% | 40.2% | 63.4% | 36.1% | 63 | 189 | 77 | 7 |

## Delta vs Current Live

| Variant | Gold Δ | Good Δ | Pass Δ | 0-hit Δ | 1-hit Δ | Top3 places Δ | Winner Top5 Δ | Strict | Directional Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Pure Static 7D | -3 | +2 | +2 | -3 | +1 | +2 | +4 | FAIL | PASS |
| Dynamic 7D Only | -3 | +1 | +0 | -3 | +3 | +0 | +4 | FAIL | PASS |
| Dynamic 7D + Safety Caps | -2 | +1 | +0 | -5 | +5 | +3 | +3 | FAIL | PASS |
| Current Minus Noisy Modifiers | -7 | -20 | -44 | +17 | +27 | -68 | -20 | FAIL | FAIL |

## Broad Rank 4-6 Watchlist Quality

- Flagged rank 4-6 horses: **1003**
- Actual Top3 among flagged: **287** (28.6%)
- Levels: High **701**, Medium **276**, Low **26**

## Condition Breakdown

| Condition | Variant | Races | Gold | Good | Pass | Winner Top5 | Top3 Place | 0-hit | 1-hit |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Good/Firm | Current Live | 238 | 4.2% | 18.1% | 37.0% | 68.9% | 42.9% | 30 | 120 |
| Good/Firm | Pure Static 7D | 238 | 3.8% | 19.3% | 37.4% | 71.0% | 43.0% | 29 | 120 |
| Good/Firm | Dynamic 7D Only | 238 | 3.8% | 18.5% | 37.0% | 70.6% | 43.1% | 27 | 123 |
| Good/Firm | Dynamic 7D + Safety Caps | 238 | 3.8% | 18.5% | 37.0% | 70.6% | 43.1% | 27 | 123 |
| Good/Firm | Current Minus Noisy Modifiers | 238 | 2.1% | 11.3% | 23.5% | 64.7% | 35.6% | 45 | 137 |
| Soft | Current Live | 69 | 5.8% | 15.9% | 37.7% | 66.7% | 41.1% | 14 | 29 |
| Soft | Pure Static 7D | 69 | 2.9% | 14.5% | 39.1% | 66.7% | 41.1% | 13 | 29 |
| Soft | Dynamic 7D Only | 69 | 2.9% | 15.9% | 37.7% | 68.1% | 40.1% | 14 | 29 |
| Soft | Dynamic 7D + Safety Caps | 69 | 4.3% | 17.4% | 37.7% | 65.2% | 41.1% | 13 | 30 |
| Soft | Current Minus Noisy Modifiers | 69 | 2.9% | 11.6% | 24.6% | 58.0% | 35.3% | 15 | 37 |
| Heavy | Current Live | 29 | 0.0% | 17.2% | 48.3% | 79.3% | 47.1% | 2 | 13 |
| Heavy | Pure Static 7D | 29 | 0.0% | 17.2% | 48.3% | 75.9% | 48.3% | 1 | 14 |
| Heavy | Dynamic 7D Only | 29 | 0.0% | 17.2% | 48.3% | 75.9% | 47.1% | 2 | 13 |
| Heavy | Dynamic 7D + Safety Caps | 29 | 0.0% | 13.8% | 48.3% | 79.3% | 48.3% | 1 | 14 |
| Heavy | Current Minus Noisy Modifiers | 29 | 0.0% | 13.8% | 37.9% | 65.5% | 42.5% | 3 | 15 |

## Watchlist Examples

- 2025-08-02 Flemington Race 1-9 R1: High danger #3 Our Chief (60.17, pos 5); reasons=near_top3_score,stable_enough,jt_or_trial_support,distance_ok,market_context_live
- 2025-08-02 Flemington Race 1-9 R1: Low danger #7 Fenestella (57.58, pos 4); reasons=excuse_shape_context
- 2025-08-02 Flemington Race 1-9 R2: High danger #4 Wyclif (61.75, pos 5); reasons=near_top3_score,stable_enough,jt_or_trial_support,distance_ok,market_context_live,timing_context
- 2025-08-02 Flemington Race 1-9 R2: High danger #2 Changingoftheguard (61.64, pos 2); reasons=near_top3_score,stable_enough,jt_or_trial_support,distance_ok,market_context_live,timing_context
- 2025-08-02 Flemington Race 1-9 R2: High danger #1 Casino Seventeen (59.66, pos 6); reasons=near_top3_score,distance_ok,market_context_live,timing_context,excuse_shape_context
- 2025-08-02 Flemington Race 1-9 R3: Medium danger #15 She's Pretty Rich (64.16, pos 11); reasons=near_top3_score,stable_enough,distance_ok
- 2025-08-02 Flemington Race 1-9 R3: Medium danger #3 Epic Proportions (62.67, pos 7); reasons=near_top3_score,stable_enough,distance_ok,market_context_live
- 2025-08-02 Flemington Race 1-9 R3: Medium danger #11 Gronkowski (62.16, pos 10); reasons=near_top3_score,distance_ok,excuse_shape_context
- 2025-08-02 Flemington Race 1-9 R4: High danger #6 Call To Glory (61.40, pos 2); reasons=near_top3_score,stable_enough,class_weight_ok,jt_or_trial_support,distance_ok,market_context_live,timing_context
- 2025-08-02 Flemington Race 1-9 R4: Medium danger #4 Mr Exclusive (61.33, pos 10); reasons=near_top3_score,jt_or_trial_support,market_context_live,timing_context
- 2025-08-02 Flemington Race 1-9 R4: Medium danger #3 Eye Of The Fire (61.15, pos 4); reasons=near_top3_score,stable_enough,distance_ok,market_context_live
- 2025-08-02 Flemington Race 1-9 R5: Medium danger #12 Catani Gardens (62.19, pos 7); reasons=near_top3_score,stable_enough,distance_ok,market_context_live
- 2025-08-02 Flemington Race 1-9 R5: Medium danger #14 Federer (62.15, pos 2); reasons=near_top3_score,stable_enough,jt_or_trial_support,market_context_live
- 2025-08-02 Flemington Race 1-9 R5: Medium danger #5 Euphoric (61.85, pos 4); reasons=near_top3_score,stable_enough,market_context_live
- 2025-08-02 Flemington Race 1-9 R6: High danger #2 Munhamek (63.71, pos 8); reasons=near_top3_score,stable_enough,class_weight_ok,distance_ok,market_context_live,timing_context
- 2025-08-02 Flemington Race 1-9 R6: High danger #9 Green Fly (63.50, pos 4); reasons=near_top3_score,stable_enough,jt_or_trial_support,distance_ok,market_context_live
- 2025-08-02 Flemington Race 1-9 R6: High danger #5 Cafe Millenium (61.97, pos 5); reasons=near_top3_score,class_weight_ok,jt_or_trial_support,distance_ok,market_context_live,timing_context
- 2025-08-02 Flemington Race 1-9 R7: Medium danger #3 Lady In Pink (63.58, pos 9); reasons=near_top3_score,stable_enough,market_context_live

## Clean Variant Improved 0/1-Hit Examples

### Pure Static 7D - 2025-09-06 Randwick Race 1-10 R9
- Hits: 0 -> 1
- Current Top3: #6 Kovalica (70.98, pos 11) / #17 Depth Of Character (70.94, pos 12) / #15 Swiftfalcon (69.47, pos 6)
- Variant Top3: #17 Depth Of Character (69.16, pos 12) / #5 Private Eye (67.62, pos 2) / #15 Swiftfalcon (67.47, pos 6)

### Dynamic 7D Only - 2025-09-06 Randwick Race 1-10 R9
- Hits: 0 -> 1
- Current Top3: #6 Kovalica (70.98, pos 11) / #17 Depth Of Character (70.94, pos 12) / #15 Swiftfalcon (69.47, pos 6)
- Variant Top3: #17 Depth Of Character (69.61, pos 12) / #15 Swiftfalcon (67.92, pos 6) / #5 Private Eye (67.64, pos 2)

### Dynamic 7D + Safety Caps - 2025-09-06 Randwick Race 1-10 R9
- Hits: 0 -> 1
- Current Top3: #6 Kovalica (70.98, pos 11) / #17 Depth Of Character (70.94, pos 12) / #15 Swiftfalcon (69.47, pos 6)
- Variant Top3: #17 Depth Of Character (69.61, pos 12) / #15 Swiftfalcon (67.92, pos 6) / #5 Private Eye (67.64, pos 2)

### Pure Static 7D - 2025-09-13 Flemington Race 1-10 R1
- Hits: 1 -> 2
- Current Top3: #15 Persian Spirit (72.59, pos 1) / #10 She's An Artist (71.78, pos 4) / #2 De Bergerac (71.20, pos 5)
- Variant Top3: #10 She's An Artist (69.96, pos 4) / #8 Tonkin (69.41, pos 2) / #15 Persian Spirit (69.07, pos 1)

### Dynamic 7D Only - 2025-09-13 Flemington Race 1-10 R1
- Hits: 1 -> 2
- Current Top3: #15 Persian Spirit (72.59, pos 1) / #10 She's An Artist (71.78, pos 4) / #2 De Bergerac (71.20, pos 5)
- Variant Top3: #10 She's An Artist (70.38, pos 4) / #15 Persian Spirit (70.01, pos 1) / #8 Tonkin (69.75, pos 2)

### Dynamic 7D + Safety Caps - 2025-09-13 Flemington Race 1-10 R1
- Hits: 1 -> 2
- Current Top3: #15 Persian Spirit (72.59, pos 1) / #10 She's An Artist (71.78, pos 4) / #2 De Bergerac (71.20, pos 5)
- Variant Top3: #10 She's An Artist (70.38, pos 4) / #15 Persian Spirit (70.01, pos 1) / #8 Tonkin (69.75, pos 2)

### Pure Static 7D - 2025-09-13 Flemington Race 1-10 R3
- Hits: 0 -> 1
- Current Top3: #3 Crossbow (73.18, pos 9) / #12 Just Kick (70.35, pos 7) / #4 Prestige Ole (68.87, pos 5)
- Variant Top3: #3 Crossbow (69.53, pos 9) / #1 Vinrock (67.22, pos 1) / #5 Arcora (66.98, pos 10)

### Dynamic 7D Only - 2025-09-13 Flemington Race 1-10 R3
- Hits: 0 -> 1
- Current Top3: #3 Crossbow (73.18, pos 9) / #12 Just Kick (70.35, pos 7) / #4 Prestige Ole (68.87, pos 5)
- Variant Top3: #3 Crossbow (70.07, pos 9) / #1 Vinrock (67.21, pos 1) / #12 Just Kick (67.16, pos 7)

### Dynamic 7D + Safety Caps - 2025-09-13 Flemington Race 1-10 R3
- Hits: 0 -> 1
- Current Top3: #3 Crossbow (73.18, pos 9) / #12 Just Kick (70.35, pos 7) / #4 Prestige Ole (68.87, pos 5)
- Variant Top3: #3 Crossbow (70.07, pos 9) / #1 Vinrock (67.21, pos 1) / #12 Just Kick (67.16, pos 7)

### Pure Static 7D - 2025-09-13 Flemington Race 1-10 R9
- Hits: 0 -> 1
- Current Top3: #13 Bossy Benita (70.98, pos 11) / #7 On Display (70.13, pos 10) / #11 Splash Back (69.98, pos 5)
- Variant Top3: #7 On Display (68.53, pos 10) / #11 Splash Back (67.82, pos 5) / #3 Lazzura (67.53, pos 1)

### Dynamic 7D Only - 2025-09-13 Flemington Race 1-10 R9
- Hits: 0 -> 1
- Current Top3: #13 Bossy Benita (70.98, pos 11) / #7 On Display (70.13, pos 10) / #11 Splash Back (69.98, pos 5)
- Variant Top3: #7 On Display (69.19, pos 10) / #11 Splash Back (68.53, pos 5) / #3 Lazzura (68.19, pos 1)

### Dynamic 7D + Safety Caps - 2025-09-13 Flemington Race 1-10 R9
- Hits: 0 -> 1
- Current Top3: #13 Bossy Benita (70.98, pos 11) / #7 On Display (70.13, pos 10) / #11 Splash Back (69.98, pos 5)
- Variant Top3: #7 On Display (69.19, pos 10) / #11 Splash Back (68.53, pos 5) / #3 Lazzura (68.19, pos 1)

### Pure Static 7D - 2025-09-21 Flemington Race 1-8 R6
- Hits: 1 -> 2
- Current Top3: #9 Jennyanydots (65.20, pos 4) / #12 Sun Setting (64.46, pos 2) / #7 Prinzerro (64.24, pos 12)
- Variant Top3: #9 Jennyanydots (65.23, pos 4) / #12 Sun Setting (64.39, pos 2) / #15 Per Sempre (63.99, pos 1)

### Dynamic 7D Only - 2025-09-21 Flemington Race 1-8 R6
- Hits: 1 -> 2
- Current Top3: #9 Jennyanydots (65.20, pos 4) / #12 Sun Setting (64.46, pos 2) / #7 Prinzerro (64.24, pos 12)
- Variant Top3: #9 Jennyanydots (65.36, pos 4) / #12 Sun Setting (64.54, pos 2) / #15 Per Sempre (64.14, pos 1)

### Dynamic 7D + Safety Caps - 2025-09-21 Flemington Race 1-8 R6
- Hits: 1 -> 2
- Current Top3: #9 Jennyanydots (65.20, pos 4) / #12 Sun Setting (64.46, pos 2) / #7 Prinzerro (64.24, pos 12)
- Variant Top3: #9 Jennyanydots (65.36, pos 4) / #12 Sun Setting (64.54, pos 2) / #15 Per Sempre (64.14, pos 1)

### Dynamic 7D Only - 2025-10-04 Flemington Race 1-10 R8
- Hits: 1 -> 2
- Current Top3: #4 Via Sistina (66.74, pos 3) / #7 Aeliana (66.07, pos 5) / #10 Golden Path (65.42, pos 13)
- Variant Top3: #4 Via Sistina (66.52, pos 3) / #7 Aeliana (65.74, pos 5) / #3 Sir Delius (65.25, pos 1)

### Dynamic 7D + Safety Caps - 2025-10-04 Flemington Race 1-10 R8
- Hits: 1 -> 2
- Current Top3: #4 Via Sistina (66.74, pos 3) / #7 Aeliana (66.07, pos 5) / #10 Golden Path (65.42, pos 13)
- Variant Top3: #4 Via Sistina (66.52, pos 3) / #7 Aeliana (65.74, pos 5) / #3 Sir Delius (65.25, pos 1)

### Pure Static 7D - 2025-10-04 Randwick Race 1-10 R2
- Hits: 1 -> 2
- Current Top3: #6 Incognito (58.00, pos 1) / #1 Artaneous (57.94, pos 6) / #2 Eviction Notice (57.77, pos 7)
- Variant Top3: #6 Incognito (58.83, pos 1) / #4 I'm Ya Huckleberry (58.61, pos 2) / #2 Eviction Notice (58.44, pos 7)

### Dynamic 7D Only - 2025-10-04 Randwick Race 1-10 R2
- Hits: 1 -> 2
- Current Top3: #6 Incognito (58.00, pos 1) / #1 Artaneous (57.94, pos 6) / #2 Eviction Notice (57.77, pos 7)
- Variant Top3: #6 Incognito (57.54, pos 1) / #1 Artaneous (57.39, pos 6) / #4 I'm Ya Huckleberry (57.39, pos 2)

### Dynamic 7D + Safety Caps - 2025-10-04 Randwick Race 1-10 R2
- Hits: 1 -> 2
- Current Top3: #6 Incognito (58.00, pos 1) / #1 Artaneous (57.94, pos 6) / #2 Eviction Notice (57.77, pos 7)
- Variant Top3: #6 Incognito (57.54, pos 1) / #1 Artaneous (57.39, pos 6) / #4 I'm Ya Huckleberry (57.39, pos 2)

### Pure Static 7D - 2025-10-04 Randwick Race 1-10 R3
- Hits: 0 -> 1
- Current Top3: #11 The Wildling (58.61, pos 6) / #1 Better Off Alone (58.38, pos 7) / #2 Doubella (58.24, pos 10)
- Variant Top3: #11 The Wildling (58.57, pos 6) / #10 Shiki (58.42, pos 1) / #1 Better Off Alone (58.30, pos 7)

### Dynamic 7D Only - 2025-10-04 Randwick Race 1-10 R3
- Hits: 0 -> 1
- Current Top3: #11 The Wildling (58.61, pos 6) / #1 Better Off Alone (58.38, pos 7) / #2 Doubella (58.24, pos 10)
- Variant Top3: #11 The Wildling (57.92, pos 6) / #1 Better Off Alone (57.66, pos 7) / #10 Shiki (57.62, pos 1)

### Dynamic 7D + Safety Caps - 2025-10-04 Randwick Race 1-10 R3
- Hits: 0 -> 1
- Current Top3: #11 The Wildling (58.61, pos 6) / #1 Better Off Alone (58.38, pos 7) / #2 Doubella (58.24, pos 10)
- Variant Top3: #11 The Wildling (57.92, pos 6) / #1 Better Off Alone (57.66, pos 7) / #10 Shiki (57.62, pos 1)

### Pure Static 7D - 2025-10-04 Randwick Race 1-10 R10
- Hits: 0 -> 1
- Current Top3: #1 Les Vampires (66.01, pos 14) / #9 Getafix (65.54, pos 15) / #10 Kerguelen (65.17, pos 5)
- Variant Top3: #1 Les Vampires (66.12, pos 14) / #9 Getafix (65.71, pos 15) / #12 Boston Rocks (65.27, pos 3)

