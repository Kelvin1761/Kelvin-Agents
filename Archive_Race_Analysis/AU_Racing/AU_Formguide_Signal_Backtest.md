# AU Formguide Signal Backtest

Shadow test using pre-race Formguide/Facts data. No live ranking or 7D matrix weights are changed.

## Overall Metrics

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 336 | 22.3% | 4.2% | 17.6% | 38.1% | 51.8% | 69.3% | 42.9% | 46 | 162 | 114 | 14 |
| Market Flucs | 336 | 18.5% | 2.4% | 17.0% | 35.4% | 48.2% | 67.6% | 41.1% | 49 | 168 | 111 | 8 |
| Market Strict Rescue | 336 | 19.6% | 3.9% | 17.9% | 36.0% | 50.6% | 69.3% | 42.3% | 44 | 171 | 108 | 13 |
| Excuse/Run-Shape | 336 | 21.1% | 3.9% | 17.3% | 37.2% | 50.3% | 69.3% | 41.9% | 52 | 159 | 112 | 13 |
| Timing Consistency | 336 | 21.1% | 4.2% | 17.3% | 36.9% | 48.5% | 69.3% | 41.9% | 52 | 160 | 110 | 14 |
| Timing Rescue Only | 336 | 21.7% | 5.7% | 17.9% | 36.9% | 50.0% | 67.6% | 43.0% | 46 | 166 | 105 | 19 |
| Gear Change | 336 | 21.1% | 3.9% | 17.3% | 37.2% | 50.3% | 69.3% | 41.9% | 52 | 159 | 112 | 13 |
| Combined Formguide | 336 | 18.8% | 3.0% | 18.5% | 34.5% | 47.9% | 68.2% | 40.5% | 54 | 166 | 106 | 10 |
| Combined Strict | 336 | 18.5% | 3.3% | 16.7% | 36.3% | 46.1% | 68.8% | 41.2% | 54 | 160 | 111 | 11 |

## Delta vs Baseline

| Version | Gold Δ | Good Δ | Pass Δ | 0-hit Δ | 1-hit Δ | Top3 places Δ | Winner Top5 Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Market Flucs | -6 | -2 | -9 | +3 | +6 | -18 | -6 |
| Market Strict Rescue | -1 | +1 | -7 | -2 | +9 | -6 | +0 |
| Excuse/Run-Shape | -1 | -1 | -3 | +6 | -3 | -10 | +0 |
| Timing Consistency | +0 | -1 | -4 | +6 | -2 | -10 | +0 |
| Timing Rescue Only | +5 | +1 | -4 | +0 | +4 | +1 | -6 |
| Gear Change | -1 | -1 | -3 | +6 | -3 | -10 | +0 |
| Combined Formguide | -4 | +3 | -12 | +8 | +4 | -24 | -4 |
| Combined Strict | -3 | -3 | -6 | +8 | -2 | -17 | -2 |

## Signal Quality

| Version | Candidate Boosts | Candidate Actual Top3 | Risk Penalties | Risk Failed | Improved Races | Same | Worse |
|---|---:|---:|---:|---:|---:|---:|---:|
| Market Flucs | 713 | 229 (32.1%) | 69 | 39 (56.5%) | 73 | 174 | 89 |
| Market Strict Rescue | 348 | 124 (35.6%) | 0 | 0 (0.0%) | 61 | 208 | 67 |
| Excuse/Run-Shape | 0 | 0 (0.0%) | 143 | 81 (56.6%) | 8 | 310 | 18 |
| Timing Consistency | 35 | 16 (45.7%) | 143 | 81 (56.6%) | 13 | 300 | 23 |
| Timing Rescue Only | 132 | 47 (35.6%) | 0 | 0 (0.0%) | 20 | 297 | 19 |
| Gear Change | 0 | 0 (0.0%) | 143 | 81 (56.6%) | 8 | 310 | 18 |
| Combined Formguide | 613 | 202 (33.0%) | 69 | 39 (56.5%) | 66 | 181 | 89 |
| Combined Strict | 435 | 149 (34.3%) | 51 | 28 (54.9%) | 63 | 194 | 79 |

## Condition Breakdown

