# AU Miss Signal Investigation

## Scope

- Historical races analysed: **336**
- 0-hit races: **46**
- 1-hit races: **162**
- Actual Top3 horses missed by model Top3 inside 0/1-hit races: **462**

## Where The Misses Sit

- Rank 4-5: **157** (34.0%)
- Rank 9+: **129** (27.9%)
- Rank 7-8: **110** (23.8%)
- Rank 6: **66** (14.3%)

Winner rank buckets inside 0/1-hit races:

- Rank 4-5: **47**
- Rank 7-8: **37**
- Rank 9+: **29**
- Rank 6: **22**

## Race Context

Condition:
- Good/Firm: **150**
- Soft: **43**
- Heavy: **15**

Class:
- BM58-70: **75**
- Other: **49**
- Group 2/3: **47**
- Group 1: **18**
- BM72-84: **9**
- Maiden: **8**
- BM88+: **2**

Field size:
- Field 9-12: **129**
- Field 13+: **62**
- Field <=8: **17**

## Most Reusable Spotting Signals

- 路程>=60: **342** (74.0%)
- SP<=15: **329** (71.2%)
- 距離 Top3 分差<=2: **295** (63.9%)
- 穩定分>=80: **263** (56.9%)
- 穩定性>=68: **256** (55.4%)
- rank4-6 視野內: **223** (48.3%)
- rank4-6近分+穩定: **175** (37.9%)
- 級磅>=62: **151** (32.7%)
- 騎練>=66: **139** (30.1%)
- 場地>=68: **117** (25.3%)
- Rating>=65: **81** (17.5%)
- 信心>=85: **80** (17.3%)
- 濕地場地可用: **46** (10.0%)
- 試閘>=70: **34** (7.4%)
- 賽績線>=66: **17** (3.7%)
- 穩定+賽績線+騎練/試閘: **6** (1.3%)
- 形勢>=62: **2** (0.4%)

## Missed Actual Top3 vs Failed Model Top3

Matrix delta, positive means actual Top3 missed horses were stronger than failed model picks:
- 級數與負重: **+0.00**
- 賽績線: **-0.64**
- 騎練訊號: **-0.78**
- 段速與引擎: **-0.90**
- 檔位形勢: **-1.06**
- 場地適性: **-2.70**
- 狀態與穩定性: **-5.68**

Feature delta:
- 負磅: **+0.28**
- 備戰: **+0.00**
- 級數: **-0.03**
- 試閘: **-0.04**
- 形勢: **-0.10**
- 騎師: **-0.21**
- 賽績線: **-0.59**
- Rating: **-0.66**
- 信心: **-0.71**
- 練馬師: **-0.79**

Failed model Top3 strongest average sections:
- 狀態與穩定性: **73.57**
- 場地適性: **66.32**
- 賽績線: **65.70**
- 騎練訊號: **65.36**
- 級數與負重: **61.52**
- 檔位形勢: **59.23**
- 段速與引擎: **48.06**

## Candidate Archetypes To Test

- A. Rank 4-6 + close score + stable: **178** (38.5%)
- B. Stable + formline + JT/trial: **6** (1.3%)
- C. Track fit on wet: **46** (10.0%)
- D. Rating/class near threshold: **35** (7.6%)
- E. SP live contender not in Top3: **329** (71.2%)

## Examples

### 2025-08-02 Flemington Race 1-9 R4 (1-hit)
- Context: Good/Firm / BM72-84 / Field 9-12
- Missed actual Top3:
  - #6 Call To Glory (rank 4, score 61.40, pos 2, 穩 68.1, 賽績 65.0, 騎練 64.7, 級磅 63.6, 場地 61.7, 試閘 60.0, 信心 82.0, SP 9.0)
  - #1 South Of India (rank 9, score 60.51, pos 3, 穩 67.3, 賽績 65.0, 騎練 60.8, 級磅 60.8, 場地 62.4, 試閘 60.0, 信心 83.0, SP 9.0)
- Failed model Top3:
  - #8 Smart Little Miss (rank 2, score 62.05, pos 9, 穩 69.3, 賽績 65.0, 騎練 64.9, 級磅 62.5, 場地 61.7, 試閘 60.0, 信心 85.0, SP 61.0)
  - #10 Commands Success (rank 3, score 61.52, pos 5, 穩 71.3, 賽績 65.0, 騎練 60.8, 級磅 63.2, 場地 61.7, 試閘 60.0, 信心 83.0, SP 101.0)

