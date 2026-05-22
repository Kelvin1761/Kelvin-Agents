# AU Auto Zero-Hit Race Audit

## Summary

- 0-hit races: **36**
- Good/Firm: **21**
- Soft: **9**
- Heavy: **6**
- BM58-70: **16**
- Field 9-12: **6**
- Field 13+: **3**
- 歷史賽果資料缺口: **31**

## Most Common Failure Tags

- 歷史賽果資料缺口: **31**
- 形勢與走位可能過信: **27**
- 騎練訊號可能過信: **26**
- 段速與引擎可能過信: **23**
- BM58-70 失手: **16**
- 頭馬其實仍在視野內: **9**
- Soft 場失手: **9**
- 場地適性低估: **6**
- 中型場失手: **6**
- Heavy 場失手: **6**
- 騎練訊號低估: **5**
- 頭馬完全跌出視野: **4**

## Most Common Underestimated Sections

- 場地適性低估: **6**
- 騎練訊號低估: **6**
- 級數與負重低估: **3**
- 段速與引擎低估: **3**
- 形勢與走位低估: **2**
- 狀態與穩定性低估: **1**
- 賽績線低估: **1**

## Race-By-Race Audit

### 2025-08-02 Flemington Race 1-9 Race 9

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`4-Y-O & Up, Mares, BM78, Handicap`) | 場數: **9** (`Field 9-12`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **場地適性低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / BM58-70 失手 / 中型場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 4.0 / 段速與引擎 -3.8 / 形勢與走位 -3.8**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -14.0 / 級數與負重 -13.0**

Model Top 3:
- [17] Eagle Express | model#1 | rank 78.17 | ability 73.82 | 實際第 5 | 強項 狀態與穩定性 76.7 | 弱項 場地適性 61.4
- [9] Illyivy | model#2 | rank 77.83 | ability 73.83 | 實際第 10 | 強項 狀態與穩定性 83.2 | 弱項 形勢與走位 60.2
- [5] Capricorn Star | model#3 | rank 77.61 | ability 73.06 | 實際第 8 | 強項 狀態與穩定性 80.1 | 弱項 場地適性 59.6

Actual Top 3:
- [14] Impending Shadow | 實際第 3 | model#6 | rank 66.56 | ability 65.03 | 強項 賽績線 70.3 | 弱項 級數與負重 56.1

### 2025-10-04 Randwick Race 1-10 Race 1

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM72, Handicap`) | 場數: **12** (`Field 9-12`)
- 頭馬: **Agita** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 -0.1 / 段速與引擎 -0.4 / 賽績線 -3.6**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -10.2 / 場地適性 -6.7**

Model Top 3:
- [6] Sunset Park | model#1 | rank 77.26 | ability 72.46 | 實際第 5 | 強項 狀態與穩定性 77.1 | 弱項 場地適性 59.1
- [5] Dr Evil | model#2 | rank 74.06 | ability 70.06 | 實際第 7 | 強項 狀態與穩定性 75.8 | 弱項 級數與負重 60.2
- [12] Magic Pharoah | model#3 | rank 71.82 | ability 69.15 | 實際第 4 | 強項 場地適性 74.4 | 弱項 級數與負重 57.8

Actual Top 3:
- [9] Agita | 實際第 1 | model#4 | rank 71.59 | ability 67.39 | 強項 賽績線 71.8 | 弱項 形勢與走位 58.9
- [1] Harlow Mist | 實際第 2 | model#11 | rank 64.23 | ability 61.29 | 強項 賽績線 66.1 | 弱項 狀態與穩定性 57.0
- [8] Highborn Harry | 實際第 3 | model#7 | rank 70.52 | ability 66.52 | 強項 賽績線 71.4 | 弱項 形勢與走位 58.2

### 2025-12-20 Randwick Race 1-10 Race 5

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3&4-Y-O, BM72, Handicap`) | 場數: **5** (`Field <=8`)
- 頭馬: **Willie Oppa** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **騎練訊號低估 / 頭馬其實仍在視野內 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 3.3 / 形勢與走位 -0.9 / 段速與引擎 -1.6**
- model top3 反而高估最多嘅 sections: **級數與負重 -10.1 / 狀態與穩定性 -9.4**

Model Top 3:
- [13] Tequisoda | model#1 | rank 77.05 | ability 72.70 | 實際第 9 | 強項 狀態與穩定性 83.3 | 弱項 場地適性 57.3
- [12] Dealt | model#2 | rank 73.19 | ability 69.19 | 實際第 6 | 強項 賽績線 72.7 | 弱項 形勢與走位 61.6
- [7] Hibiki Harmony | model#3 | rank 72.98 | ability 68.98 | 實際第 4 | 強項 狀態與穩定性 82.3 | 弱項 級數與負重 57.2

Actual Top 3:
- [10] Willie Oppa | 實際第 1 | model#5 | rank 67.04 | ability 63.04 | 強項 賽績線 69.8 | 弱項 級數與負重 55.6
- [9] Climb The Ladder | 實際第 2 | model#4 | rank 69.35 | ability 64.80 | 強項 賽績線 72.9 | 弱項 級數與負重 52.6

