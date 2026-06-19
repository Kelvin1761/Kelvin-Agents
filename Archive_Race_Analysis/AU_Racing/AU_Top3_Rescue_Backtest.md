# AU Top3 Rescue Backtest

Analysis-first shadow test. The 7D matrix scores and live ranking engine are unchanged.

## Overall Metrics

| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 336 | 22.3% | 4.2% | 17.6% | 38.1% | 51.8% | 69.3% | 42.9% | 46 | 162 | 114 | 14 |
| Conservative Flags | 336 | 22.3% | 4.2% | 17.6% | 38.1% | 51.8% | 69.3% | 42.9% | 46 | 162 | 114 | 14 |
| Controlled Market-Free | 336 | 22.0% | 3.3% | 16.4% | 36.3% | 50.0% | 69.6% | 41.7% | 49 | 165 | 111 | 11 |
| Controlled Market-Aware | 336 | 22.0% | 4.5% | 18.5% | 39.9% | 53.0% | 69.3% | 43.7% | 45 | 157 | 119 | 15 |

## Delta vs Baseline

| Version | Gold Δ | Good Δ | Pass Δ | 0-hit Δ | 1-hit Δ | Top3 places Δ | Winner Top5 Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Conservative Flags | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| Controlled Market-Free | -3 | -4 | -6 | +3 | +3 | -12 | +1 |
| Controlled Market-Aware | +1 | +3 | +6 | -1 | -5 | +8 | +0 |

## Rescue/Risk Flag Quality

| Flag Set | Races With Candidate | Candidates | Candidate Actual Top3 | Races With Risk | Risks | Risk Failed Top3 |
|---|---:|---:|---:|---:|---:|---:|
| Market-Free | 308 | 805 | 231 (28.7%) | 126 | 218 | 119 (54.6%) |
| Market-Aware | 308 | 805 | 231 (28.7%) | 158 | 254 | 152 (59.8%) |

Top market-free rescue reasons:
- rank4_6: **805**
- score_gap_le_2: **778**
- stable_enough: **742**
- distance_ok: **672**
- jt_or_trial_support: **506**
- market_live: **455**
- track_ok: **416**
- class_weight_ok: **389**

Top market-free overrating risk reasons:
- weak_engine_and_shape: **214**
- multi_structural_weakness: **10**
- stability_formline_overtrust: **6**

## Controlled Swap Quality

| Version | Swaps | Improved | Same | Worse | High-Odds Swap-In | High-Odds Swap-In Actual Top3 | Short-Odds Swap-Out | Short-Odds Swap-Out Actual Top3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Controlled Market-Free | 94 | 19 | 44 | 31 | 31 | 5 | 50 | 33 |
| Controlled Market-Aware | 65 | 19 | 35 | 11 | 13 | 3 | 1 | 1 |

## Segment Deltas

### Condition

| Segment | Version | Races | Gold | Good | Pass | 0-hit | 1-hit | Top3 Place |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Good/Firm | Baseline | 238 | 4.2% | 18.1% | 37.0% | 30 | 120 | 42.9% |
| Good/Firm | Controlled Market-Free | 238 | 2.9% | 17.2% | 35.7% | 34 | 119 | 41.5% |
| Good/Firm | Controlled Market-Aware | 238 | 4.2% | 18.5% | 38.7% | 31 | 115 | 43.3% |
| Soft | Baseline | 69 | 5.8% | 15.9% | 37.7% | 14 | 29 | 41.1% |
| Soft | Controlled Market-Free | 69 | 4.3% | 14.5% | 31.9% | 13 | 34 | 39.1% |
| Soft | Controlled Market-Aware | 69 | 5.8% | 18.8% | 37.7% | 12 | 31 | 42.0% |
| Heavy | Baseline | 29 | 0.0% | 17.2% | 48.3% | 2 | 13 | 47.1% |
| Heavy | Controlled Market-Free | 29 | 3.4% | 13.8% | 51.7% | 2 | 12 | 49.4% |
| Heavy | Controlled Market-Aware | 29 | 3.4% | 17.2% | 55.2% | 2 | 11 | 50.6% |

### Class