### 2025-08-02 Flemington Race 1-9 R5 (1-hit)
- Context: Good/Firm / BM72-84 / Field 9-12
- Missed actual Top3:
  - #8 Vega Magnifico (rank 7, score 60.78, pos 1, 穩 67.0, 賽績 65.0, 騎練 60.0, 級磅 60.8, 場地 62.4, 試閘 60.0, 信心 85.0, SP 21.0)
  - #14 Federer (rank 5, score 62.15, pos 2, 穩 70.2, 賽績 65.0, 騎練 65.9, 級磅 60.2, 場地 62.4, 試閘 60.0, 信心 83.0, SP 2.4)
- Failed model Top3:
  - #1 Aztec State (rank 1, score 63.82, pos 5, 穩 72.3, 賽績 65.0, 騎練 62.9, 級磅 58.4, 場地 69.8, 試閘 60.0, 信心 83.0, SP 3.9)
  - #9 Paradise Storm (rank 2, score 63.73, pos 10, 穩 76.0, 賽績 65.0, 騎練 63.3, 級磅 59.6, 場地 62.4, 試閘 60.0, 信心 85.0, SP 19.0)

### 2025-08-02 Flemington Race 1-9 R8 (1-hit)
- Context: Good/Firm / BM72-84 / Field 13+
- Missed actual Top3:
  - #15 Too Darn Discreet (rank 4, score 64.01, pos 1, 穩 72.3, 賽績 65.0, 騎練 64.9, 級磅 61.5, 場地 68.5, 試閘 60.0, 信心 82.0, SP 26.0)
  - #16 Farhh Flung (rank 11, score 62.60, pos 2, 穩 67.0, 賽績 65.0, 騎練 64.4, 級磅 62.0, 場地 69.8, 試閘 60.0, 信心 85.0, SP 7.0)
- Failed model Top3:
  - #11 One Long Day (rank 1, score 65.94, pos 10, 穩 76.0, 賽績 65.0, 騎練 67.3, 級磅 62.5, 場地 68.5, 試閘 60.0, 信心 81.0, SP 3.5)
  - #7 Whisky On The Hill (rank 3, score 64.20, pos 8, 穩 73.3, 賽績 65.0, 騎練 66.2, 級磅 62.1, 場地 66.5, 試閘 60.0, 信心 81.0, SP 31.0)

### 2025-08-23 Randwick Race 1-10 R2 (1-hit)
- Context: Heavy / Other / Field 13+
- Missed actual Top3:
  - #5 Neil (rank 4, score 63.50, pos 1, 穩 72.5, 賽績 65.0, 騎練 64.4, 級磅 61.2, 場地 62.4, 試閘 60.0, 信心 82.0, SP 11.0)
  - #9 Beer Baron (rank 7, score 62.49, pos 3, 穩 68.1, 賽績 65.0, 騎練 62.9, 級磅 63.2, 場地 66.5, 試閘 60.0, 信心 82.0, SP 20.0)
- Failed model Top3:
  - #2 Exit Fee (rank 1, score 64.73, pos 6, 穩 72.3, 賽績 65.0, 騎練 65.5, 級磅 61.9, 場地 69.8, 試閘 60.0, 信心 85.0, SP 3.7)
  - #4 Calido Magic (rank 3, score 63.79, pos 5, 穩 75.6, 賽績 65.0, 騎練 64.3, 級磅 63.6, 場地 62.4, 試閘 60.0, 信心 82.0, SP 26.0)

### 2025-08-23 Randwick Race 1-10 R3 (1-hit)
- Context: Heavy / BM58-70 / Field 9-12
- Missed actual Top3:
  - #9 Wuddzz (rank 6, score 63.41, pos 1, 穩 72.3, 賽績 65.0, 騎練 63.1, 級磅 60.6, 場地 66.5, 試閘 60.0, 信心 80.0, SP 10.0)
  - #4 Cormac T (rank 5, score 63.60, pos 2, 穩 75.6, 賽績 65.0, 騎練 61.9, 級磅 61.7, 場地 62.4, 試閘 60.0, 信心 85.0, SP 19.0)