| Condition | Version | Races | Gold | Good | Pass | 0-hit | 1-hit | Top3 Place |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Good/Firm | Baseline | 238 | 4.2% | 18.1% | 37.0% | 30 | 120 | 42.9% |
| Good/Firm | Market Flucs | 238 | 2.9% | 16.4% | 37.0% | 34 | 116 | 41.9% |
| Good/Firm | Market Strict Rescue | 238 | 4.2% | 17.6% | 38.2% | 31 | 116 | 43.1% |
| Good/Firm | Excuse/Run-Shape | 238 | 3.8% | 17.6% | 35.3% | 35 | 119 | 41.5% |
| Good/Firm | Timing Consistency | 238 | 4.2% | 18.1% | 35.3% | 35 | 119 | 41.6% |
| Good/Firm | Timing Rescue Only | 238 | 5.5% | 18.5% | 35.7% | 30 | 123 | 42.9% |
| Good/Firm | Gear Change | 238 | 3.8% | 17.6% | 35.3% | 35 | 119 | 41.5% |
| Good/Firm | Combined Formguide | 238 | 3.8% | 17.6% | 37.4% | 38 | 111 | 41.7% |
| Good/Firm | Combined Strict | 238 | 4.2% | 16.8% | 39.1% | 38 | 107 | 42.4% |
| Soft | Baseline | 69 | 5.8% | 15.9% | 37.7% | 14 | 29 | 41.1% |
| Soft | Market Flucs | 69 | 1.4% | 15.9% | 30.4% | 14 | 34 | 37.2% |
| Soft | Market Strict Rescue | 69 | 2.9% | 15.9% | 26.1% | 12 | 39 | 37.2% |
| Soft | Excuse/Run-Shape | 69 | 5.8% | 17.4% | 36.2% | 16 | 28 | 39.6% |
| Soft | Timing Consistency | 69 | 5.8% | 15.9% | 34.8% | 16 | 29 | 39.1% |
| Soft | Timing Rescue Only | 69 | 7.2% | 15.9% | 37.7% | 14 | 29 | 41.5% |
| Soft | Gear Change | 69 | 5.8% | 17.4% | 36.2% | 16 | 28 | 39.6% |
| Soft | Combined Formguide | 69 | 1.4% | 15.9% | 26.1% | 13 | 38 | 36.2% |
| Soft | Combined Strict | 69 | 1.4% | 13.0% | 24.6% | 14 | 38 | 35.3% |
| Heavy | Baseline | 29 | 0.0% | 17.2% | 48.3% | 2 | 13 | 47.1% |
| Heavy | Market Flucs | 29 | 0.0% | 24.1% | 34.5% | 1 | 18 | 43.7% |
| Heavy | Market Strict Rescue | 29 | 3.4% | 24.1% | 41.4% | 1 | 16 | 47.1% |
| Heavy | Excuse/Run-Shape | 29 | 0.0% | 13.8% | 55.2% | 1 | 12 | 50.6% |
| Heavy | Timing Consistency | 29 | 0.0% | 13.8% | 55.2% | 1 | 12 | 50.6% |
| Heavy | Timing Rescue Only | 29 | 3.4% | 17.2% | 44.8% | 2 | 14 | 47.1% |
| Heavy | Gear Change | 29 | 0.0% | 13.8% | 55.2% | 1 | 12 | 50.6% |
| Heavy | Combined Formguide | 29 | 0.0% | 31.0% | 31.0% | 3 | 17 | 40.2% |
| Heavy | Combined Strict | 29 | 0.0% | 24.1% | 41.4% | 2 | 15 | 44.8% |

## Improved 0/1-Hit Examples

### Market Flucs - 2025-08-02 Flemington Race 1-9 R4
- Context: Good/Firm / BM72-84 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #2 Losesomewinmore (rank 1, pos 1, fluc 3.25)
  - #8 Smart Little Miss (rank 2, pos 9, fluc 26.0)
  - #10 Commands Success (rank 3, pos 5, fluc 41.0)
- Shadow Top3:
  - #2 Losesomewinmore (rank 1, pos 1, fluc 3.25)
  - #6 Call To Glory (rank 4, pos 2, fluc 4.6; market_live_le_15,market_live_le_8)
  - #4 Mr Exclusive (rank 5, pos 10, fluc 1.8; market_live_le_15,market_live_le_8)

### Market Strict Rescue - 2025-08-02 Flemington Race 1-9 R4
- Context: Good/Firm / BM72-84 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #2 Losesomewinmore (rank 1, pos 1, fluc 3.25)
  - #8 Smart Little Miss (rank 2, pos 9, fluc 26.0)
  - #10 Commands Success (rank 3, pos 5, fluc 41.0)