| Segment | Version | Races | Gold | Good | Pass | 0-hit | 1-hit | Top3 Place |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| BM58-70 | Baseline | 121 | 4.1% | 19.8% | 38.0% | 15 | 60 | 43.3% |
| BM58-70 | Controlled Market-Free | 121 | 3.3% | 14.9% | 33.1% | 17 | 64 | 40.8% |
| BM58-70 | Controlled Market-Aware | 121 | 4.1% | 18.2% | 38.0% | 15 | 60 | 43.3% |
| Other | Baseline | 88 | 3.4% | 18.2% | 44.3% | 14 | 35 | 43.9% |
| Other | Controlled Market-Free | 88 | 3.4% | 18.2% | 42.0% | 13 | 38 | 43.6% |
| Other | Controlled Market-Aware | 88 | 4.5% | 20.5% | 47.7% | 12 | 34 | 46.2% |
| Group 2/3 | Baseline | 66 | 4.5% | 12.1% | 28.8% | 11 | 36 | 38.9% |
| Group 2/3 | Controlled Market-Free | 66 | 3.0% | 12.1% | 31.8% | 11 | 34 | 39.4% |
| Group 2/3 | Controlled Market-Aware | 66 | 4.5% | 15.2% | 31.8% | 11 | 34 | 39.9% |
| Group 1 | Baseline | 29 | 3.4% | 20.7% | 37.9% | 3 | 15 | 43.7% |
| Group 1 | Controlled Market-Free | 29 | 0.0% | 20.7% | 37.9% | 4 | 14 | 41.4% |
| Group 1 | Controlled Market-Aware | 29 | 3.4% | 24.1% | 37.9% | 4 | 14 | 42.5% |
| BM72-84 | Baseline | 17 | 0.0% | 11.8% | 47.1% | 1 | 8 | 47.1% |
| BM72-84 | Controlled Market-Free | 17 | 5.9% | 23.5% | 47.1% | 2 | 7 | 47.1% |
| BM72-84 | Controlled Market-Aware | 17 | 0.0% | 11.8% | 52.9% | 1 | 7 | 49.0% |
| Maiden | Baseline | 10 | 0.0% | 0.0% | 20.0% | 2 | 6 | 33.3% |
| Maiden | Controlled Market-Free | 10 | 0.0% | 0.0% | 20.0% | 2 | 6 | 33.3% |
| Maiden | Controlled Market-Aware | 10 | 0.0% | 0.0% | 20.0% | 2 | 6 | 33.3% |
| BM88+ | Baseline | 5 | 40.0% | 60.0% | 60.0% | 0 | 2 | 66.7% |
| BM88+ | Controlled Market-Free | 5 | 20.0% | 60.0% | 60.0% | 0 | 2 | 60.0% |
| BM88+ | Controlled Market-Aware | 5 | 40.0% | 60.0% | 60.0% | 0 | 2 | 66.7% |

### Field Size

| Segment | Version | Races | Gold | Good | Pass | 0-hit | 1-hit | Top3 Place |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Field 9-12 | Baseline | 193 | 4.1% | 15.0% | 33.2% | 26 | 103 | 41.3% |
| Field 9-12 | Controlled Market-Free | 193 | 3.6% | 15.0% | 31.6% | 27 | 105 | 40.4% |
| Field 9-12 | Controlled Market-Aware | 193 | 4.1% | 16.6% | 35.2% | 24 | 101 | 42.3% |
| Field 13+ | Baseline | 88 | 2.3% | 12.5% | 29.5% | 17 | 45 | 37.5% |
| Field 13+ | Controlled Market-Free | 88 | 2.3% | 9.1% | 28.4% | 19 | 44 | 36.4% |
| Field 13+ | Controlled Market-Aware | 88 | 4.5% | 13.6% | 31.8% | 18 | 42 | 38.6% |
| Field <=8 | Baseline | 55 | 7.3% | 34.5% | 69.1% | 3 | 14 | 57.0% |
| Field <=8 | Controlled Market-Free | 55 | 3.6% | 32.7% | 65.5% | 3 | 16 | 54.5% |
| Field <=8 | Controlled Market-Aware | 55 | 5.5% | 32.7% | 69.1% | 3 | 14 | 56.4% |

## Kensington Gate

- PASS - Kensington standalone check: #4 Existential Bob is flagged (rank 5, score 64.90, reasons=rank4_6,score_gap_le_2,stable_enough,class_weight_ok,jt_or_trial_support).

## 0/1-Hit Focus Examples

### 2025-08-02 Flemington Race 1-9 R4 (1-hit)
- Context: Good/Firm / BM72-84 / Field 9-12
- Baseline Top3:
  - #2 Losesomewinmore (rank 1, score 63.12, pos 1, SP 3.8)
  - #8 Smart Little Miss (rank 2, score 62.05, pos 9, SP 61.0)
  - #10 Commands Success (rank 3, score 61.52, pos 5, SP 101.0)
- Market-free rescue candidates:
  - #6 Call To Glory (rank 4, score 61.40, pos 2, SP 9.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,market_live; rescue_score=5.68
  - #3 Eye Of The Fire (rank 6, score 61.15, pos 4, SP 7.5); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,market_live; rescue_score=4.15