- Failed model Top3:
  - #6 Piggyback (rank 1, score 65.05, pos 4, 穩 75.5, 賽績 65.0, 騎練 63.6, 級磅 60.8, 場地 69.8, 試閘 60.0, 信心 83.0, SP 5.0)
  - #1 Juja Kibo (rank 3, score 63.76, pos 6, 穩 76.0, 賽績 65.0, 騎練 63.8, 級磅 60.8, 場地 62.4, 試閘 60.0, 信心 82.0, SP 3.0)

### 2025-08-23 Randwick Race 1-10 R9 (1-hit)
- Context: Heavy / Group 2/3 / Field <=8
- Missed actual Top3:
  - #4 Lazzura (rank 4, score 63.57, pos 1, 穩 72.3, 賽績 65.0, 騎練 63.6, 級磅 61.7, 場地 69.8, 試閘 60.0, 信心 76.0, SP 6.0)
  - #7 With Your Blessing (rank 5, score 63.25, pos 2, 穩 71.3, 賽績 65.0, 騎練 63.8, 級磅 65.1, 場地 69.8, 試閘 60.0, 信心 80.0, SP 17.0)
- Failed model Top3:
  - #8 Romeo's Choice (rank 2, score 64.22, pos 5, 穩 75.5, 賽績 65.0, 騎練 63.6, 級磅 62.8, 場地 69.8, 試閘 60.0, 信心 85.0, SP 9.5)
  - #6 Corniche (rank 3, score 63.86, pos 6, 穩 70.2, 賽績 65.0, 騎練 68.5, 級磅 62.9, 場地 69.8, 試閘 60.0, 信心 85.0, SP 3.8)

### 2025-08-23 Randwick Race 1-10 R10 (1-hit)
- Context: Heavy / BM58-70 / Field 9-12
- Missed actual Top3:
  - #5 Glad You Think So (rank 5, score 63.12, pos 1, 穩 67.0, 賽績 65.0, 騎練 66.9, 級磅 61.2, 場地 69.8, 試閘 60.0, 信心 81.0, SP 3.0)
  - #11 Narbold (rank 4, score 63.14, pos 2, 穩 73.3, 賽績 65.0, 騎練 66.2, 級磅 62.7, 場地 62.4, 試閘 60.0, 信心 81.0, SP 4.2)
- Failed model Top3:
  - #3 Louisville (rank 2, score 63.91, pos 5, 穩 71.3, 賽績 65.0, 騎練 65.2, 級磅 59.7, 場地 69.8, 試閘 60.0, 信心 80.0, SP 31.0)
  - #8 Louie's Legacy (rank 3, score 63.49, pos 7, 穩 74.4, 賽績 65.0, 騎練 66.1, 級磅 60.9, 場地 61.7, 試閘 60.0, 信心 85.0, SP 21.0)

### 2025-09-06 Randwick Race 1-10 R2 (1-hit)
- Context: Good/Firm / Other / Field 13+
- Missed actual Top3:
  - #15 Zumbo (rank 6, score 70.92, pos 2, 穩 85.2, 賽績 65.5, 騎練 64.6, 級磅 63.5, 場地 62.4, 試閘 87.0, 信心 60.0, SP 7.0)
  - #2 Nimble Star (rank 7, score 70.25, pos 3, 穩 86.7, 賽績 64.5, 騎練 63.0, 級磅 63.3, 場地 62.4, 試閘 89.0, 信心 60.0, SP 17.0)
- Failed model Top3:
  - #14 Lightning Speed (rank 2, score 72.24, pos 16, 穩 89.4, 賽績 72.1, 騎練 61.0, 級磅 63.2, 場地 62.4, 試閘 76.0, 信心 60.0, SP 7.0)
  - #19 Graceful Ellen (rank 3, score 71.92, pos 13, 穩 85.0, 賽績 63.3, 騎練 62.7, 級磅 60.8, 場地 62.4, 試閘 76.0, 信心 60.0, SP 31.0)