- Shadow Top3:
  - #2 Losesomewinmore (rank 1, pos 1, fluc 3.25)
  - #6 Call To Glory (rank 4, pos 2, fluc 4.6; market_live_le_15,market_live_le_8)
  - #4 Mr Exclusive (rank 5, pos 10, fluc 1.8; market_live_le_15,market_live_le_8)

### Combined Formguide - 2025-08-02 Flemington Race 1-9 R4
- Context: Good/Firm / BM72-84 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #2 Losesomewinmore (rank 1, pos 1, fluc 3.25)
  - #8 Smart Little Miss (rank 2, pos 9, fluc 26.0)
  - #10 Commands Success (rank 3, pos 5, fluc 41.0)
- Shadow Top3:
  - #2 Losesomewinmore (rank 1, pos 1, fluc 3.25)
  - #6 Call To Glory (rank 4, pos 2, fluc 4.6; market_live_le_15,market_live_le_8,shape_inconsistent,best_l600_top3_field,timing_improving)
  - #4 Mr Exclusive (rank 5, pos 10, fluc 1.8; market_live_le_15,market_live_le_8,shape_inconsistent,recent_l600_top3_field,timing_sharp_improving)

### Combined Strict - 2025-08-02 Flemington Race 1-9 R4
- Context: Good/Firm / BM72-84 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #2 Losesomewinmore (rank 1, pos 1, fluc 3.25)
  - #8 Smart Little Miss (rank 2, pos 9, fluc 26.0)
  - #10 Commands Success (rank 3, pos 5, fluc 41.0)
- Shadow Top3:
  - #2 Losesomewinmore (rank 1, pos 1, fluc 3.25)
  - #6 Call To Glory (rank 4, pos 2, fluc 4.6; market_live_le_15,market_live_le_8,shape_inconsistent,best_l600_top3_field,timing_improving)
  - #4 Mr Exclusive (rank 5, pos 10, fluc 1.8; market_live_le_15,market_live_le_8,shape_inconsistent,recent_l600_top3_field,timing_sharp_improving)

### Excuse/Run-Shape - 2025-08-23 Randwick Race 1-10 R2
- Context: Heavy / Other / Field 13+
- Hits: 1 -> 2
- Baseline Top3:
  - #2 Exit Fee (rank 1, pos 6, fluc 12.0)
  - #8 Xcessive Force (rank 2, pos 2, fluc 4.85)
  - #4 Calido Magic (rank 3, pos 5, fluc 16.0)
- Shadow Top3:
  - #2 Exit Fee (rank 1, pos 6, fluc 12.0)
  - #8 Xcessive Force (rank 2, pos 2, fluc 4.85)
  - #5 Neil (rank 4, pos 1, fluc 2.1)

### Timing Consistency - 2025-08-23 Randwick Race 1-10 R2
- Context: Heavy / Other / Field 13+
- Hits: 1 -> 2
- Baseline Top3:
  - #2 Exit Fee (rank 1, pos 6, fluc 12.0)
  - #8 Xcessive Force (rank 2, pos 2, fluc 4.85)
  - #4 Calido Magic (rank 3, pos 5, fluc 16.0)
- Shadow Top3:
  - #2 Exit Fee (rank 1, pos 6, fluc 12.0)
  - #8 Xcessive Force (rank 2, pos 2, fluc 4.85)
  - #5 Neil (rank 4, pos 1, fluc 2.1)

### Gear Change - 2025-08-23 Randwick Race 1-10 R2
- Context: Heavy / Other / Field 13+
- Hits: 1 -> 2
- Baseline Top3:
  - #2 Exit Fee (rank 1, pos 6, fluc 12.0)
  - #8 Xcessive Force (rank 2, pos 2, fluc 4.85)
  - #4 Calido Magic (rank 3, pos 5, fluc 16.0)
- Shadow Top3:
  - #2 Exit Fee (rank 1, pos 6, fluc 12.0)
  - #8 Xcessive Force (rank 2, pos 2, fluc 4.85)
  - #5 Neil (rank 4, pos 1, fluc 2.1)