- Market-free Top3 risks:
  - #8 Smart Little Miss (rank 2, score 62.05, pos 9, SP 61.0); reasons=weak_engine_and_shape; risk_score=1.10
  - #10 Commands Success (rank 3, score 61.52, pos 5, SP 101.0); reasons=weak_engine_and_shape; risk_score=1.10

### 2025-08-02 Flemington Race 1-9 R5 (1-hit)
- Context: Good/Firm / BM72-84 / Field 9-12
- Baseline Top3:
  - #1 Aztec State (rank 1, score 63.82, pos 5, SP 3.9)
  - #9 Paradise Storm (rank 2, score 63.73, pos 10, SP 19.0)
  - #18 Maisy (rank 3, score 62.40, pos 3, SP 5.5)
- Market-free rescue candidates:
  - #12 Catani Gardens (rank 4, score 62.19, pos 7, SP 18.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok; rescue_score=4.27
  - #14 Federer (rank 5, score 62.15, pos 2, SP 2.4); reasons=rank4_6,score_gap_le_2,stable_enough,jt_or_trial_support,market_live; rescue_score=4.24
- Market-free Top3 risks:
  - None

### 2025-08-02 Flemington Race 1-9 R8 (1-hit)
- Context: Good/Firm / BM72-84 / Field 13+
- Baseline Top3:
  - #11 One Long Day (rank 1, score 65.94, pos 10, SP 3.5)
  - #3 Hard To Cross (rank 2, score 64.37, pos 3, SP 16.0)
  - #7 Whisky On The Hill (rank 3, score 64.20, pos 8, SP 31.0)
- Market-free rescue candidates:
  - #15 Too Darn Discreet (rank 4, score 64.01, pos 1, SP 26.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,track_ok; rescue_score=6.68
  - #14 He'll Rip (rank 5, score 63.82, pos 11, SP 11.0); reasons=rank4_6,score_gap_le_2,stable_enough,class_weight_ok,jt_or_trial_support,track_ok,market_live; rescue_score=5.69
  - #10 Black Storm (rank 6, score 63.59, pos 7, SP 8.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,market_live; rescue_score=3.97
- Market-free Top3 risks:
  - None

### 2025-08-23 Randwick Race 1-10 R2 (1-hit)
- Context: Heavy / Other / Field 13+
- Baseline Top3:
  - #2 Exit Fee (rank 1, score 64.73, pos 6, SP 3.7)
  - #8 Xcessive Force (rank 2, score 64.16, pos 2, SP 4.6)
  - #4 Calido Magic (rank 3, score 63.79, pos 5, SP 26.0)
- Market-free rescue candidates:
  - #5 Neil (rank 4, score 63.50, pos 1, SP 11.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,jt_or_trial_support,market_live; rescue_score=4.76
  - #12 Dekadance (rank 6, score 63.12, pos 9, SP 26.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok; rescue_score=4.72
  - #10 Beyond My Ken (rank 5, score 63.24, pos 12, SP 12.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,jt_or_trial_support,market_live; rescue_score=4.56
- Market-free Top3 risks:
  - #4 Calido Magic (rank 3, score 63.79, pos 5, SP 26.0); reasons=weak_engine_and_shape; risk_score=1.10

### 2025-08-23 Randwick Race 1-10 R3 (1-hit)
- Context: Heavy / BM58-70 / Field 9-12
- Baseline Top3:
  - #6 Piggyback (rank 1, score 65.05, pos 4, SP 5.0)
  - #5 Bluestone (rank 2, score 64.81, pos 3, SP 3.8)
  - #1 Juja Kibo (rank 3, score 63.76, pos 6, SP 3.0)
- Market-free rescue candidates:
  - #4 Cormac T (rank 5, score 63.60, pos 2, SP 19.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok; rescue_score=5.41
  - #11 Stylebender (rank 4, score 63.66, pos 9, SP 61.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok; rescue_score=5.15
  - #9 Wuddzz (rank 6, score 63.41, pos 1, SP 10.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,track_ok,market_live; rescue_score=4.91
- Market-free Top3 risks:
  - None

### 2025-08-23 Randwick Race 1-10 R9 (1-hit)
- Context: Heavy / Group 2/3 / Field <=8
- Baseline Top3:
  - #5 General Salute (rank 1, score 64.38, pos 3, SP 4.2)
  - #8 Romeo's Choice (rank 2, score 64.22, pos 5, SP 9.5)
  - #6 Corniche (rank 3, score 63.86, pos 6, SP 3.8)