### 2025-09-06 Randwick Race 1-10 R6 (1-hit)
- Context: Good/Firm / Group 2/3 / Field 13+
- Missed actual Top3:
  - #16 Apocalyptic (rank 5, score 67.79, pos 1, 穩 64.7, 賽績 59.9, 騎練 68.2, 級磅 59.9, 場地 66.5, 試閘 80.0, 信心 60.0, SP 5.0)
  - #2 Tupakara (rank 4, score 67.84, pos 2, 穩 70.4, 賽績 58.5, 騎練 68.1, 級磅 62.0, 場地 69.8, 試閘 78.0, 信心 60.0, SP 12.0)
- Failed model Top3:
  - #1 Within The Law (rank 1, score 74.03, pos 5, 穩 75.7, 賽績 89.1, 騎練 69.4, 級磅 62.9, 場地 69.8, 試閘 87.0, 信心 60.0, SP 4.2)
  - #4 Memo (rank 3, score 68.46, pos 9, 穩 64.6, 賽績 56.6, 騎練 70.4, 級磅 61.1, 場地 69.8, 試閘 87.0, 信心 60.0, SP 26.0)

### 2025-09-06 Randwick Race 1-10 R7 (1-hit)
- Context: Good/Firm / Group 2/3 / Field 9-12
- Missed actual Top3:
  - #4 Lindermann (rank 8, score 61.23, pos 1, 穩 50.0, 賽績 84.5, 騎練 70.4, 級磅 60.5, 場地 69.8, 試閘 87.0, 信心 60.0, SP 11.0)
  - #3 Vauban (rank 5, score 66.96, pos 3, 穩 62.7, 賽績 87.7, 騎練 65.9, 級磅 61.4, 場地 61.7, 試閘 80.0, 信心 60.0, SP 15.0)
- Failed model Top3:
  - #1 Arapaho (rank 1, score 71.10, pos 6, 穩 70.1, 賽績 90.3, 騎練 71.4, 級磅 65.6, 場地 69.8, 試閘 76.0, 信心 60.0, SP 12.0)
  - #2 Ceolwulf (rank 2, score 70.89, pos 4, 穩 65.2, 賽績 88.8, 騎練 67.9, 級磅 63.1, 場地 69.8, 試閘 87.0, 信心 60.0, SP 1.8)

### 2025-09-06 Randwick Race 1-10 R9 (0-hit)
- Context: Good/Firm / Group 2/3 / Field 13+
- Missed actual Top3:
  - #7 Pericles (rank 10, score 61.97, pos 1, 穩 53.7, 賽績 85.5, 騎練 66.0, 級磅 62.1, 場地 69.8, 試閘 87.0, 信心 60.0, SP 9.5)
  - #5 Private Eye (rank 4, score 69.25, pos 2, 穩 70.7, 賽績 59.8, 騎練 71.4, 級磅 66.2, 場地 69.8, 試閘 89.0, 信心 60.0, SP 2.1)
  - #14 With Your Blessing (rank 5, score 68.35, pos 3, 穩 73.6, 賽績 59.1, 騎練 67.8, 級磅 62.2, 場地 69.8, 試閘 89.0, 信心 60.0, SP 19.0)
- Failed model Top3:
  - #6 Kovalica (rank 1, score 70.98, pos 11, 穩 67.3, 賽績 88.2, 騎練 66.9, 級磅 64.5, 場地 69.8, 試閘 78.0, 信心 60.0, SP 61.0)
  - #17 Depth Of Character (rank 2, score 70.94, pos 12, 穩 78.2, 賽績 60.8, 騎練 65.3, 級磅 59.3, 場地 66.5, 試閘 69.0, 信心 60.0, SP 51.0)
  - #15 Swiftfalcon (rank 3, score 69.47, pos 6, 穩 70.0, 賽績 58.0, 騎練 67.9, 級磅 59.5, 場地 69.8, 試閘 87.0, 信心 60.0, SP 6.0)

### 2025-09-13 Flemington Race 1-10 R1 (1-hit)
- Context: Good/Firm / BM58-70 / Field 13+
- Missed actual Top3:
  - #8 Tonkin (rank 4, score 70.75, pos 2, 穩 82.0, 賽績 62.2, 騎練 68.1, 級磅 63.2, 場地 62.4, 試閘 87.0, 信心 60.0, SP 8.5)
  - #7 Stoli Bolli (rank 9, score 66.32, pos 3, 穩 65.1, 賽績 57.0, 騎練 65.8, 級磅 60.7, 場地 61.7, 試閘 89.0, 信心 60.0, SP 6.0)
