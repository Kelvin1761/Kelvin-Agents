# HKJC Wong Choi Step 1 — 0／1 Hit Baseline Manifest

## Definition Lock

- Primary: original model Top 2 finishing in official Top 3: 0／1／2 hit.
- Comparison: canonical Reflector exclusive label.
- Dead heats are position-safe (`finish <= 3`); original rank gaps are never compressed.
- No scoring, re-ranking, odds, going, draw, or rank-4-to-rank-7 tie-break is used.

## Coverage

- Meetings: 25
- Races seen: 252
- Valid races: 245
- Invalid races: 7
- Source gaps: 2

## Top 2 Baseline

- 0 hit: 75 (30.6%)
- 1 hit: 117 (47.8%)
- 2 hit: 53 (21.6%)
- Third pick finished Top 3: 89
- Third pick was the only model Top-3 hit while Top 2 had 0: 29
- Winner contained in model Top 2: 92/245

## Top 2 / Third-Pick Bridge

- Top 2 = 0 hit, third pick hit: 29
- Top 2 = 0 hit, no model Top-3 hit: 46
- Top 2 = 1 hit, third pick also hit: 52
- Top 2 = 1 hit, third pick missed: 65
- Top 2 = 2 hit, third pick also hit (Gold): 8
- Top 2 = 2 hit, third pick missed: 45

## One-Hit Position Split

- Rank 1 hit; rank 2 and rank 3 missed: 43
- Rank 1 and rank 3 hit; rank 2 missed (direct rank-3 promotion opportunity): 29
- Rank 1 missed; rank 2 and rank 3 hit (rank-2-to-rank-3 swap cannot improve hit count): 23
- Rank 1 and rank 3 missed; rank 2 hit: 22

## Dataset Split

- `archive`: 13 meetings / 127 valid races; Top2 hits {'0': 33, '1': 60, '2': 34}
- `external_2026_07_15`: 1 meetings / 9 valid races; Top2 hits {'0': 5, '1': 1, '2': 3}
- `independent_recent`: 11 meetings / 109 valid races; Top2 hits {'0': 37, '1': 56, '2': 16}

## Data Gaps

- 2026-05-31_ShaTin R-: missing_logic_or_local_results
- 2026-06-24_HappyValley R-: missing_logic_or_local_results
- 2026-04-12_ShaTin R10: rank_3_count=0
- 2026-04-19_ShaTin R8: rank_1_count=0
- 2026-04-22_HappyValley R2: rank_2_count=0
- 2026-05-27_HappyValley R6: rank_2_missing_numeric_finish=#6
- 2026-06-03_HappyValley R9: rank_3_missing_numeric_finish=#2
- 2026-06-07_ShaTin R1: rank_2_missing_numeric_finish=#3, actual_top3_count=1
- 2026-06-07_ShaTin R8: rank_1_missing_numeric_finish=#5

## Step 1 Status

Baseline only. No causal conclusion or production model change is authorised at this step.