- Market-free rescue candidates:
  - #4 Lazzura (rank 4, score 63.57, pos 1, SP 6.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,track_ok,market_live; rescue_score=6.06
  - #7 With Your Blessing (rank 5, score 63.25, pos 2, SP 17.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,track_ok; rescue_score=5.52
  - #12 Just Feelin' Lucky (rank 6, score 62.85, pos 8, SP 6.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,market_live; rescue_score=5.02
- Market-free Top3 risks:
  - None

### 2025-08-23 Randwick Race 1-10 R10 (1-hit)
- Context: Heavy / BM58-70 / Field 9-12
- Baseline Top3:
  - #15 Island Dream (rank 1, score 64.14, pos 3, SP 5.5)
  - #3 Louisville (rank 2, score 63.91, pos 5, SP 31.0)
  - #8 Louie's Legacy (rank 3, score 63.49, pos 7, SP 21.0)
- Market-free rescue candidates:
  - #11 Narbold (rank 4, score 63.14, pos 2, SP 4.2); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,market_live; rescue_score=5.51
  - #5 Glad You Think So (rank 5, score 63.12, pos 1, SP 3.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,jt_or_trial_support,track_ok,market_live; rescue_score=4.55
  - #1 Hutchence (rank 6, score 63.04, pos 6, SP 41.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok; rescue_score=4.09
- Market-free Top3 risks:
  - #15 Island Dream (rank 1, score 64.14, pos 3, SP 5.5); reasons=weak_engine_and_shape; risk_score=1.10
  - #8 Louie's Legacy (rank 3, score 63.49, pos 7, SP 21.0); reasons=weak_engine_and_shape; risk_score=1.10

### 2025-09-06 Randwick Race 1-10 R2 (1-hit)
- Context: Good/Firm / Other / Field 13+
- Baseline Top3:
  - #5 So Magnificent (rank 1, score 72.79, pos 1, SP 8.0)
  - #14 Lightning Speed (rank 2, score 72.24, pos 16, SP 7.0)
  - #19 Graceful Ellen (rank 3, score 71.92, pos 13, SP 31.0)
- Market-free rescue candidates:
  - #1 Highway Strip (rank 5, score 71.12, pos 6, SP 3.7); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,track_ok,market_live; rescue_score=6.08
  - #16 Poisen Point (rank 4, score 71.15, pos 4, SP 20.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support; rescue_score=5.35
  - #15 Zumbo (rank 6, score 70.92, pos 2, SP 7.0); reasons=rank4_6,score_gap_le_2,stable_enough,class_weight_ok,jt_or_trial_support,market_live; rescue_score=5.18
- Market-free Top3 risks:
  - None

### 2025-09-06 Randwick Race 1-10 R6 (1-hit)
- Context: Good/Firm / Group 2/3 / Field 13+
- Baseline Top3:
  - #1 Within The Law (rank 1, score 74.03, pos 5, SP 4.2)
  - #3 Savvy Hallie (rank 2, score 71.77, pos 3, SP 2.9)
  - #4 Memo (rank 3, score 68.46, pos 9, SP 26.0)
- Market-free rescue candidates:
  - #2 Tupakara (rank 4, score 67.84, pos 2, SP 12.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,track_ok,market_live; rescue_score=6.51
  - #6 Stardom (rank 6, score 67.65, pos 11, SP 13.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,market_live; rescue_score=4.92
- Market-free Top3 risks:
  - None

### 2025-09-06 Randwick Race 1-10 R7 (1-hit)
- Context: Good/Firm / Group 2/3 / Field 9-12
- Baseline Top3:
  - #1 Arapaho (rank 1, score 71.10, pos 6, SP 12.0)
  - #2 Ceolwulf (rank 2, score 70.89, pos 4, SP 1.8)
  - #5 Sir Delius (rank 3, score 68.97, pos 2, SP 5.5)
- Market-free rescue candidates:
  - #10 Birdman (rank 4, score 67.77, pos 5, SP 26.0); reasons=rank4_6,score_gap_le_2,distance_ok,jt_or_trial_support,track_ok; rescue_score=4.07
  - #3 Vauban (rank 5, score 66.96, pos 3, SP 15.0); reasons=rank4_6,jt_or_trial_support,market_live; rescue_score=3.27
- Market-free Top3 risks:
  - None

### 2025-09-06 Randwick Race 1-10 R9 (0-hit)
- Context: Good/Firm / Group 2/3 / Field 13+
- Baseline Top3:
  - #6 Kovalica (rank 1, score 70.98, pos 11, SP 61.0)
  - #17 Depth Of Character (rank 2, score 70.94, pos 12, SP 51.0)
  - #15 Swiftfalcon (rank 3, score 69.47, pos 6, SP 6.0)