- Failed model Top3:
  - #10 She's An Artist (rank 2, score 71.78, pos 4, 穩 75.7, 賽績 61.2, 騎練 69.7, 級磅 62.9, 場地 69.8, 試閘 89.0, 信心 60.0, SP 1.9)
  - #2 De Bergerac (rank 3, score 71.20, pos 5, 穩 73.2, 賽績 87.4, 騎練 62.0, 級磅 60.8, 場地 69.8, 試閘 78.0, 信心 60.0, SP 41.0)

### 2025-09-13 Flemington Race 1-10 R2 (1-hit)
- Context: Good/Firm / Other / Field <=8
- Missed actual Top3:
  - #3 Legacy Bound (rank 4, score 68.14, pos 1, 穩 76.2, 賽績 87.7, 騎練 66.9, 級磅 61.2, 場地 62.4, 試閘 87.0, 信心 60.0, SP 6.0)
  - #7 Navy Pilot (rank 7, score 64.39, pos 2, 穩 62.8, 賽績 57.3, 騎練 65.9, 級磅 60.3, 場地 62.4, 試閘 80.0, 信心 60.0, SP 26.0)
- Failed model Top3:
  - #4 Shining Smile (rank 1, score 70.59, pos 4, 穩 76.0, 賽績 77.5, 騎練 68.6, 級磅 61.3, 場地 69.8, 試閘 89.0, 信心 60.0, SP 13.0)
  - #5 Mcgaw (rank 3, score 68.72, pos 5, 穩 76.7, 賽績 61.2, 騎練 68.2, 級磅 62.6, 場地 62.4, 試閘 89.0, 信心 60.0, SP 4.2)

### 2025-09-13 Flemington Race 1-10 R3 (0-hit)
- Context: Good/Firm / Other / Field 9-12
- Missed actual Top3:
  - #1 Vinrock (rank 4, score 68.84, pos 1, 穩 72.3, 賽績 60.0, 騎練 68.3, 級磅 64.1, 場地 68.5, 試閘 87.0, 信心 60.0, SP 2.8)
  - #6 West Of Swindon (rank 7, score 67.05, pos 2, 穩 59.9, 賽績 86.4, 騎練 66.9, 級磅 62.5, 場地 62.4, 試閘 87.0, 信心 60.0, SP 8.5)
  - #8 Wise Inlaw (rank 9, score 64.85, pos 3, 穩 65.9, 賽績 59.2, 騎練 65.4, 級磅 61.3, 場地 62.4, 試閘 87.0, 信心 60.0, SP 6.5)
- Failed model Top3:
  - #3 Crossbow (rank 1, score 73.18, pos 9, 穩 77.0, 賽績 89.8, 騎練 67.2, 級磅 61.6, 場地 68.5, 試閘 87.0, 信心 60.0, SP 5.5)
  - #12 Just Kick (rank 2, score 70.35, pos 7, 穩 68.9, 賽績 88.0, 騎練 66.8, 級磅 62.1, 場地 66.5, 試閘 87.0, 信心 60.0, SP 10.0)
  - #4 Prestige Ole (rank 3, score 68.87, pos 5, 穩 73.7, 賽績 60.5, 騎練 63.1, 級磅 61.5, 場地 68.5, 試閘 87.0, 信心 60.0, SP 31.0)

### 2025-09-13 Flemington Race 1-10 R5 (0-hit)
- Context: Good/Firm / Maiden / Field 9-12
- Missed actual Top3:
  - #4 Cafe Millenium (rank 6, score 67.71, pos 1, 穩 63.6, 賽績 59.1, 騎練 65.6, 級磅 58.5, 場地 68.5, 試閘 88.0, 信心 60.0, SP 9.0)
  - #3 Transatlantic (rank 5, score 67.88, pos 2, 穩 67.5, 賽績 88.2, 騎練 67.8, 級磅 57.8, 場地 62.4, 試閘 79.0, 信心 60.0, SP 5.0)
  - #1 Rise At Dawn (rank 8, score 61.16, pos 3, 穩 56.1, 賽績 55.6, 騎練 67.0, 級磅 57.9, 場地 69.8, 試閘 93.0, 信心 60.0, SP 7.0)