### Combined Strict - 2025-08-23 Randwick Race 1-10 R2
- Context: Heavy / Other / Field 13+
- Hits: 1 -> 2
- Baseline Top3:
  - #2 Exit Fee (rank 1, pos 6, fluc 12.0)
  - #8 Xcessive Force (rank 2, pos 2, fluc 4.85)
  - #4 Calido Magic (rank 3, pos 5, fluc 16.0)
- Shadow Top3:
  - #2 Exit Fee (rank 1, pos 6, fluc 12.0)
  - #8 Xcessive Force (rank 2, pos 2, fluc 4.85)
  - #5 Neil (rank 4, pos 1, fluc 2.1)

### Combined Strict - 2025-08-23 Randwick Race 1-10 R3
- Context: Heavy / BM58-70 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #6 Piggyback (rank 1, pos 4, fluc 4.6)
  - #5 Bluestone (rank 2, pos 3, fluc 2.1)
  - #1 Juja Kibo (rank 3, pos 6, fluc 2.4)
- Shadow Top3:
  - #6 Piggyback (rank 1, pos 4, fluc 4.6)
  - #5 Bluestone (rank 2, pos 3, fluc 2.1)
  - #9 Wuddzz (rank 6, pos 1, fluc 7.0; market_live_le_15,market_live_le_8,shape_inconsistent,timing_sharp_improving)

### Market Flucs - 2025-08-23 Randwick Race 1-10 R9
- Context: Heavy / Group 2/3 / Field <=8
- Hits: 1 -> 2
- Baseline Top3:
  - #5 General Salute (rank 1, pos 3, fluc 2.1)
  - #8 Romeo's Choice (rank 2, pos 5, fluc 4.85)
  - #6 Corniche (rank 3, pos 6, fluc 3.6)
- Shadow Top3:
  - #4 Lazzura (rank 4, pos 1, fluc 5.5; market_live_le_15,market_live_le_8,firming_market)
  - #5 General Salute (rank 1, pos 3, fluc 2.1)
  - #8 Romeo's Choice (rank 2, pos 5, fluc 4.85)

### Market Strict Rescue - 2025-08-23 Randwick Race 1-10 R9
- Context: Heavy / Group 2/3 / Field <=8
- Hits: 1 -> 2
- Baseline Top3:
  - #5 General Salute (rank 1, pos 3, fluc 2.1)
  - #8 Romeo's Choice (rank 2, pos 5, fluc 4.85)
  - #6 Corniche (rank 3, pos 6, fluc 3.6)
- Shadow Top3:
  - #4 Lazzura (rank 4, pos 1, fluc 5.5; market_live_le_15,market_live_le_8,firming_market)
  - #5 General Salute (rank 1, pos 3, fluc 2.1)
  - #8 Romeo's Choice (rank 2, pos 5, fluc 4.85)

### Combined Formguide - 2025-08-23 Randwick Race 1-10 R9
- Context: Heavy / Group 2/3 / Field <=8
- Hits: 1 -> 2
- Baseline Top3:
  - #5 General Salute (rank 1, pos 3, fluc 2.1)
  - #8 Romeo's Choice (rank 2, pos 5, fluc 4.85)
  - #6 Corniche (rank 3, pos 6, fluc 3.6)
- Shadow Top3:
  - #4 Lazzura (rank 4, pos 1, fluc 5.5; market_live_le_15,market_live_le_8,firming_market,shape_inconsistent,recent_l600_top3_field,best_l600_top3_field,timing_sharp_declining)
  - #5 General Salute (rank 1, pos 3, fluc 2.1)
  - #8 Romeo's Choice (rank 2, pos 5, fluc 4.85)

### Combined Strict - 2025-08-23 Randwick Race 1-10 R9
- Context: Heavy / Group 2/3 / Field <=8
- Hits: 1 -> 2
- Baseline Top3:
  - #5 General Salute (rank 1, pos 3, fluc 2.1)
  - #8 Romeo's Choice (rank 2, pos 5, fluc 4.85)
  - #6 Corniche (rank 3, pos 6, fluc 3.6)
- Shadow Top3:
  - #4 Lazzura (rank 4, pos 1, fluc 5.5; market_live_le_15,market_live_le_8,firming_market,shape_inconsistent,recent_l600_top3_field,best_l600_top3_field,timing_sharp_declining)
  - #5 General Salute (rank 1, pos 3, fluc 2.1)
  - #8 Romeo's Choice (rank 2, pos 5, fluc 4.85)