- Market-free rescue candidates:
  - #5 Private Eye (rank 4, score 69.25, pos 2, SP 2.1); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,track_ok,market_live; rescue_score=7.06
  - #14 With Your Blessing (rank 5, score 68.35, pos 3, SP 19.0); reasons=rank4_6,score_gap_le_2,stable_enough,class_weight_ok,jt_or_trial_support,track_ok; rescue_score=5.13
- Market-free Top3 risks:
  - None

### 2025-09-13 Flemington Race 1-10 R1 (1-hit)
- Context: Good/Firm / BM58-70 / Field 13+
- Baseline Top3:
  - #15 Persian Spirit (rank 1, score 72.59, pos 1, SP 51.0)
  - #10 She's An Artist (rank 2, score 71.78, pos 4, SP 1.9)
  - #2 De Bergerac (rank 3, score 71.20, pos 5, SP 41.0)
- Market-free rescue candidates:
  - #8 Tonkin (rank 4, score 70.75, pos 2, SP 8.5); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,market_live; rescue_score=6.14
  - #6 Salsa Fellow (rank 5, score 69.30, pos 14, SP 41.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,jt_or_trial_support,track_ok; rescue_score=3.90
- Market-free Top3 risks:
  - None

### 2025-09-13 Flemington Race 1-10 R2 (1-hit)
- Context: Good/Firm / Other / Field <=8
- Baseline Top3:
  - #4 Shining Smile (rank 1, score 70.59, pos 4, SP 13.0)
  - #2 Tycoon Star (rank 2, score 68.86, pos 3, SP 2.3)
  - #5 Mcgaw (rank 3, score 68.72, pos 5, SP 4.2)
- Market-free rescue candidates:
  - #3 Legacy Bound (rank 4, score 68.14, pos 1, SP 6.0); reasons=rank4_6,score_gap_le_2,stable_enough,jt_or_trial_support,market_live; rescue_score=4.54
- Market-free Top3 risks:
  - None

### 2025-09-13 Flemington Race 1-10 R3 (0-hit)
- Context: Good/Firm / Other / Field 9-12
- Baseline Top3:
  - #3 Crossbow (rank 1, score 73.18, pos 9, SP 5.5)
  - #12 Just Kick (rank 2, score 70.35, pos 7, SP 10.0)
  - #4 Prestige Ole (rank 3, score 68.87, pos 5, SP 31.0)
- Market-free rescue candidates:
  - #1 Vinrock (rank 4, score 68.84, pos 1, SP 2.8); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,track_ok,market_live; rescue_score=7.20
  - #5 Arcora (rank 5, score 68.58, pos 10, SP 61.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,track_ok; rescue_score=6.06
  - #10 Fastoso (rank 6, score 67.48, pos 8, SP 18.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,jt_or_trial_support; rescue_score=4.08
- Market-free Top3 risks:
  - None

### 2025-09-13 Flemington Race 1-10 R5 (0-hit)
- Context: Good/Firm / Maiden / Field 9-12
- Baseline Top3:
  - #10 Athanatos (rank 1, score 70.95, pos 6, SP 7.5)
  - #12 Wonder Boy (rank 2, score 70.82, pos 9, SP 6.0)
  - #6 Pop Award (rank 3, score 69.22, pos 8, SP 10.0)
- Market-free rescue candidates:
  - #8 Gerringong (rank 4, score 68.56, pos 4, SP 10.0); reasons=rank4_6,score_gap_le_2,stable_enough,class_weight_ok,jt_or_trial_support,market_live; rescue_score=4.88
  - #3 Transatlantic (rank 5, score 67.88, pos 2, SP 5.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,jt_or_trial_support,market_live; rescue_score=4.87
  - #4 Cafe Millenium (rank 6, score 67.71, pos 1, SP 9.0); reasons=rank4_6,score_gap_le_2,distance_ok,jt_or_trial_support,track_ok,market_live; rescue_score=3.84
- Market-free Top3 risks:
  - None

### 2025-09-13 Flemington Race 1-10 R6 (1-hit)
- Context: Good/Firm / Group 2/3 / Field 9-12
- Baseline Top3:
  - #9 Enxuto (rank 1, score 69.19, pos 7, SP 51.0)
  - #4 Arkansaw Kid (rank 2, score 68.84, pos 1, SP 3.2)
  - #3 Steparty (rank 3, score 67.60, pos 8, SP 13.0)