- Failed model Top3:
  - #10 Athanatos (rank 1, score 70.95, pos 6, 穩 76.9, 賽績 60.3, 騎練 65.0, 級磅 60.1, 場地 69.8, 試閘 68.0, 信心 60.0, SP 7.5)
  - #12 Wonder Boy (rank 2, score 70.82, pos 9, 穩 69.5, 賽績 87.4, 騎練 63.3, 級磅 63.0, 場地 69.8, 試閘 92.0, 信心 60.0, SP 6.0)
  - #6 Pop Award (rank 3, score 69.22, pos 8, 穩 76.0, 賽績 60.0, 騎練 64.5, 級磅 63.6, 場地 62.4, 試閘 92.0, 信心 60.0, SP 10.0)

### 2025-09-13 Flemington Race 1-10 R6 (1-hit)
- Context: Good/Firm / Group 2/3 / Field 9-12
- Missed actual Top3:
  - #5 Star Patrol (rank 10, score 59.32, pos 2, 穩 49.3, 賽績 63.0, 騎練 67.5, 級磅 62.3, 場地 69.8, 試閘 89.0, 信心 60.0, SP 7.0)
  - #10 Media World (rank 4, score 66.61, pos 3, 穩 74.6, 賽績 60.1, 騎練 63.3, 級磅 62.0, 場地 61.7, 試閘 89.0, 信心 60.0, SP 8.0)
- Failed model Top3:
  - #9 Enxuto (rank 1, score 69.19, pos 7, 穩 71.4, 賽績 65.3, 騎練 63.5, 級磅 63.0, 場地 69.8, 試閘 78.0, 信心 60.0, SP 51.0)
  - #3 Steparty (rank 3, score 67.60, pos 8, 穩 70.8, 賽績 58.1, 騎練 63.3, 級磅 62.7, 場地 69.8, 試閘 80.0, 信心 60.0, SP 13.0)

### 2025-09-13 Flemington Race 1-10 R9 (0-hit)
- Context: Good/Firm / Group 2/3 / Field 13+
- Missed actual Top3:
  - #3 Lazzura (rank 4, score 69.74, pos 1, 穩 75.8, 賽績 68.7, 騎練 67.5, 級磅 63.1, 場地 62.4, 試閘 60.0, 信心 60.0, SP 2.0)
  - #10 Oh Too Good (rank 8, score 67.33, pos 2, 穩 67.9, 賽績 57.0, 騎練 68.4, 級磅 61.0, 場地 69.8, 試閘 89.0, 信心 60.0, SP 6.5)
  - #6 Abounding (rank 11, score 65.46, pos 3, 穩 58.5, 賽績 88.0, 騎練 62.4, 級磅 65.3, 場地 62.4, 試閘 60.0, 信心 60.0, SP 9.5)
- Failed model Top3:
  - #13 Bossy Benita (rank 1, score 70.98, pos 11, 穩 76.6, 賽績 91.3, 騎練 69.7, 級磅 59.9, 場地 61.7, 試閘 89.0, 信心 60.0, SP 21.0)
  - #7 On Display (rank 2, score 70.13, pos 10, 穩 75.9, 賽績 60.5, 騎練 68.4, 級磅 61.2, 場地 62.4, 試閘 87.0, 信心 60.0, SP 6.5)
  - #11 Splash Back (rank 3, score 69.98, pos 5, 穩 72.3, 賽績 59.6, 騎練 65.7, 級磅 61.4, 場地 68.5, 試閘 87.0, 信心 60.0, SP 13.0)

### 2025-09-21 Flemington Race 1-8 R1 (1-hit)
- Context: Good/Firm / BM58-70 / Field 9-12
- Missed actual Top3:
  - #7 Highland Bling (rank 8, score 60.22, pos 1, 穩 64.9, 賽績 65.0, 騎練 62.8, 級磅 60.3, 場地 61.7, 試閘 60.0, 信心 81.0, SP 16.0)
  - #4 Karburan (rank 10, score 58.57, pos 3, 穩 63.1, 賽績 65.0, 騎練 63.3, 級磅 59.9, 場地 55.1, 試閘 60.0, 信心 82.0, SP 4.4)
- Failed model Top3:
  - #9 Thurmond (rank 1, score 63.99, pos 6, 穩 76.0, 賽績 65.0, 騎練 63.9, 級磅 60.3, 場地 62.4, 試閘 60.0, 信心 82.0, SP 6.0)
  - #1 Navy King (rank 3, score 62.51, pos 7, 穩 69.3, 賽績 65.0, 騎練 61.5, 級磅 59.4, 場地 68.5, 試閘 60.0, 信心 82.0, SP 7.5)

### 2025-09-21 Flemington Race 1-8 R3 (1-hit)
- Context: Good/Firm / BM58-70 / Field <=8
- Missed actual Top3:
  - #5 Morrissette (rank 7, score 58.84, pos 2, 穩 72.0, 賽績 65.0, 騎練 61.9, 級磅 61.2, 場地 55.1, 試閘 60.0, 信心 85.0, SP 9.5)
  - #6 Brave Miss (rank 6, score 59.21, pos 3, 穩 69.0, 賽績 65.0, 騎練 65.0, 級磅 60.6, 場地 55.1, 試閘 60.0, 信心 77.0, SP 20.0)
- Failed model Top3:
  - #8 Lake Vostok (rank 1, score 62.71, pos 4, 穩 76.0, 賽績 65.0, 騎練 58.5, 級磅 60.5, 場地 69.8, 試閘 60.0, 信心 80.0, SP 8.5)
  - #10 Yachiyo (rank 3, score 61.39, pos 7, 穩 74.4, 賽績 65.0, 騎練 62.9, 級磅 62.8, 場地 62.4, 試閘 60.0, 信心 80.0, SP 3.0)

### 2025-09-21 Flemington Race 1-8 R4 (1-hit)
- Context: Good/Firm / BM58-70 / Field 13+
- Missed actual Top3:
  - #4 Gala Queen (rank 10, score 61.20, pos 1, 穩 65.0, 賽績 65.0, 騎練 67.7, 級磅 60.6, 場地 62.4, 試閘 60.0, 信心 82.0, SP 3.7)
  - #5 Nearing Liberty (rank 12, score 59.61, pos 2, 穩 66.9, 賽績 65.0, 騎練 63.1, 級磅 58.9, 場地 55.1, 試閘 60.0, 信心 85.0, SP 18.0)
- Failed model Top3:
  - #15 Heed The Omens (rank 1, score 65.12, pos 11, 穩 74.4, 賽績 65.0, 騎練 66.4, 級磅 60.0, 場地 66.5, 試閘 60.0, 信心 85.0, SP 8.0)
  - #9 Black Peppermint (rank 3, score 64.24, pos 6, 穩 74.4, 賽績 65.0, 騎練 69.3, 級磅 60.2, 場地 62.4, 試閘 60.0, 信心 81.0, SP 41.0)

### 2025-09-21 Flemington Race 1-8 R6 (1-hit)
- Context: Good/Firm / BM58-70 / Field 13+
- Missed actual Top3:
  - #15 Per Sempre (rank 4, score 64.14, pos 1, 穩 76.0, 賽績 65.0, 騎練 65.2, 級磅 60.1, 場地 61.7, 試閘 60.0, 信心 85.0, SP 21.0)
  - #13 Mckeyla (rank 7, score 63.57, pos 3, 穩 71.3, 賽績 65.0, 騎練 65.5, 級磅 61.0, 場地 66.5, 試閘 60.0, 信心 82.0, SP 8.5)
- Failed model Top3:
  - #9 Jennyanydots (rank 1, score 65.20, pos 4, 穩 76.0, 賽績 65.0, 騎練 70.2, 級磅 61.5, 場地 62.4, 試閘 60.0, 信心 85.0, SP 11.0)
  - #7 Prinzerro (rank 3, score 64.24, pos 12, 穩 71.3, 賽績 65.0, 騎練 63.8, 級磅 58.6, 場地 69.8, 試閘 60.0, 信心 81.0, SP 13.0)

### 2025-10-04 Flemington Race 1-10 R2 (1-hit)
- Context: Good/Firm / Other / Field 9-12
- Missed actual Top3:
  - #12 Streisand (rank 6, score 57.64, pos 2, 穩 57.0, 賽績 65.0, 騎練 63.3, 級磅 61.3, 場地 62.4, 試閘 58.0, 信心 75.0, SP 5.5)
  - #9 One Day At A Time (rank 7, score 57.55, pos 3, 穩 57.0, 賽績 65.0, 騎練 62.8, 級磅 61.3, 場地 62.4, 試閘 58.0, 信心 73.0, SP 4.0)