### Market Flucs - 2025-08-23 Randwick Race 1-10 R10
- Context: Heavy / BM58-70 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #15 Island Dream (rank 1, pos 3, fluc 26.0)
  - #3 Louisville (rank 2, pos 5, fluc 8.5)
  - #8 Louie's Legacy (rank 3, pos 7, fluc 4.85)
- Shadow Top3:
  - #5 Glad You Think So (rank 5, pos 1, fluc 2.1; market_live_le_15,market_live_le_8,firming_market)
  - #11 Narbold (rank 4, pos 2, fluc 8.5; market_live_le_15,firming_market)
  - #3 Louisville (rank 2, pos 5, fluc 8.5)

### Market Strict Rescue - 2025-08-23 Randwick Race 1-10 R10
- Context: Heavy / BM58-70 / Field 9-12
- Hits: 1 -> 3
- Baseline Top3:
  - #15 Island Dream (rank 1, pos 3, fluc 26.0)
  - #3 Louisville (rank 2, pos 5, fluc 8.5)
  - #8 Louie's Legacy (rank 3, pos 7, fluc 4.85)
- Shadow Top3:
  - #5 Glad You Think So (rank 5, pos 1, fluc 2.1; market_live_le_15,market_live_le_8,firming_market)
  - #11 Narbold (rank 4, pos 2, fluc 8.5; market_live_le_15,firming_market)
  - #15 Island Dream (rank 1, pos 3, fluc 26.0)

### Excuse/Run-Shape - 2025-08-23 Randwick Race 1-10 R10
- Context: Heavy / BM58-70 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #15 Island Dream (rank 1, pos 3, fluc 26.0)
  - #3 Louisville (rank 2, pos 5, fluc 8.5)
  - #8 Louie's Legacy (rank 3, pos 7, fluc 4.85)
- Shadow Top3:
  - #3 Louisville (rank 2, pos 5, fluc 8.5)
  - #15 Island Dream (rank 1, pos 3, fluc 26.0; weak_engine_shape,stability_overtrust)
  - #11 Narbold (rank 4, pos 2, fluc 8.5)

### Timing Consistency - 2025-08-23 Randwick Race 1-10 R10
- Context: Heavy / BM58-70 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #15 Island Dream (rank 1, pos 3, fluc 26.0)
  - #3 Louisville (rank 2, pos 5, fluc 8.5)
  - #8 Louie's Legacy (rank 3, pos 7, fluc 4.85)
- Shadow Top3:
  - #3 Louisville (rank 2, pos 5, fluc 8.5)
  - #15 Island Dream (rank 1, pos 3, fluc 26.0; weak_engine_shape,stability_overtrust)
  - #11 Narbold (rank 4, pos 2, fluc 8.5)

### Gear Change - 2025-08-23 Randwick Race 1-10 R10
- Context: Heavy / BM58-70 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #15 Island Dream (rank 1, pos 3, fluc 26.0)
  - #3 Louisville (rank 2, pos 5, fluc 8.5)
  - #8 Louie's Legacy (rank 3, pos 7, fluc 4.85)
- Shadow Top3:
  - #3 Louisville (rank 2, pos 5, fluc 8.5)
  - #15 Island Dream (rank 1, pos 3, fluc 26.0; weak_engine_shape,stability_overtrust)
  - #11 Narbold (rank 4, pos 2, fluc 8.5)

### Combined Formguide - 2025-08-23 Randwick Race 1-10 R10
- Context: Heavy / BM58-70 / Field 9-12
- Hits: 1 -> 2
- Baseline Top3:
  - #15 Island Dream (rank 1, pos 3, fluc 26.0)
  - #3 Louisville (rank 2, pos 5, fluc 8.5)
  - #8 Louie's Legacy (rank 3, pos 7, fluc 4.85)
- Shadow Top3:
  - #5 Glad You Think So (rank 5, pos 1, fluc 2.1; market_live_le_15,market_live_le_8,firming_market,shape_inconsistent,timing_sharp_declining)
  - #11 Narbold (rank 4, pos 2, fluc 8.5; market_live_le_15,firming_market,shape_inconsistent,best_l600_top3_field,timing_declining)
  - #3 Louisville (rank 2, pos 5, fluc 8.5)

### Market Flucs - 2025-09-06 Randwick Race 1-10 R6
- Context: Good/Firm / Group 2/3 / Field 13+
- Hits: 1 -> 2
- Baseline Top3:
  - #1 Within The Law (rank 1, pos 5, fluc 3.8)
  - #3 Savvy Hallie (rank 2, pos 3, fluc 2.8)
  - #4 Memo (rank 3, pos 9, fluc 12.0)
- Shadow Top3:
  - #1 Within The Law (rank 1, pos 5, fluc 3.8)
  - #3 Savvy Hallie (rank 2, pos 3, fluc 2.8)
  - #16 Apocalyptic (rank 5, pos 1, fluc 4.0; market_live_le_15,market_live_le_8)

### Market Strict Rescue - 2025-09-06 Randwick Race 1-10 R6
- Context: Good/Firm / Group 2/3 / Field 13+
- Hits: 1 -> 2
- Baseline Top3:
  - #1 Within The Law (rank 1, pos 5, fluc 3.8)
  - #3 Savvy Hallie (rank 2, pos 3, fluc 2.8)
  - #4 Memo (rank 3, pos 9, fluc 12.0)
- Shadow Top3:
  - #1 Within The Law (rank 1, pos 5, fluc 3.8)
  - #3 Savvy Hallie (rank 2, pos 3, fluc 2.8)
  - #16 Apocalyptic (rank 5, pos 1, fluc 4.0; market_live_le_15,market_live_le_8)

### Combined Formguide - 2025-09-06 Randwick Race 1-10 R6
- Context: Good/Firm / Group 2/3 / Field 13+
- Hits: 1 -> 2
- Baseline Top3:
  - #1 Within The Law (rank 1, pos 5, fluc 3.8)
  - #3 Savvy Hallie (rank 2, pos 3, fluc 2.8)
  - #4 Memo (rank 3, pos 9, fluc 12.0)
- Shadow Top3:
  - #1 Within The Law (rank 1, pos 5, fluc 3.8)
  - #3 Savvy Hallie (rank 2, pos 3, fluc 2.8)
  - #16 Apocalyptic (rank 5, pos 1, fluc 4.0; market_live_le_15,market_live_le_8,shape_inconsistent,recent_l600_top3_field)

### Combined Strict - 2025-09-06 Randwick Race 1-10 R6
- Context: Good/Firm / Group 2/3 / Field 13+
- Hits: 1 -> 2
- Baseline Top3:
  - #1 Within The Law (rank 1, pos 5, fluc 3.8)
  - #3 Savvy Hallie (rank 2, pos 3, fluc 2.8)
  - #4 Memo (rank 3, pos 9, fluc 12.0)
- Shadow Top3:
  - #1 Within The Law (rank 1, pos 5, fluc 3.8)
  - #3 Savvy Hallie (rank 2, pos 3, fluc 2.8)
  - #16 Apocalyptic (rank 5, pos 1, fluc 4.0; market_live_le_15,market_live_le_8,shape_inconsistent,recent_l600_top3_field)

### Market Flucs - 2025-09-06 Randwick Race 1-10 R9
- Context: Good/Firm / Group 2/3 / Field 13+
- Hits: 0 -> 1
- Baseline Top3:
  - #6 Kovalica (rank 1, pos 11, fluc 23.0)
  - #17 Depth Of Character (rank 2, pos 12, fluc 21.0)
  - #15 Swiftfalcon (rank 3, pos 6, fluc 4.4)
- Shadow Top3:
  - #6 Kovalica (rank 1, pos 11, fluc 23.0)
  - #17 Depth Of Character (rank 2, pos 12, fluc 21.0)
  - #5 Private Eye (rank 4, pos 2, fluc 2.0; market_live_le_15,market_live_le_8,firming_market)

### Market Strict Rescue - 2025-09-06 Randwick Race 1-10 R9
- Context: Good/Firm / Group 2/3 / Field 13+
- Hits: 0 -> 1
- Baseline Top3:
  - #6 Kovalica (rank 1, pos 11, fluc 23.0)
  - #17 Depth Of Character (rank 2, pos 12, fluc 21.0)
  - #15 Swiftfalcon (rank 3, pos 6, fluc 4.4)
- Shadow Top3:
  - #6 Kovalica (rank 1, pos 11, fluc 23.0)
  - #17 Depth Of Character (rank 2, pos 12, fluc 21.0)
  - #5 Private Eye (rank 4, pos 2, fluc 2.0; market_live_le_15,market_live_le_8,firming_market)