- Market-free rescue candidates:
  - #10 Media World (rank 4, score 66.61, pos 3, SP 8.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,market_live; rescue_score=4.48
  - #1 Tuvalu (rank 5, score 65.71, pos 11, SP 41.0); reasons=rank4_6,score_gap_le_2,distance_ok,class_weight_ok,jt_or_trial_support,track_ok; rescue_score=4.36
- Market-free Top3 risks:
  - None

### 2025-09-13 Flemington Race 1-10 R9 (0-hit)
- Context: Good/Firm / Group 2/3 / Field 13+
- Baseline Top3:
  - #13 Bossy Benita (rank 1, score 70.98, pos 11, SP 21.0)
  - #7 On Display (rank 2, score 70.13, pos 10, SP 6.5)
  - #11 Splash Back (rank 3, score 69.98, pos 5, SP 13.0)
- Market-free rescue candidates:
  - #3 Lazzura (rank 4, score 69.74, pos 1, SP 2.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support,market_live; rescue_score=6.29
  - #2 Marble Arch (rank 5, score 69.28, pos 6, SP 18.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,jt_or_trial_support,track_ok; rescue_score=5.90
  - #1 Leica Lucy (rank 6, score 68.51, pos 4, SP 31.0); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,class_weight_ok,jt_or_trial_support; rescue_score=4.57
- Market-free Top3 risks:
  - #13 Bossy Benita (rank 1, score 70.98, pos 11, SP 21.0); reasons=stability_formline_overtrust; risk_score=1.60

### 2025-09-21 Flemington Race 1-8 R1 (1-hit)
- Context: Good/Firm / BM58-70 / Field 9-12
- Baseline Top3:
  - #9 Thurmond (rank 1, score 63.99, pos 6, SP 6.0)
  - #11 Haaland (rank 2, score 62.53, pos 2, SP 14.0)
  - #1 Navy King (rank 3, score 62.51, pos 7, SP 7.5)
- Market-free rescue candidates:
  - #2 Wuddzz (rank 4, score 61.92, pos 8, SP 5.5); reasons=rank4_6,score_gap_le_2,stable_enough,distance_ok,market_live; rescue_score=4.53
- Market-free Top3 risks:
  - #11 Haaland (rank 2, score 62.53, pos 2, SP 14.0); reasons=multi_structural_weakness,weak_engine_and_shape; risk_score=2.30
  - #9 Thurmond (rank 1, score 63.99, pos 6, SP 6.0); reasons=weak_engine_and_shape; risk_score=1.10

## Controlled Swap Examples

### 2025-08-02 Flemington Race 1-9 R1
- Baseline hits: 3; market-free hits: 2; market-aware hits: 2
- Market-free swap in: #3 Our Chief (rank 4, score 60.17, pos 5, SP 4.4)
- Market-free swap out: #1 Hillier (rank 2, score 61.43, pos 2, SP 9.0)
- Market-aware swap in: #3 Our Chief (rank 4, score 60.17, pos 5, SP 4.4)
- Market-aware swap out: #1 Hillier (rank 2, score 61.43, pos 2, SP 9.0)

### 2025-08-02 Flemington Race 1-9 R3
- Baseline hits: 2; market-free hits: 2; market-aware hits: 2
- Market-free swap in: #15 She's Pretty Rich (rank 4, score 64.16, pos 11, SP 26.0)
- Market-free swap out: #10 Prevailed (rank 3, score 64.46, pos 4, SP 19.0)
- Market-aware swap in: #15 She's Pretty Rich (rank 4, score 64.16, pos 11, SP 26.0)
- Market-aware swap out: #10 Prevailed (rank 3, score 64.46, pos 4, SP 19.0)

### 2025-08-02 Flemington Race 1-9 R4
- Baseline hits: 1; market-free hits: 2; market-aware hits: 2
- Market-free swap in: #6 Call To Glory (rank 4, score 61.40, pos 2, SP 9.0)
- Market-free swap out: #8 Smart Little Miss (rank 2, score 62.05, pos 9, SP 61.0)
- Market-aware swap in: #6 Call To Glory (rank 4, score 61.40, pos 2, SP 9.0)
- Market-aware swap out: #10 Commands Success (rank 3, score 61.52, pos 5, SP 101.0)

### 2025-08-02 Flemington Race 1-9 R9
- Baseline hits: 2; market-free hits: 2; market-aware hits: 2
- Market-free swap in: #5 Capricorn Star (rank 4, score 64.29, pos 8, SP 31.0)
- Market-free swap out: #4 Terrestar (rank 2, score 64.72, pos 2, SP 9.0)
- Market-aware swap in: #15 Ten Deep (rank 5, score 63.99, pos 9, SP 3.6)
- Market-aware swap out: #4 Terrestar (rank 2, score 64.72, pos 2, SP 9.0)