- Failed model Top3:
  - #4 Knightsbridge (rank 2, score 58.34, pos 5, 穩 57.0, 賽績 65.0, 騎練 67.6, 級磅 60.4, 場地 62.4, 試閘 58.0, 信心 77.0, SP 3.7)
  - #5 Knurl (rank 3, score 58.12, pos 4, 穩 57.0, 賽績 65.0, 騎練 67.0, 級磅 60.4, 場地 62.4, 試閘 58.0, 信心 77.0, SP 6.5)

### 2025-10-04 Flemington Race 1-10 R3 (1-hit)
- Context: Good/Firm / Other / Field 9-12
- Missed actual Top3:
  - #2 Miewa (rank 10, score 60.07, pos 2, 穩 65.0, 賽績 65.0, 騎練 62.8, 級磅 62.3, 場地 61.7, 試閘 60.0, 信心 85.0, SP 3.4)
  - #3 Officiate (rank 5, score 61.73, pos 3, 穩 67.0, 賽績 65.0, 騎練 68.5, 級磅 61.3, 場地 62.4, 試閘 60.0, 信心 85.0, SP 4.0)
- Failed model Top3:
  - #1 Arcora (rank 1, score 64.82, pos 11, 穩 73.3, 賽績 65.0, 騎練 65.8, 級磅 62.1, 場地 69.8, 試閘 60.0, 信心 82.0, SP 12.0)
  - #10 Super Paradise (rank 3, score 62.39, pos 10, 穩 70.4, 賽績 65.0, 騎練 65.8, 級磅 60.4, 場地 61.7, 試閘 60.0, 信心 81.0, SP 151.0)

### 2025-10-04 Flemington Race 1-10 R4 (1-hit)
- Context: Good/Firm / Group 2/3 / Field 9-12
- Missed actual Top3:
  - #10 Getta Good Feeling (rank 6, score 61.79, pos 1, 穩 71.3, 賽績 65.0, 騎練 63.3, 級磅 60.2, 場地 62.4, 試閘 60.0, 信心 82.0, SP 17.0)
  - #9 Mating Call (rank 8, score 60.32, pos 3, 穩 65.0, 賽績 65.0, 騎練 65.3, 級磅 60.5, 場地 62.4, 試閘 60.0, 信心 77.0, SP 10.0)
- Failed model Top3:
  - #2 Zany Girl (rank 2, score 63.41, pos 4, 穩 76.0, 賽績 65.0, 騎練 62.8, 級磅 61.0, 場地 62.4, 試閘 60.0, 信心 82.0, SP 8.5)
  - #6 Just Kick (rank 3, score 62.59, pos 9, 穩 71.3, 賽績 65.0, 騎練 63.3, 級磅 60.5, 場地 66.5, 試閘 60.0, 信心 79.0, SP 9.5)

### 2025-10-04 Flemington Race 1-10 R5 (1-hit)
- Context: Good/Firm / Group 2/3 / Field 9-12
- Missed actual Top3:
  - #10 Tuileries (rank 7, score 62.21, pos 2, 穩 70.2, 賽績 65.0, 騎練 65.9, 級磅 60.2, 場地 62.4, 試閘 60.0, 信心 82.0, SP 13.0)
  - #4 On Display (rank 6, score 62.98, pos 3, 穩 71.3, 賽績 65.0, 騎練 69.3, 級磅 60.3, 場地 61.7, 試閘 60.0, 信心 82.0, SP 2.4)
- Failed model Top3:
  - #7 Roll On High (rank 2, score 64.41, pos 7, 穩 72.3, 賽績 65.0, 騎練 66.0, 級磅 62.5, 場地 69.8, 試閘 60.0, 信心 85.0, SP 11.0)
  - #8 Terrestar (rank 3, score 63.72, pos 8, 穩 73.3, 賽績 65.0, 騎練 61.1, 級磅 59.8, 場地 69.8, 試閘 60.0, 信心 76.0, SP 51.0)