### 2025-12-31 Flemington Race 1-8 Race 7

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM66, Handicap`) | 場數: **8** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 1.6 / 場地適性 0.7 / 騎練訊號 0.2**
- model top3 反而高估最多嘅 sections: **級數與負重 -9.1 / 狀態與穩定性 -7.0**

Model Top 3:
- [19] Tan Tat Delight | model#1 | rank 74.38 | ability 70.38 | 實際第 11 | 強項 狀態與穩定性 78.1 | 弱項 場地適性 59.1
- [18] Flat Chat | model#2 | rank 73.79 | ability 70.14 | 實際第 9 | 強項 狀態與穩定性 80.5 | 弱項 形勢與走位 58.0
- [16] Jakivy | model#3 | rank 71.97 | ability 67.42 | 實際第 4 | 強項 賽績線 73.3 | 弱項 場地適性 56.9

Actual Top 3:
- [17] Majesticity | 實際第 2 | model#8 | rank 67.61 | ability 63.96 | 強項 賽績線 71.8 | 弱項 級數與負重 54.6

### 2025-12-31 Flemington Race 1-8 Race 8

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`BM70, Handicap`) | 場數: **5** (`Field <=8`)
- 頭馬: **Rue De Royale** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **場地適性低估 / 形勢與走位低估 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 9.8 / 形勢與走位 7.6 / 段速與引擎 1.5**
- model top3 反而高估最多嘅 sections: **級數與負重 -20.5 / 騎練訊號 -7.7**

Model Top 3:
- [8] Podargoni | model#1 | rank 74.18 | ability 70.53 | 實際第 9 | 強項 騎練訊號 73.8 | 弱項 形勢與走位 58.7
- [7] Barnage | model#2 | rank 73.10 | ability 69.65 | 實際第 13 | 強項 狀態與穩定性 77.6 | 弱項 形勢與走位 53.8
- [17] Palm Of Jumeirah | model#3 | rank 73.07 | ability 69.07 | 實際第 6 | 強項 賽績線 74.4 | 弱項 場地適性 56.9

Actual Top 3:
- [1] Rue De Royale | 實際第 1 | model#5 | rank 69.93 | ability 65.58 | 強項 賽績線 72.5 | 弱項 級數與負重 52.2

### 2026-01-10 Flemington Race 1-10 Race 6

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM70, Handicap`) | 場數: **8** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 -61.7 / 場地適性 -62.8 / 段速與引擎 -64.2**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -74.1 / 賽績線 -74.0**

Model Top 3:
- [14] Chergui | model#1 | rank 74.56 | ability 70.91 | 實際第 8 | 強項 賽績線 73.3 | 弱項 形勢與走位 60.4
- [13] Cavalry Girl | model#2 | rank 73.61 | ability 69.61 | 實際第 12 | 強項 狀態與穩定性 76.1 | 弱項 騎練訊號 61.0
- [7] Runlikenencryption | model#3 | rank 73.25 | ability 69.25 | 實際第 4 | 強項 賽績線 75.3 | 弱項 場地適性 58.1

Actual Top 3:

### 2026-01-10 Flemington Race 1-10 Race 9

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM74, Handicap`) | 場數: **6** (`Field <=8`)
- 頭馬: **Fission** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 -0.4 / 賽績線 -2.5 / 場地適性 -2.9**
- model top3 反而高估最多嘅 sections: **級數與負重 -9.0 / 騎練訊號 -6.4**

Model Top 3:
- [11] Tanganyika | model#1 | rank 74.17 | ability 69.62 | 實際第 12 | 強項 賽績線 73.3 | 弱項 場地適性 59.1
- [10] Behaviour | model#2 | rank 72.71 | ability 68.71 | 實際第 5 | 強項 騎練訊號 74.8 | 弱項 場地適性 57.3
- [12] Mercurial Lady | model#3 | rank 72.40 | ability 68.40 | 實際第 7 | 強項 狀態與穩定性 74.0 | 弱項 場地適性 56.9

Actual Top 3:
- [5] Fission | 實際第 1 | model#5 | rank 66.42 | ability 62.42 | 強項 賽績線 70.7 | 弱項 場地適性 54.8

### 2026-01-10 Flemington Race 1-10 Race 10

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM74, Handicap`) | 場數: **7** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 -0.3 / 騎練訊號 -2.9 / 形勢與走位 -3.5**
- model top3 反而高估最多嘅 sections: **級數與負重 -19.5 / 狀態與穩定性 -14.3**

Model Top 3:
- [14] Legacy Bay | model#1 | rank 79.67 | ability 75.67 | 實際第 5 | 強項 狀態與穩定性 83.2 | 弱項 形勢與走位 60.5
- [13] Hot Digity Boom | model#2 | rank 76.51 | ability 72.16 | 實際第 4 | 強項 狀態與穩定性 77.1 | 弱項 騎練訊號 64.5
- [12] Yam | model#3 | rank 75.26 | ability 71.26 | 實際第 10 | 強項 狀態與穩定性 78.2 | 弱項 形勢與走位 58.0

Actual Top 3:
- [11] Paradise City | 實際第 2 | model#6 | rank 66.49 | ability 62.49 | 強項 賽績線 70.3 | 弱項 場地適性 53.2