### 2025-08-23 Randwick Race 1-10 R1
- Baseline hits: 2; market-free hits: 1; market-aware hits: 2
- Market-free swap in: #16 Close Encounter (rank 4, score 62.51, pos 5, SP 16.0)
- Market-free swap out: #12 Divine Bene (rank 3, score 63.20, pos 3, SP 4.4)

### 2025-08-23 Randwick Race 1-10 R2
- Baseline hits: 1; market-free hits: 2; market-aware hits: 2
- Market-free swap in: #5 Neil (rank 4, score 63.50, pos 1, SP 11.0)
- Market-free swap out: #4 Calido Magic (rank 3, score 63.79, pos 5, SP 26.0)
- Market-aware swap in: #5 Neil (rank 4, score 63.50, pos 1, SP 11.0)
- Market-aware swap out: #4 Calido Magic (rank 3, score 63.79, pos 5, SP 26.0)

### 2025-08-23 Randwick Race 1-10 R10
- Baseline hits: 1; market-free hits: 2; market-aware hits: 2
- Market-free swap in: #11 Narbold (rank 4, score 63.14, pos 2, SP 4.2)
- Market-free swap out: #8 Louie's Legacy (rank 3, score 63.49, pos 7, SP 21.0)
- Market-aware swap in: #11 Narbold (rank 4, score 63.14, pos 2, SP 4.2)
- Market-aware swap out: #8 Louie's Legacy (rank 3, score 63.49, pos 7, SP 21.0)

### 2025-09-21 Flemington Race 1-8 R1
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #2 Wuddzz (rank 4, score 61.92, pos 8, SP 5.5)
- Market-free swap out: #11 Haaland (rank 2, score 62.53, pos 2, SP 14.0)
- Market-aware swap in: #2 Wuddzz (rank 4, score 61.92, pos 8, SP 5.5)
- Market-aware swap out: #11 Haaland (rank 2, score 62.53, pos 2, SP 14.0)

### 2025-09-21 Flemington Race 1-8 R3
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #11 Farewell To Eire (rank 4, score 60.71, pos 5, SP 26.0)
- Market-free swap out: #2 She's A Hustler (rank 2, score 61.74, pos 1, SP 2.4)

### 2025-09-21 Flemington Race 1-8 R4
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #1 Vivideel (rank 5, score 63.27, pos 10, SP 51.0)
- Market-free swap out: #9 Black Peppermint (rank 3, score 64.24, pos 6, SP 41.0)
- Market-aware swap in: #1 Vivideel (rank 5, score 63.27, pos 10, SP 51.0)
- Market-aware swap out: #9 Black Peppermint (rank 3, score 64.24, pos 6, SP 41.0)

### 2025-09-21 Flemington Race 1-8 R6
- Baseline hits: 1; market-free hits: 2; market-aware hits: 1
- Market-free swap in: #15 Per Sempre (rank 4, score 64.14, pos 1, SP 21.0)
- Market-free swap out: #12 Sun Setting (rank 2, score 64.46, pos 2, SP 2.9)

### 2025-10-04 Flemington Race 1-10 R3
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-aware swap in: #11 Arabian Prince (rank 4, score 61.82, pos 5, SP 9.5)
- Market-aware swap out: #10 Super Paradise (rank 3, score 62.39, pos 10, SP 151.0)

### 2025-10-04 Flemington Race 1-10 R4
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #3 Spicy Lu (rank 4, score 62.44, pos 8, SP 8.0)
- Market-free swap out: #2 Zany Girl (rank 2, score 63.41, pos 4, SP 8.5)
- Market-aware swap in: #3 Spicy Lu (rank 4, score 62.44, pos 8, SP 8.0)
- Market-aware swap out: #2 Zany Girl (rank 2, score 63.41, pos 4, SP 8.5)

### 2025-10-04 Flemington Race 1-10 R5
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-aware swap in: #5 Running By (rank 4, score 63.57, pos 10, SP 18.0)
- Market-aware swap out: #8 Terrestar (rank 3, score 63.72, pos 8, SP 51.0)

### 2025-10-04 Randwick Race 1-10 R4
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #7 Attica (rank 5, score 61.69, pos 1, SP 4.2)
- Market-free swap out: #1 Without Peer (rank 2, score 62.15, pos 6, SP 3.5)

### 2025-11-01 Flemington Race 1-9 R4
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #7 Fashionable (rank 5, score 61.07, pos 4, SP 7.5)
- Market-free swap out: #2 Ethereum Girl (rank 3, score 62.23, pos 6, SP 14.0)
- Market-aware swap in: #7 Fashionable (rank 5, score 61.07, pos 4, SP 7.5)
- Market-aware swap out: #2 Ethereum Girl (rank 3, score 62.23, pos 6, SP 14.0)

### 2025-11-01 Randwick Race 1-10 R1
- Baseline hits: 2; market-free hits: 3; market-aware hits: 2
- Market-free swap in: #4 Strawberry Impact (rank 4, score 61.55, pos 2, SP 3.7)
- Market-free swap out: #5 Chicama (rank 3, score 61.87, pos 6, SP 4.0)

### 2025-11-01 Randwick Race 1-10 R2
- Baseline hits: 1; market-free hits: 0; market-aware hits: 1
- Market-free swap in: #14 Swinging High (rank 4, score 63.38, pos 4, SP 18.0)
- Market-free swap out: #2 Pony Soprano (rank 2, score 63.84, pos 3, SP 7.5)
- Market-aware swap in: #14 Swinging High (rank 4, score 63.38, pos 4, SP 18.0)
- Market-aware swap out: #10 Lightning Speed (rank 3, score 63.84, pos 15, SP 10.0)

### 2025-11-01 Randwick Race 1-10 R3
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #8 Transcend (rank 5, score 62.72, pos 2, SP 3.0)
- Market-free swap out: #9 Bravissima (rank 3, score 63.16, pos 1, SP 41.0)
- Market-aware swap in: #8 Transcend (rank 5, score 62.72, pos 2, SP 3.0)
- Market-aware swap out: #9 Bravissima (rank 3, score 63.16, pos 1, SP 41.0)

### 2025-11-01 Randwick Race 1-10 R5
- Baseline hits: 2; market-free hits: 2; market-aware hits: 2
- Market-free swap in: #9 Harlow Mist (rank 4, score 62.72, pos 4, SP 7.0)
- Market-free swap out: #12 United Kingdom (rank 2, score 63.34, pos 3, SP 3.6)
- Market-aware swap in: #9 Harlow Mist (rank 4, score 62.72, pos 4, SP 7.0)
- Market-aware swap out: #4 Majorian (rank 3, score 63.01, pos 9, SP 20.0)

### 2025-11-01 Randwick Race 1-10 R6
- Baseline hits: 2; market-free hits: 2; market-aware hits: 2
- Market-free swap in: #8 Istolea Merc (rank 4, score 63.30, pos 6, SP 2.6)
- Market-free swap out: #6 The Astronomer (rank 3, score 63.52, pos 5, SP 51.0)
- Market-aware swap in: #8 Istolea Merc (rank 4, score 63.30, pos 6, SP 2.6)
- Market-aware swap out: #6 The Astronomer (rank 3, score 63.52, pos 5, SP 51.0)

### 2025-11-04 Flemington Race 1-10 R3
- Baseline hits: 2; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #9 Arabian Prince (rank 6, score 61.56, pos 6, SP 5.5)
- Market-free swap out: #5 Brave Danza (rank 2, score 62.34, pos 2, SP 31.0)
- Market-aware swap in: #9 Arabian Prince (rank 6, score 61.56, pos 6, SP 5.5)
- Market-aware swap out: #5 Brave Danza (rank 2, score 62.34, pos 2, SP 31.0)

### 2025-11-04 Flemington Race 1-10 R5
- Baseline hits: 1; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #7 Fernao (rank 4, score 63.04, pos 11, SP 14.0)
- Market-free swap out: #10 Golden Century (rank 3, score 63.68, pos 9, SP 4.8)

### 2025-11-04 Flemington Race 1-10 R8
- Baseline hits: 0; market-free hits: 1; market-aware hits: 1
- Market-free swap in: #12 Tagline (rank 4, score 63.83, pos 2, SP 41.0)
- Market-free swap out: #3 Grand Prairie (rank 3, score 64.71, pos 9, SP 8.5)
- Market-aware swap in: #12 Tagline (rank 4, score 63.83, pos 2, SP 41.0)
- Market-aware swap out: #3 Grand Prairie (rank 3, score 64.71, pos 9, SP 8.5)

### 2025-11-04 Flemington Race 1-10 R10
- Baseline hits: 3; market-free hits: 2; market-aware hits: 3
- Market-free swap in: #14 He'll Rip (rank 4, score 63.58, pos 4, SP 10.0)
- Market-free swap out: #7 Sunshineinmypocket (rank 3, score 63.69, pos 2, SP 3.6)