### 2026-01-24 Randwick Race 1-10 Race 6

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, C,G&E, BM78, Handicap`) | 場數: **4** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 -60.3 / 狀態與穩定性 -60.4 / 段速與引擎 -62.5**
- model top3 反而高估最多嘅 sections: **騎練訊號 -68.7 / 賽績線 -68.5**

Model Top 3:
- [7] Shall Be | model#1 | rank 69.04 | ability 64.49 | 實際第 9 | 強項 騎練訊號 73.5 | 弱項 場地適性 55.2
- [13] King Of Dragons | model#2 | rank 67.43 | ability 63.43 | 實際第 6 | 強項 賽績線 70.3 | 弱項 級數與負重 51.1
- [9] Unstopabull | model#3 | rank 64.42 | ability 62.69 | 實際第 7 | 強項 級數與負重 68.6 | 弱項 狀態與穩定性 57.5

Actual Top 3:

### 2026-02-14 Randwick Race 1-10 Race 5

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM88, Handicap`) | 場數: **4** (`Field <=8`)
- 頭馬: **Jamberoo** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 0.7 / 騎練訊號 -0.4 / 賽績線 -3.1**
- model top3 反而高估最多嘅 sections: **場地適性 -9.0 / 狀態與穩定性 -7.6**

Model Top 3:
- [12] Casual Connection | model#1 | rank 74.11 | ability 69.91 | 實際第 8 | 強項 狀態與穩定性 77.8 | 弱項 級數與負重 59.7
- [9] It's A Knockout | model#2 | rank 72.98 | ability 68.38 | 實際第 7 | 強項 騎練訊號 77.7 | 弱項 級數與負重 50.3
- [11] Glad You Think So | model#3 | rank 72.53 | ability 67.98 | 實際第 4 | 強項 賽績線 72.2 | 弱項 騎練訊號 59.0

Actual Top 3:
- [15] Jamberoo | 實際第 1 | model#4 | rank 67.46 | ability 63.46 | 強項 賽績線 70.3 | 弱項 級數與負重 53.1

### 2026-04-25 Randwick Race 1-8 Race 8

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM78, Handicap`) | 場數: **13** (`Field 13+`)
- 頭馬: **Nobler** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **場地適性低估 / 段速與引擎低估 / 騎練訊號可能過信 / 頭馬完全跌出視野 / BM58-70 失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 2.4 / 段速與引擎 2.3 / 狀態與穩定性 0.1**
- model top3 反而高估最多嘅 sections: **級數與負重 -8.1 / 騎練訊號 -7.5**

Model Top 3:
- [15] Black Babylon | model#1 | rank 73.88 | ability 68.93 | 實際第 9 | 強項 賽績線 88.8 | 弱項 級數與負重 54.8
- [13] Crossbow | model#2 | rank 72.27 | ability 67.82 | 實際第 5 | 強項 騎練訊號 77.0 | 弱項 形勢與走位 56.8
- [2] Luskaire | model#3 | rank 71.69 | ability 67.69 | 實際第 13 | 強項 騎練訊號 72.3 | 弱項 段速與引擎 61.6

Actual Top 3:
- [19] Nobler | 實際第 1 | model#8 | rank 70.13 | ability 65.58 | 強項 賽績線 76.8 | 弱項 級數與負重 50.5
- [4] Bella Montagna | 實際第 2 | model#4 | rank 71.62 | ability 67.22 | 強項 段速與引擎 69.2 | 弱項 形勢與走位 56.8
- [1] Uzziah | 實際第 3 | model#12 | rank 66.99 | ability 63.34 | 強項 場地適性 72.6 | 弱項 級數與負重 42.3

### 2025-08-02 Flemington Race 1-9 Race 8

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM72-84** (`BM84, Handicap`) | 場數: **10** (`Field 9-12`)
- 頭馬: **Too Darn Discreet** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **場地適性低估 / 騎練訊號低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 頭馬其實仍在視野內 / 中型場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 4.6 / 騎練訊號 2.5 / 段速與引擎 -3.0**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -18.4 / 賽績線 -8.4**

Model Top 3:
- [11] One Long Day | model#1 | rank 82.65 | ability 78.30 | 實際第 10 | 強項 狀態與穩定性 86.2 | 弱項 段速與引擎 68.3
- [10] Black Storm | model#2 | rank 75.34 | ability 71.69 | 實際第 7 | 強項 狀態與穩定性 83.3 | 弱項 形勢與走位 58.0
- [5] Outta Compton | model#3 | rank 74.42 | ability 70.07 | 實際第 12 | 強項 狀態與穩定性 79.4 | 弱項 級數與負重 58.1

Actual Top 3:
- [15] Too Darn Discreet | 實際第 1 | model#5 | rank 71.87 | ability 67.87 | 強項 騎練訊號 72.5 | 弱項 級數與負重 59.5
- [16] Farhh Flung | 實際第 2 | model#8 | rank 68.06 | ability 66.94 | 強項 賽績線 69.2 | 弱項 狀態與穩定性 63.5

### 2025-12-31 Flemington Race 1-8 Race 1

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`No Metro Wins, Handicap`) | 場數: **11** (`Field 9-12`)
- 頭馬: **Somewhere** | model 排名: **9** | 頭馬完全跌出前6
- 初步失誤標籤: **級數與負重低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬完全跌出視野 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 3.9 / 場地適性 0.2 / 騎練訊號 -2.4**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -9.0 / 賽績線 -4.6**

Model Top 3:
- [12] Vivacissimo | model#1 | rank 74.58 | ability 70.58 | 實際第 4 | 強項 狀態與穩定性 80.7 | 弱項 場地適性 56.9
- [13] Thunder Hawk | model#2 | rank 74.17 | ability 69.62 | 實際第 9 | 強項 狀態與穩定性 75.0 | 弱項 場地適性 59.1
- [5] Leg Drive | model#3 | rank 72.57 | ability 68.22 | 實際第 10 | 強項 賽績線 75.8 | 弱項 場地適性 53.6

Actual Top 3:
- [3] Somewhere | 實際第 1 | model#9 | rank 68.12 | ability 64.12 | 強項 賽績線 70.7 | 弱項 場地適性 54.0
- [9] His Finest Hour | 實際第 2 | model#7 | rank 69.90 | ability 65.90 | 強項 級數與負重 73.8 | 弱項 形勢與走位 55.2
- [6] Make It Sweet | 實際第 3 | model#8 | rank 68.54 | ability 63.99 | 強項 賽績線 70.3 | 弱項 級數與負重 54.6

### 2025-11-01 Flemington Race 1-9 Race 2

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 2/3** (`Group 3, 3-Y-O, Fillies, SW + P`) | 場數: **5** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **騎練訊號低估 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 4.4 / 段速與引擎 1.4 / 形勢與走位 0.9**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -14.6 / 賽績線 -6.7**

Model Top 3:
- [12] Miss Revealing | model#1 | rank 74.57 | ability 70.57 | 實際第 5 | 強項 賽績線 74.9 | 弱項 形勢與走位 57.3
- [10] Gisella | model#2 | rank 73.89 | ability 69.54 | 實際第 10 | 強項 狀態與穩定性 77.8 | 弱項 場地適性 57.3
- [13] M'lady Rose | model#3 | rank 71.84 | ability 67.84 | 實際第 8 | 強項 賽績線 71.3 | 弱項 形勢與走位 60.1

Actual Top 3:
- [1] Icarian Dream | 實際第 3 | model#5 | rank 69.15 | ability 65.15 | 強項 騎練訊號 69.9 | 弱項 狀態與穩定性 59.3

### 2025-11-01 Flemington Race 1-9 Race 3

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 2/3** (`Group 3, Handicap, Maidens Ineligible`) | 場數: **5** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 -61.1 / 級數與負重 -61.9 / 形勢與走位 -62.5**
- model top3 反而高估最多嘅 sections: **賽績線 -72.6 / 狀態與穩定性 -72.4**

Model Top 3:
- [10] Hedged | model#1 | rank 77.38 | ability 73.38 | 實際第 6 | 強項 狀態與穩定性 76.9 | 弱項 場地適性 59.7
- [11] Disneck | model#2 | rank 70.60 | ability 66.05 | 實際第 5 | 強項 狀態與穩定性 72.9 | 弱項 級數與負重 50.5
- [13] Royal Insignia | model#3 | rank 70.09 | ability 65.74 | 實際第 8 | 強項 賽績線 70.7 | 弱項 場地適性 57.2

Actual Top 3:

### 2026-01-10 Flemington Race 1-10 Race 3

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`3-Y-O, Fillies, Handicap`) | 場數: **6** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 -59.4 / 形勢與走位 -61.3 / 段速與引擎 -65.9**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -76.0 / 賽績線 -75.2**

Model Top 3:
- [7] Breakfast | model#1 | rank 75.56 | ability 71.56 | 實際第 11 | 強項 賽績線 75.8 | 弱項 場地適性 57.3
- [11] Seven Oceans | model#2 | rank 74.42 | ability 70.07 | 實際第 8 | 強項 狀態與穩定性 76.8 | 弱項 騎練訊號 61.0
- [12] Rosangela | model#3 | rank 73.60 | ability 69.60 | 實際第 5 | 強項 狀態與穩定性 76.5 | 弱項 場地適性 59.6

Actual Top 3:

### 2026-01-10 Flemington Race 1-10 Race 8

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 2/3** (`Group 3, Handicap, Maidens Ineligible`) | 場數: **5** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 -0.6 / 段速與引擎 -2.1 / 形勢與走位 -4.4**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -18.6 / 場地適性 -8.2**

Model Top 3:
- [5] Hedged | model#1 | rank 74.99 | ability 70.79 | 實際第 10 | 強項 級數與負重 73.2 | 弱項 形勢與走位 65.3
- [9] Major Share | model#2 | rank 74.66 | ability 70.66 | 實際第 7 | 強項 狀態與穩定性 76.2 | 弱項 級數與負重 58.4
- [12] Celsius Star | model#3 | rank 72.10 | ability 68.10 | 實際第 8 | 強項 狀態與穩定性 79.6 | 弱項 場地適性 54.8

Actual Top 3:
- [10] Extratwo | 實際第 2 | model#4 | rank 68.60 | ability 64.60 | 強項 騎練訊號 69.9 | 弱項 場地適性 56.6
- [11] Contemporary | 實際第 3 | model#5 | rank 60.94 | ability 59.62 | 強項 賽績線 66.1 | 弱項 級數與負重 53.1

### 2026-01-24 Randwick Race 1-10 Race 3

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`3-Y-O & Up, Class 3, Handicap`) | 場數: **6** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **段速與引擎可能過信 / 騎練訊號可能過信 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 1.6 / 狀態與穩定性 -1.3 / 賽績線 -1.6**
- model top3 反而高估最多嘅 sections: **騎練訊號 -9.3 / 段速與引擎 -4.3**

Model Top 3:
- [13] Nova Centauri | model#1 | rank 79.09 | ability 75.04 | 實際第 12 | 強項 狀態與穩定性 85.7 | 弱項 級數與負重 63.5
- [12] Navy Steel | model#2 | rank 76.63 | ability 72.63 | 實際第 7 | 強項 狀態與穩定性 76.9 | 弱項 形勢與走位 59.6
- [15] Micro Mikki | model#3 | rank 75.34 | ability 71.14 | 實際第 6 | 強項 狀態與穩定性 78.1 | 弱項 級數與負重 60.7

Actual Top 3:
- [7] Satin Stiletto | 實際第 2 | model#4 | rank 73.54 | ability 69.89 | 強項 狀態與穩定性 79.0 | 弱項 形勢與走位 59.8

### 2026-02-14 Randwick Race 1-10 Race 4

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM72-84** (`BM78, Handicap`) | 場數: **4** (`Field <=8`)
- 頭馬: **Amreekiyah** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **頭馬其實仍在視野內 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 1.9 / 形勢與走位 0.3 / 段速與引擎 -1.0**
- model top3 反而高估最多嘅 sections: **級數與負重 -12.8 / 狀態與穩定性 -10.7**

Model Top 3:
- [11] Miss Kim Kar | model#1 | rank 75.13 | ability 70.78 | 實際第 6 | 強項 級數與負重 74.4 | 弱項 形勢與走位 65.3
- [15] Arabian Rose | model#2 | rank 72.98 | ability 69.18 | 實際第 4 | 強項 狀態與穩定性 75.6 | 弱項 形勢與走位 58.0
- [9] One Step Closer | model#3 | rank 67.94 | ability 63.94 | 實際第 10 | 強項 賽績線 71.4 | 弱項 級數與負重 53.6

Actual Top 3:
- [17] Amreekiyah | 實際第 1 | model#4 | rank 65.36 | ability 61.36 | 強項 騎練訊號 69.9 | 弱項 級數與負重 50.5

### 2026-02-28 Flemington Race 1-10 Race 9

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`3-Y-O, SW + P, Inglis horses only`) | 場數: **7** (`Field <=8`)
- 頭馬: **Getta Good Feeling** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **場地適性低估 / 騎練訊號低估 / 形勢與走位低估 / 頭馬其實仍在視野內 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 3.7 / 騎練訊號 2.5 / 形勢與走位 2.4**
- model top3 反而高估最多嘅 sections: **級數與負重 -16.8 / 狀態與穩定性 -3.3**

Model Top 3:
- [12] Toronado Queen | model#1 | rank 77.24 | ability 72.69 | 實際第 12 | 強項 狀態與穩定性 78.5 | 弱項 場地適性 59.1
- [15] Layla | model#2 | rank 74.14 | ability 70.14 | 實際第 14 | 強項 賽績線 74.9 | 弱項 形勢與走位 59.3
- [10] Rohesia | model#3 | rank 73.11 | ability 69.46 | 實際第 9 | 強項 狀態與穩定性 77.6 | 弱項 形勢與走位 54.8

Actual Top 3:
- [2] Getta Good Feeling | 實際第 1 | model#4 | rank 72.67 | ability 68.12 | 強項 狀態與穩定性 75.1 | 弱項 級數與負重 51.4
- [13] Fundamental Nature | 實際第 3 | model#5 | rank 72.00 | ability 68.35 | 強項 賽績線 73.3 | 弱項 形勢與走位 58.0

### 2026-04-11 Randwick Race 1-10 Race 4

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`Set Weights`) | 場數: **4** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 -61.3 / 級數與負重 -62.4 / 段速與引擎 -66.3**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -76.2 / 賽績線 -74.7**

Model Top 3:
- [15] Oakfield Saturn | model#1 | rank 76.17 | ability 72.52 | 實際第 14 | 強項 狀態與穩定性 82.7 | 弱項 形勢與走位 56.8
- [4] Mogul Monarch | model#2 | rank 75.76 | ability 71.21 | 實際第 12 | 強項 場地適性 73.7 | 弱項 級數與負重 61.3
- [14] Harry's Bar | model#3 | rank 74.86 | ability 70.86 | 實際第 5 | 強項 狀態與穩定性 75.8 | 弱項 形勢與走位 58.2

Actual Top 3:

### 2025-08-09 Randwick Race 1-10 Race 1

- 條件: **Heavy** (`Heavy 10`) | 班次: **BM58-70** (`3yo+, BM72, Handicap`) | 場數: **15** (`Field 13+`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / BM58-70 失手 / 大場面失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 -59.1 / 形勢與走位 -59.4 / 段速與引擎 -64.4**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -80.6 / 賽績線 -77.1**

Model Top 3:
- [3] Mal Coupe | model#1 | rank 76.28 | ability 72.28 | 實際第 8 | 強項 狀態與穩定性 82.6 | 弱項 場地適性 59.1
- [2] Desi Emperor | model#2 | rank 74.62 | ability 70.97 | 實際第 8 | 強項 狀態與穩定性 82.6 | 弱項 形勢與走位 58.0
- [13] Stratafy | model#3 | rank 74.22 | ability 70.57 | 實際第 8 | 強項 狀態與穩定性 76.5 | 弱項 場地適性 59.1

Actual Top 3:

### 2025-11-08 Flemington Race 1-9 Race 9

- 條件: **Soft** (`Soft 6`) | 班次: **BM58-70** (`3-Y-O & Up, BM80, Handicap`) | 場數: **4** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Soft 場失手 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 -60.3 / 場地適性 -63.3 / 級數與負重 -64.9**
- model top3 反而高估最多嘅 sections: **賽績線 -72.2 / 狀態與穩定性 -69.8**

Model Top 3:
- [16] Actuality | model#1 | rank 75.73 | ability 71.73 | 實際第 8 | 強項 狀態與穩定性 77.2 | 弱項 形勢與走位 64.0
- [14] Latin Lover | model#2 | rank 70.61 | ability 66.61 | 實際第 10 | 強項 賽績線 69.6 | 弱項 形勢與走位 58.1
- [18] Riche D'amour | model#3 | rank 69.78 | ability 67.09 | 實際第 6 | 強項 賽績線 72.2 | 弱項 形勢與走位 58.7

Actual Top 3:

### 2025-12-13 Randwick Race 1-10 Race 4

- 條件: **Soft** (`Soft 5`) | 班次: **BM58-70** (`3-Y-O & Up, BM78, Handicap`) | 場數: **6** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Soft 場失手 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 -56.5 / 形勢與走位 -59.6 / 級數與負重 -59.8**
- model top3 反而高估最多嘅 sections: **賽績線 -73.2 / 狀態與穩定性 -72.0**

Model Top 3:
- [10] Miss Kim Kar | model#1 | rank 73.91 | ability 69.66 | 實際第 8 | 強項 騎練訊號 77.2 | 弱項 級數與負重 59.2
- [11] Smashing Time | model#2 | rank 70.94 | ability 66.94 | 實際第 7 | 強項 賽績線 72.2 | 弱項 場地適性 56.6
- [14] Laurel Hill | model#3 | rank 70.91 | ability 66.56 | 實際第 9 | 強項 狀態與穩定性 75.0 | 弱項 場地適性 53.2

Actual Top 3:

### 2026-01-03 Randwick Race 1-10 Race 9

- 條件: **Soft** (`Soft 5`) | 班次: **BM58-70** (`3-Y-O & Up, BM78, Handicap`) | 場數: **4** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / Soft 場失手 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 0.9 / 賽績線 -3.3 / 形勢與走位 -5.3**
- model top3 反而高估最多嘅 sections: **場地適性 -8.7 / 狀態與穩定性 -7.5**

Model Top 3:
- [12] Exit Fee | model#1 | rank 67.76 | ability 63.96 | 實際第 5 | 強項 賽績線 69.2 | 弱項 級數與負重 53.8
- [9] Massira | model#2 | rank 67.50 | ability 66.80 | 實際第 8 | 強項 賽績線 70.7 | 弱項 騎練訊號 59.0
- [14] Manwari | model#3 | rank 66.40 | ability 63.02 | 實際第 9 | 強項 賽績線 72.9 | 弱項 級數與負重 51.1

Actual Top 3:
- [13] King Taurus | 實際第 2 | model#4 | rank 56.45 | ability 58.75 | 強項 賽績線 67.6 | 弱項 級數與負重 51.1

### 2026-02-28 Randwick Race 1-10 Race 1

- 條件: **Soft** (`Soft 6`) | 班次: **BM58-70** (`3-Y-O & Up, BM72, Handicap`) | 場數: **13** (`Field 13+`)
- 頭馬: **Bryant** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬完全跌出視野 / Soft 場失手 / BM58-70 失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 0.0 / 場地適性 -0.9 / 級數與負重 -1.1**
- model top3 反而高估最多嘅 sections: **騎練訊號 -5.5 / 形勢與走位 -3.4**

Model Top 3:
- [5] Flightcrew | model#1 | rank 74.59 | ability 70.04 | 實際第 6 | 強項 狀態與穩定性 75.9 | 弱項 場地適性 57.3
- [3] Zoutastic | model#2 | rank 73.78 | ability 69.58 | 實際第 10 | 強項 狀態與穩定性 73.6 | 弱項 場地適性 59.9
- [11] The New Sinatra | model#3 | rank 73.43 | ability 69.23 | 實際第 12 | 強項 騎練訊號 72.7 | 弱項 形勢與走位 58.0

Actual Top 3:
- [10] Bryant | 實際第 1 | model#7 | rank 71.03 | ability 67.38 | 強項 狀態與穩定性 76.0 | 弱項 形勢與走位 55.9
- [2] Shaggy | 實際第 2 | model#5 | rank 72.82 | ability 68.62 | 強項 賽績線 72.2 | 弱項 形勢與走位 61.6
- [1] Los Padres | 實際第 3 | model#13 | rank 62.96 | ability 62.07 | 強項 賽績線 70.7 | 弱項 場地適性 53.4

### 2025-11-01 Randwick Race 1-10 Race 2

- 條件: **Soft** (`Soft 7`) | 班次: **Other** (`3-Y-O & Up, Class 3, Handicap`) | 場數: **9** (`Field 9-12`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Soft 場失手 / 中型場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 -58.1 / 場地適性 -58.2 / 段速與引擎 -63.6**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -77.1 / 賽績線 -75.5**

Model Top 3:
- [10] Lightning Speed | model#1 | rank 74.42 | ability 70.42 | 實際第 15 | 強項 賽績線 75.3 | 弱項 形勢與走位 56.1
- [9] Manwari | model#2 | rank 74.25 | ability 70.25 | 實際第 13 | 強項 狀態與穩定性 80.1 | 弱項 場地適性 59.1
- [15] Fan Harder | model#3 | rank 73.16 | ability 69.16 | 實際第 7 | 強項 狀態與穩定性 76.1 | 弱項 形勢與走位 58.7

Actual Top 3:

### 2025-11-04 Flemington Race 1-10 Race 7

- 條件: **Soft** (`Soft 6`) | 班次: **Group 1** (`Group 1, 3-Y-O & Up, Handicap`) | 場數: **12** (`Field 9-12`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **賽績線低估 / 狀態與穩定性低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Soft 場失手 / 中型場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **狀態與穩定性 3.9 / 賽績線 2.2 / 段速與引擎 -2.4**
- model top3 反而高估最多嘅 sections: **騎練訊號 -10.1 / 形勢與走位 -9.6**

Model Top 3:
- [18] Parchment Party | model#1 | rank 77.49 | ability 73.14 | 實際第 20 | 強項 狀態與穩定性 83.2 | 弱項 段速與引擎 60.6
- [24] Valiant King | model#2 | rank 75.12 | ability 71.32 | 實際第 16 | 強項 狀態與穩定性 75.5 | 弱項 級數與負重 59.8
- [13] Changingoftheguard | model#3 | rank 72.43 | ability 68.78 | 實際第 9 | 強項 賽績線 72.7 | 弱項 形勢與走位 58.3

Actual Top 3:
- [20] Goodie Two Shoes | 實際第 2 | model#6 | rank 70.03 | ability 66.38 | 強項 狀態與穩定性 80.4 | 弱項 形勢與走位 52.4

### 2025-08-09 Randwick Race 1-10 Race 9

- 條件: **Heavy** (`Heavy 10`) | 班次: **Other** (`3yo+, open, Handicap`) | 場數: **5** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 -60.9 / 段速與引擎 -61.9 / 級數與負重 -63.0**
- model top3 反而高估最多嘅 sections: **賽績線 -71.6 / 狀態與穩定性 -69.1**

Model Top 3:
- [16] Saltcoats | model#1 | rank 77.92 | ability 73.37 | 實際第 8 | 強項 狀態與穩定性 77.9 | 弱項 級數與負重 65.0
- [20] Nellie Leylax | model#2 | rank 68.83 | ability 66.51 | 實際第 8 | 強項 賽績線 71.8 | 弱項 形勢與走位 58.3
- [19] Age Of Kings | model#3 | rank 65.42 | ability 63.56 | 實際第 8 | 強項 賽績線 67.2 | 弱項 形勢與走位 56.6

Actual Top 3:

### 2025-11-04 Randwick Race 1-10 Race 6

- 條件: **Heavy** (`Heavy 8`) | 班次: **Other** (`3-Y-O & Up, Handicap`) | 場數: **7** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **騎練訊號低估 / 段速與引擎低估 / 形勢與走位可能過信 / Heavy 場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 4.2 / 段速與引擎 2.5 / 狀態與穩定性 -1.6**
- model top3 反而高估最多嘅 sections: **形勢與走位 -9.8 / 級數與負重 -4.6**

Model Top 3:
- [2] Mogo Magic | model#1 | rank 77.88 | ability 73.33 | 實際第 10 | 強項 狀態與穩定性 85.0 | 弱項 段速與引擎 63.4
- [1] Gallant Star | model#2 | rank 75.39 | ability 71.04 | 實際第 4 | 強項 狀態與穩定性 77.3 | 弱項 級數與負重 56.5
- [10] Chidiac | model#3 | rank 75.14 | ability 70.79 | 實際第 5 | 強項 狀態與穩定性 75.2 | 弱項 級數與負重 59.1

Actual Top 3:
- [5] Lisztomania | 實際第 2 | model#5 | rank 72.28 | ability 68.28 | 強項 狀態與穩定性 77.6 | 弱項 級數與負重 55.6

### 2025-11-04 Flemington Race 1-10 Race 9

- 條件: **Soft** (`Soft 6`) | 班次: **Group 2/3** (`Group 3, 4-Y-O & Up, Mares, SW + P`) | 場數: **6** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **場地適性低估 / 級數與負重低估 / 形勢與走位低估 / 段速與引擎可能過信 / 騎練訊號可能過信 / Soft 場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 5.7 / 形勢與走位 4.1 / 場地適性 3.1**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -6.9 / 段速與引擎 -5.4**

Model Top 3:
- [19] Perfect Picture | model#1 | rank 74.98 | ability 70.63 | 實際第 9 | 強項 狀態與穩定性 76.2 | 弱項 場地適性 61.0
- [18] Kirribilli | model#2 | rank 74.06 | ability 70.06 | 實際第 12 | 強項 賽績線 73.3 | 弱項 形勢與走位 59.5
- [15] Surfin' Bird | model#3 | rank 73.44 | ability 69.44 | 實際第 5 | 強項 賽績線 74.9 | 弱項 場地適性 57.3

Actual Top 3:
- [16] Jenni The Fox | 實際第 3 | model#4 | rank 71.20 | ability 67.20 | 強項 級數與負重 69.6 | 弱項 段速與引擎 62.1

### 2025-11-04 Flemington Race 1-10 Race 10

- 條件: **Soft** (`Soft 6`) | 班次: **BM88+** (`BM90, Handicap`) | 場數: **4** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Soft 場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 -56.6 / 形勢與走位 -58.8 / 場地適性 -60.1**
- model top3 反而高估最多嘅 sections: **賽績線 -70.6 / 狀態與穩定性 -65.7**

Model Top 3:
- [15] Nostringsattached | model#1 | rank 69.99 | ability 65.99 | 實際第 9 | 強項 賽績線 69.2 | 弱項 形勢與走位 59.0
- [20] Jugiong | model#2 | rank 67.26 | ability 63.81 | 實際第 6 | 強項 賽績線 72.2 | 弱項 形勢與走位 55.9
- [19] Boltsaver | model#3 | rank 62.66 | ability 61.71 | 實際第 7 | 強項 賽績線 70.3 | 弱項 級數與負重 50.5

Actual Top 3:

### 2026-02-28 Randwick Race 1-10 Race 2

- 條件: **Soft** (`Soft 6`) | 班次: **Other** (`3-Y-O & Up, Class 3, Handicap`) | 場數: **6** (`Field <=8`)
- 頭馬: **Brave Xena** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / Soft 場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 0.3 / 賽績線 -1.9 / 場地適性 -1.9**
- model top3 反而高估最多嘅 sections: **級數與負重 -6.2 / 狀態與穩定性 -5.6**

Model Top 3:
- [16] Ishikari | model#1 | rank 75.64 | ability 71.09 | 實際第 12 | 強項 狀態與穩定性 75.0 | 弱項 騎練訊號 63.1
- [18] Silver Serenade | model#2 | rank 73.00 | ability 69.35 | 實際第 9 | 強項 狀態與穩定性 79.6 | 弱項 形勢與走位 52.4
- [20] Marine Girl | model#3 | rank 70.65 | ability 66.65 | 實際第 11 | 強項 狀態與穩定性 76.6 | 弱項 形勢與走位 55.2

Actual Top 3:
- [17] Brave Xena | 實際第 1 | model#5 | rank 69.55 | ability 67.04 | 強項 賽績線 73.3 | 弱項 場地適性 58.9

### 2026-03-28 Flemington Race 1

- 條件: **Heavy** (`Heavy 8`) | 班次: **Other** (`4-Y-O & Up, Mares, Handicap`) | 場數: **8** (`Field <=8`)
- 頭馬: **Pop Award** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **級數與負重低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬完全跌出視野 / Heavy 場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 2.7 / 段速與引擎 -3.5 / 形勢與走位 -3.8**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -17.7 / 騎練訊號 -8.5**

Model Top 3:
- [5] She's An Artist | model#1 | rank 78.61 | ability 74.01 | 實際第 6 | 強項 狀態與穩定性 79.2 | 弱項 級數與負重 60.9
- [7] Fluent | model#2 | rank 74.53 | ability 70.53 | 實際第 5 | 強項 狀態與穩定性 79.9 | 弱項 級數與負重 56.9
- [3] Gentle Steel | model#3 | rank 74.06 | ability 70.06 | 實際第 4 | 強項 狀態與穩定性 79.4 | 弱項 級數與負重 57.1

Actual Top 3:
- [1] Pop Award | 實際第 1 | model#7 | rank 65.72 | ability 61.72 | 強項 賽績線 68.3 | 弱項 場地適性 53.2
- [2] Bossy Nic | 實際第 2 | model#5 | rank 69.77 | ability 66.32 | 強項 賽績線 70.3 | 弱項 級數與負重 60.7
- [4] She's Got Pizzazz | 實際第 3 | model#8 | rank 59.86 | ability 60.82 | 強項 賽績線 67.2 | 弱項 場地適性 52.8

### 2026-03-28 Flemington Race 4

- 條件: **Heavy** (`Heavy 8`) | 班次: **BM72-84** (`BM78, Handicap`) | 場數: **6** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 -55.7 / 場地適性 -61.7 / 段速與引擎 -63.2**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -73.5 / 賽績線 -73.2**

Model Top 3:
- [13] Actuality | model#1 | rank 73.21 | ability 68.86 | 實際第 7 | 強項 賽績線 72.2 | 弱項 級數與負重 59.7
- [10] Tookay Pete | model#2 | rank 69.59 | ability 65.59 | 實際第 11 | 強項 狀態與穩定性 77.7 | 弱項 級數與負重 55.9
- [9] Salsa Fellow | model#3 | rank 69.23 | ability 64.88 | 實際第 6 | 強項 狀態與穩定性 71.8 | 弱項 級數與負重 51.6

Actual Top 3:

### 2026-03-28 Flemington Race 8

- 條件: **Heavy** (`Heavy 8`) | 班次: **Group 1** (`Group 1, 3-Y-O & Up, Weight for Age, Maidens Ineligible`) | 場數: **4** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 -51.0 / 段速與引擎 -63.9 / 騎練訊號 -65.0**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -73.8 / 賽績線 -73.5**

Model Top 3:
- [11] Basilinna | model#1 | rank 71.00 | ability 67.00 | 實際第 8 | 強項 場地適性 75.2 | 弱項 級數與負重 50.1
- [10] Leica Lucy | model#2 | rank 70.42 | ability 66.07 | 實際第 6 | 強項 賽績線 73.3 | 弱項 級數與負重 50.1
- [9] Damask Rose | model#3 | rank 70.03 | ability 65.68 | 實際第 10 | 強項 賽績線 74.4 | 弱項 級數與負重 52.8

Actual Top 3:

