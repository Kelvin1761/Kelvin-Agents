# AU Auto Zero-Hit Race Audit

## Summary

- 0-hit races: **53**
- Good/Firm: **30**
- Soft: **8**
- Heavy: **15**
- BM58-70: **22**
- Field 9-12: **24**
- Field 13+: **23**
- 歷史賽果資料缺口: **10**

## Most Common Failure Tags

- 形勢與走位可能過信: **38**
- 頭馬完全跌出視野: **27**
- 騎練訊號可能過信: **27**
- 段速與引擎可能過信: **26**
- 中型場失手: **24**
- 大場面失手: **23**
- BM58-70 失手: **22**
- 頭馬其實仍在視野內: **16**
- Heavy 場失手: **15**
- 歷史賽果資料缺口: **10**
- 級數與負重低估: **8**
- Soft 場失手: **8**

## Most Common Underestimated Sections

- 級數與負重低估: **8**
- 騎練訊號低估: **8**
- 場地適性低估: **6**
- 形勢與走位低估: **2**
- 段速與引擎低估: **1**

## Race-By-Race Audit

### 2025-10-04 Randwick Race 1-10 Race 1

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM72, Handicap`) | 場數: **12** (`Field 9-12`)
- 頭馬: **Agita** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 -0.1 / 段速與引擎 -0.4 / 騎練訊號 -4.3**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -10.9 / 場地適性 -6.7**

Model Top 3:
- [6] Sunset Park | model#1 | rank 76.84 | ability 72.29 | 實際第 5 | 強項 狀態與穩定性 76.6 | 弱項 場地適性 59.1
- [5] Dr Evil | model#2 | rank 73.73 | ability 69.73 | 實際第 7 | 強項 狀態與穩定性 75.2 | 弱項 級數與負重 60.2
- [12] Magic Pharoah | model#3 | rank 71.82 | ability 69.15 | 實際第 4 | 強項 場地適性 74.4 | 弱項 級數與負重 57.8

Actual Top 3:
- [9] Agita | 實際第 1 | model#4 | rank 71.59 | ability 67.39 | 強項 賽績線 71.2 | 弱項 形勢與走位 58.9
- [1] Harlow Mist | 實際第 2 | model#11 | rank 64.23 | ability 61.29 | 強項 騎練訊號 64.2 | 弱項 狀態與穩定性 54.9
- [8] Highborn Harry | 實際第 3 | model#7 | rank 70.52 | ability 66.52 | 強項 賽績線 70.6 | 弱項 形勢與走位 58.2

### 2025-12-20 Randwick Race 1-10 Race 6

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM78, Handicap`) | 場數: **10** (`Field 9-12`)
- 頭馬: **Brave Call** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 1.4 / 騎練訊號 0.5 / 賽績線 -0.7**
- model top3 反而高估最多嘅 sections: **場地適性 -6.5 / 級數與負重 -3.3**

Model Top 3:
- [4] Bestower | model#1 | rank 76.57 | ability 72.22 | 實際第 5 | 強項 狀態與穩定性 80.2 | 弱項 場地適性 58.9 | risk: high_consumption_load
- [1] Belle Detelle | model#2 | rank 73.43 | ability 69.43 | 實際第 7 | 強項 場地適性 73.8 | 弱項 級數與負重 58.9
- [11] Shadashi | model#3 | rank 73.24 | ability 68.69 | 實際第 10 | 強項 級數與負重 76.3 | 弱項 場地適性 59.8

Actual Top 3:
- [2] Brave Call | 實際第 1 | model#5 | rank 72.23 | ability 68.23 | 強項 賽績線 72.0 | 弱項 場地適性 57.3
- [3] King Pedro | 實際第 2 | model#4 | rank 72.82 | ability 68.62 | 強項 狀態與穩定性 75.3 | 弱項 級數與負重 57.2
- [9] War Ribbon | 實際第 3 | model#8 | rank 71.53 | ability 67.33 | 強項 級數與負重 76.3 | 弱項 場地適性 54.0

### 2026-01-10 Flemington Race 1-10 Race 10

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM74, Handicap`) | 場數: **12** (`Field 9-12`)
- 頭馬: **Porter** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **頭馬完全跌出視野 / BM58-70 失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 0.4 / 形勢與走位 -1.0 / 段速與引擎 -1.8**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -12.6 / 級數與負重 -11.8**

Model Top 3:
- [14] Legacy Bay | model#1 | rank 79.50 | ability 75.50 | 實際第 5 | 強項 狀態與穩定性 83.8 | 弱項 形勢與走位 60.5 | risk: high_consumption_load
- [13] Hot Digity Boom | model#2 | rank 76.84 | ability 72.49 | 實際第 4 | 強項 狀態與穩定性 76.5 | 弱項 段速與引擎 66.5 | risk: high_consumption_load
- [2] Narbold | model#3 | rank 76.17 | ability 71.97 | 實際第 11 | 強項 狀態與穩定性 86.3 | 弱項 騎練訊號 60.3 | risk: top_weight

Actual Top 3:
- [4] Porter | 實際第 1 | model#7 | rank 72.33 | ability 68.13 | 強項 賽績線 74.6 | 弱項 場地適性 56.6
- [11] Paradise City | 實際第 2 | model#10 | rank 66.49 | ability 62.49 | 強項 賽績線 69.2 | 弱項 場地適性 53.2
- [3] Fear No Evil | 實際第 3 | model#5 | rank 73.38 | ability 68.83 | 強項 賽績線 70.6 | 弱項 級數與負重 58.1

### 2026-01-17 Flemington Race 1-10 Race 2

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM78, Handicap`) | 場數: **10** (`Field 9-12`)
- 頭馬: **Dictionary** | model 排名: **9** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 頭馬完全跌出視野 / BM58-70 失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 -0.5 / 賽績線 -1.4 / 段速與引擎 -1.8**
- model top3 反而高估最多嘅 sections: **場地適性 -5.4 / 狀態與穩定性 -4.7**

Model Top 3:
- [7] Leonchroi | model#1 | rank 74.82 | ability 70.82 | 實際第 5 | 強項 狀態與穩定性 74.7 | 弱項 場地適性 61.0 | risk: high_consumption_load
- [5] Scintillante | model#2 | rank 73.69 | ability 69.34 | 實際第 7 | 強項 賽績線 73.2 | 弱項 場地適性 61.0 | risk: high_consumption_load
- [8] Hot Too Go | model#3 | rank 73.09 | ability 68.54 | 實際第 6 | 強項 狀態與穩定性 73.4 | 弱項 級數與負重 59.8

Actual Top 3:
- [4] Dictionary | 實際第 1 | model#9 | rank 64.71 | ability 62.35 | 強項 賽績線 68.7 | 弱項 級數與負重 55.2
- [6] Tarvue | 實際第 2 | model#5 | rank 72.24 | ability 68.24 | 強項 賽績線 72.3 | 弱項 場地適性 59.7
- [9] Navy Heart | 實際第 3 | model#7 | rank 70.49 | ability 66.49 | 強項 賽績線 75.7 | 弱項 場地適性 54.0

### 2026-01-17 Flemington Race 1-10 Race 10

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O, BM70, Handicap`) | 場數: **10** (`Field 9-12`)
- 頭馬: **Sass Appeal** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **級數與負重低估 / 頭馬其實仍在視野內 / BM58-70 失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 2.4 / 場地適性 1.4 / 騎練訊號 -0.3**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -10.4 / 賽績線 -5.8**

Model Top 3:
- [1] Buccleuch | model#1 | rank 76.91 | ability 72.91 | 實際第 6 | 強項 狀態與穩定性 83.9 | 弱項 形勢與走位 62.8 | risk: high_consumption_load
- [6] Itazura | model#2 | rank 75.76 | ability 71.41 | 實際第 8 | 強項 賽績線 78.2 | 弱項 場地適性 57.3 | risk: high_consumption_load
- [7] Yes Maxi | model#3 | rank 74.05 | ability 70.25 | 實際第 9 | 強項 狀態與穩定性 79.6 | 弱項 形勢與走位 58.1

Actual Top 3:
- [8] Sass Appeal | 實際第 1 | model#4 | rank 73.68 | ability 69.68 | 強項 賽績線 75.1 | 弱項 形勢與走位 60.8
- [4] The Volta | 實際第 2 | model#6 | rank 72.59 | ability 68.24 | 強項 賽績線 72.3 | 弱項 級數與負重 57.2
- [9] Eden Rose | 實際第 3 | model#5 | rank 72.73 | ability 68.73 | 強項 級數與負重 74.9 | 弱項 形勢與走位 61.5

### 2026-04-25 Flemington Race 1-8 Race 2

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O, Fillies, BM70, Handicap`) | 場數: **12** (`Field 9-12`)
- 頭馬: **Concord Connie** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **級數與負重低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 6.9 / 騎練訊號 -1.3 / 賽績線 -2.1**
- model top3 反而高估最多嘅 sections: **形勢與走位 -9.8 / 狀態與穩定性 -6.2**

Model Top 3:
- [6] Carriedo | model#1 | rank 76.41 | ability 72.41 | 實際第 12 | 強項 狀態與穩定性 85.0 | 弱項 級數與負重 58.2
- [4] Cafe Au Lait | model#2 | rank 75.51 | ability 71.16 | 實際第 10 | 強項 狀態與穩定性 78.2 | 弱項 級數與負重 55.5 | risk: high_consumption_load
- [5] Cardamom | model#3 | rank 75.33 | ability 70.98 | 實際第 4 | 強項 狀態與穩定性 77.8 | 弱項 級數與負重 60.8 | risk: high_consumption_load

Actual Top 3:
- [8] Concord Connie | 實際第 1 | model#5 | rank 72.88 | ability 68.88 | 強項 賽績線 75.1 | 弱項 形勢與走位 57.3
- [14] Two To Tango | 實際第 2 | model#8 | rank 72.39 | ability 68.39 | 強項 賽績線 74.3 | 弱項 級數與負重 61.7
- [7] Cooly | 實際第 3 | model#6 | rank 72.74 | ability 68.74 | 強項 狀態與穩定性 81.6 | 弱項 形勢與走位 55.9

### 2026-04-25 Randwick Race 1-8 Race 7

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM100, Handicap`) | 場數: **10** (`Field 9-12`)
- 頭馬: **Hellsing** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **騎練訊號可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 1.0 / 段速與引擎 0.9 / 場地適性 -2.4**
- model top3 反而高估最多嘅 sections: **級數與負重 -15.5 / 賽績線 -4.9**

Model Top 3:
- [8] Caboche | model#1 | rank 72.21 | ability 67.66 | 實際第 8 | 強項 場地適性 70.1 | 弱項 段速與引擎 61.4
- [11] Kintyre | model#2 | rank 72.09 | ability 67.54 | 實際第 10 | 強項 騎練訊號 73.2 | 弱項 級數與負重 57.4
- [4] El Castello | model#3 | rank 71.46 | ability 67.26 | 實際第 9 | 強項 賽績線 73.2 | 弱項 狀態與穩定性 57.5 | risk: top_weight

Actual Top 3:
- [10] Hellsing | 實際第 1 | model#4 | rank 67.92 | ability 63.37 | 強項 場地適性 72.6 | 弱項 級數與負重 48.2
- [6] Encap | 實際第 2 | model#10 | rank 64.21 | ability 59.66 | 強項 場地適性 68.6 | 弱項 級數與負重 45.3
- [1] Cristal Clear | 實際第 3 | model#6 | rank 65.94 | ability 61.94 | 強項 騎練訊號 68.8 | 弱項 級數與負重 45.3

### 2025-08-02 Flemington Race 1-9 Race 9

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`4-Y-O & Up, Mares, BM78, Handicap`) | 場數: **13** (`Field 13+`)
- 頭馬: **Stylish** | model 排名: **6** | 頭馬其實只係排第4-6
- 初步失誤標籤: **場地適性低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 4.2 / 段速與引擎 -2.0 / 形勢與走位 -4.5**
- model top3 反而高估最多嘅 sections: **級數與負重 -11.9 / 狀態與穩定性 -8.6**

Model Top 3:
- [17] Eagle Express | model#1 | rank 78.17 | ability 73.82 | 實際第 5 | 強項 狀態與穩定性 76.4 | 弱項 場地適性 61.4 | risk: high_consumption_load
- [9] Illyivy | model#2 | rank 77.66 | ability 73.66 | 實際第 10 | 強項 狀態與穩定性 83.8 | 弱項 形勢與走位 60.2 | risk: high_consumption_load
- [5] Capricorn Star | model#3 | rank 77.44 | ability 72.89 | 實際第 8 | 強項 狀態與穩定性 80.2 | 弱項 場地適性 59.6

Actual Top 3:
- [1] Stylish | 實際第 1 | model#6 | rank 75.39 | ability 71.39 | 強項 狀態與穩定性 76.3 | 弱項 級數與負重 57.8
- [4] Terrestar | 實際第 2 | model#7 | rank 71.27 | ability 67.62 | 強項 賽績線 74.6 | 弱項 形勢與走位 56.8
- [14] Impending Shadow | 實際第 3 | model#9 | rank 67.52 | ability 65.28 | 強項 賽績線 69.2 | 弱項 級數與負重 56.1

### 2025-10-04 Randwick Race 1-10 Race 10

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM94, Handicap`) | 場數: **15** (`Field 13+`)
- 頭馬: **Disneck** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **級數與負重低估 / 形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬完全跌出視野 / BM58-70 失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 2.2 / 段速與引擎 0.4 / 騎練訊號 -3.2**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -9.5 / 形勢與走位 -7.7**

Model Top 3:
- [1] Les Vampires | model#1 | rank 76.86 | ability 72.31 | 實際第 14 | 強項 狀態與穩定性 77.9 | 弱項 級數與負重 57.8 | risk: high_consumption_load, top_weight
- [10] Kerguelen | model#2 | rank 76.83 | ability 72.63 | 實際第 5 | 強項 狀態與穩定性 81.1 | 弱項 形勢與走位 59.7 | risk: high_consumption_load
- [7] Shangri La Spring | model#3 | rank 75.53 | ability 70.73 | 實際第 7 | 強項 騎練訊號 77.2 | 弱項 級數與負重 58.9

Actual Top 3:
- [5] Disneck | 實際第 1 | model#8 | rank 72.69 | ability 68.69 | 強項 騎練訊號 69.9 | 弱項 形勢與走位 59.3
- [6] Beauty Charge | 實際第 2 | model#13 | rank 70.48 | ability 66.13 | 強項 段速與引擎 68.6 | 弱項 場地適性 59.1
- [12] Boston Rocks | 實際第 3 | model#9 | rank 72.66 | ability 69.01 | 強項 賽績線 74.6 | 弱項 形勢與走位 56.9

### 2025-12-20 Randwick Race 1-10 Race 4

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O, BM72, Handicap`) | 場數: **8** (`Field <=8`)
- 頭馬: **Plaintiff** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 頭馬完全跌出視野 / BM58-70 失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **賽績線 -0.6 / 騎練訊號 -0.7 / 形勢與走位 -2.1**
- model top3 反而高估最多嘅 sections: **級數與負重 -3.7 / 段速與引擎 -3.4**

Model Top 3:
- [2] Good Hotspur | model#1 | rank 75.19 | ability 70.64 | 實際第 6 | 強項 狀態與穩定性 79.9 | 弱項 騎練訊號 60.0 | risk: high_consumption_load
- [6] Lancelot Du Lac | model#2 | rank 74.57 | ability 69.97 | 實際第 4 | 強項 騎練訊號 75.1 | 弱項 級數與負重 62.5
- [12] Philatelic | model#3 | rank 73.00 | ability 68.80 | 實際第 7 | 強項 賽績線 71.2 | 弱項 場地適性 61.5

Actual Top 3:
- [3] Plaintiff | 實際第 1 | model#8 | rank 68.81 | ability 64.81 | 強項 賽績線 72.6 | 弱項 級數與負重 55.5
- [13] Shady Road | 實際第 2 | model#7 | rank 72.07 | ability 67.78 | 強項 賽績線 73.2 | 弱項 場地適性 58.9
- [11] Big Papa | 實際第 3 | model#5 | rank 72.70 | ability 68.35 | 強項 騎練訊號 73.6 | 弱項 場地適性 58.6

### 2025-12-31 Flemington Race 1-8 Race 7

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM66, Handicap`) | 場數: **15** (`Field 13+`)
- 頭馬: **Egerton** | model 排名: **6** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 -0.9 / 場地適性 -1.4 / 賽績線 -3.4**
- model top3 反而高估最多嘅 sections: **騎練訊號 -6.5 / 級數與負重 -5.7**

Model Top 3:
- [6] Alero | model#1 | rank 76.63 | ability 71.83 | 實際第 6 | 強項 騎練訊號 77.2 | 弱項 場地適性 61.0 | risk: high_consumption_load
- [12] Rose De Vellor | model#2 | rank 76.55 | ability 72.90 | 實際第 8 | 強項 狀態與穩定性 86.3 | 弱項 形勢與走位 59.5
- [19] Tan Tat Delight | model#3 | rank 74.71 | ability 70.71 | 實際第 11 | 強項 狀態與穩定性 78.5 | 弱項 場地適性 59.1

Actual Top 3:
- [14] Egerton | 實際第 1 | model#6 | rank 73.34 | ability 69.34 | 強項 狀態與穩定性 75.4 | 弱項 形勢與走位 56.6
- [17] Majesticity | 實際第 2 | model#15 | rank 67.61 | ability 63.96 | 強項 賽績線 71.2 | 弱項 級數與負重 54.6
- [13] Smart Little Miss | 實際第 3 | model#10 | rank 71.70 | ability 67.70 | 強項 賽績線 73.2 | 弱項 段速與引擎 60.3

### 2026-01-24 Randwick Race 1-10 Race 5

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM88, Handicap`) | 場數: **7** (`Field <=8`)
- 頭馬: **Furious** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **場地適性低估 / 騎練訊號低估 / 頭馬完全跌出視野 / BM58-70 失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 5.0 / 場地適性 2.3 / 段速與引擎 -0.2**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -12.0 / 級數與負重 -6.7**

Model Top 3:
- [11] Trapalanda | model#1 | rank 72.98 | ability 68.98 | 實際第 6 | 強項 狀態與穩定性 76.6 | 弱項 場地適性 56.9 | risk: high_consumption_load
- [7] Casino Bear | model#2 | rank 71.87 | ability 68.38 | 實際第 4 | 強項 賽績線 73.7 | 弱項 場地適性 57.3 | risk: high_consumption_load
- [9] Fay's Angels | model#3 | rank 71.86 | ability 67.97 | 實際第 5 | 強項 賽績線 71.2 | 弱項 級數與負重 59.8 | risk: high_consumption_load

Actual Top 3:
- [8] Furious | 實際第 1 | model#7 | rank 65.53 | ability 61.18 | 強項 騎練訊號 69.9 | 弱項 級數與負重 53.1
- [1] Townsend | 實際第 2 | model#5 | rank 67.88 | ability 63.53 | 強項 場地適性 74.8 | 弱項 級數與負重 49.5
- [6] Sounds Unusual | 實際第 3 | model#4 | rank 71.75 | ability 67.75 | 強項 賽績線 71.8 | 弱項 場地適性 57.7

### 2026-04-25 Flemington Race 1-8 Race 7

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM58-70** (`3-Y-O & Up, BM100, Handicap`) | 場數: **14** (`Field 13+`)
- 頭馬: **Too Darn Discreet** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **騎練訊號低估 / 形勢與走位可能過信 / 頭馬其實仍在視野內 / BM58-70 失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 2.4 / 段速與引擎 -0.0 / 級數與負重 -0.8**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -17.2 / 賽績線 -8.5**

Model Top 3:
- [15] Zakouma | model#1 | rank 77.73 | ability 73.73 | 實際第 7 | 強項 狀態與穩定性 82.8 | 弱項 級數與負重 62.4 | risk: high_consumption_load
- [13] Bring Forth | model#2 | rank 75.40 | ability 70.85 | 實際第 11 | 強項 狀態與穩定性 76.9 | 弱項 場地適性 61.5
- [3] Etna Rosso | model#3 | rank 74.96 | ability 70.96 | 實際第 4 | 強項 賽績線 75.7 | 弱項 段速與引擎 62.2 | risk: high_consumption_load, top_weight

Actual Top 3:
- [6] Too Darn Discreet | 實際第 1 | model#5 | rank 74.10 | ability 69.75 | 強項 級數與負重 70.7 | 弱項 狀態與穩定性 63.5
- [1] Land Legend | 實際第 2 | model#11 | rank 65.43 | ability 61.08 | 強項 騎練訊號 66.6 | 弱項 狀態與穩定性 51.6
- [4] Plymouth | 實際第 3 | model#7 | rank 70.80 | ability 67.00 | 強項 賽績線 70.6 | 弱項 形勢與走位 59.3

### 2025-08-02 Flemington Race 1-9 Race 5

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM72-84** (`BM78, Handicap`) | 場數: **12** (`Field 9-12`)
- 頭馬: **Vega Magnifico** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **級數與負重低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 頭馬完全跌出視野 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 5.5 / 騎練訊號 0.1 / 場地適性 -2.6**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -8.1 / 段速與引擎 -4.2**

Model Top 3:
- [1] Aztec State | model#1 | rank 74.21 | ability 70.21 | 實際第 5 | 強項 狀態與穩定性 77.9 | 弱項 級數與負重 58.1 | risk: top_weight
- [12] Catani Gardens | model#2 | rank 73.53 | ability 68.98 | 實際第 7 | 強項 賽績線 72.3 | 弱項 場地適性 59.1
- [9] Paradise Storm | model#3 | rank 73.36 | ability 69.01 | 實際第 10 | 強項 賽績線 75.1 | 弱項 場地適性 57.3 | risk: high_consumption_load

Actual Top 3:
- [8] Vega Magnifico | 實際第 1 | model#8 | rank 64.08 | ability 63.30 | 強項 賽績線 69.8 | 弱項 形勢與走位 55.9
- [14] Federer | 實際第 2 | model#5 | rank 71.22 | ability 66.87 | 強項 賽績線 69.8 | 弱項 場地適性 57.3
- [18] Maisy | 實際第 3 | model#4 | rank 71.65 | ability 67.65 | 強項 騎練訊號 69.9 | 弱項 形勢與走位 57.3

### 2025-11-01 Flemington Race 1-9 Race 9

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 2/3** (`Group 3, 4-Y-O & Up, Mares, SW + P`) | 場數: **12** (`Field 9-12`)
- 頭馬: **New York Lustre** | model 排名: **6** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 -0.8 / 級數與負重 -1.0 / 賽績線 -1.5**
- model top3 反而高估最多嘅 sections: **場地適性 -9.6 / 形勢與走位 -7.8**

Model Top 3:
- [13] Soft Love | model#1 | rank 76.91 | ability 72.56 | 實際第 7 | 強項 狀態與穩定性 75.8 | 弱項 級數與負重 64.5
- [3] She's Bulletproof | model#2 | rank 75.74 | ability 71.39 | 實際第 11 | 強項 賽績線 73.2 | 弱項 級數與負重 64.0
- [5] Stretan Angel | model#3 | rank 75.08 | ability 71.08 | 實際第 9 | 強項 級數與負重 74.2 | 弱項 形勢與走位 62.8 | risk: high_consumption_load

Actual Top 3:
- [10] New York Lustre | 實際第 1 | model#6 | rank 71.11 | ability 67.46 | 強項 級數與負重 74.4 | 弱項 形勢與走位 54.7
- [14] Flying For Fun | 實際第 2 | model#4 | rank 71.62 | ability 67.82 | 強項 賽績線 74.3 | 弱項 場地適性 57.3
- [2] Arabian Summer | 實際第 3 | model#11 | rank 69.64 | ability 65.64 | 強項 賽績線 69.2 | 弱項 場地適性 58.1

### 2025-12-26 Randwick Race 1-8 Race 2

- 條件: **Good/Firm** (`Good 4`) | 班次: **Maiden** (`3-Y-O, Maiden, Set Weights`) | 場數: **12** (`Field 9-12`)
- 頭馬: **Performance** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 0.5 / 騎練訊號 -2.3 / 場地適性 -2.5**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -8.1 / 段速與引擎 -4.2**

Model Top 3:
- [13] Snitzel Miss | model#1 | rank 75.76 | ability 71.56 | 實際第 6 | 強項 狀態與穩定性 80.0 | 弱項 級數與負重 60.4
- [5] Makhachev | model#2 | rank 73.44 | ability 69.09 | 實際第 7 | 強項 賽績線 73.2 | 弱項 場地適性 61.3
- [8] Conical Net | model#3 | rank 71.39 | ability 67.39 | 實際第 11 | 強項 賽績線 71.2 | 弱項 場地適性 57.3 | risk: high_consumption_load

Actual Top 3:
- [12] Performance | 實際第 1 | model#4 | rank 71.15 | ability 67.15 | 強項 賽績線 73.2 | 弱項 形勢與走位 57.2
- [11] Miss Supernova | 實際第 2 | model#5 | rank 70.46 | ability 66.11 | 強項 賽績線 69.5 | 弱項 段速與引擎 59.3
- [15] Bottles Of Shells | 實際第 3 | model#7 | rank 68.40 | ability 64.40 | 強項 騎練訊號 68.9 | 弱項 狀態與穩定性 58.2

### 2025-12-31 Flemington Race 1-8 Race 1

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`No Metro Wins, Handicap`) | 場數: **11** (`Field 9-12`)
- 頭馬: **Somewhere** | model 排名: **10** | 頭馬完全跌出前6
- 初步失誤標籤: **級數與負重低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬完全跌出視野 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 3.9 / 場地適性 0.2 / 騎練訊號 -2.2**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -10.0 / 賽績線 -5.9**

Model Top 3:
- [12] Vivacissimo | model#1 | rank 74.91 | ability 70.91 | 實際第 4 | 強項 狀態與穩定性 81.2 | 弱項 場地適性 56.9 | risk: high_consumption_load
- [13] Thunder Hawk | model#2 | rank 74.17 | ability 69.62 | 實際第 9 | 強項 狀態與穩定性 74.6 | 弱項 場地適性 59.1
- [5] Leg Drive | model#3 | rank 72.41 | ability 68.06 | 實際第 10 | 強項 賽績線 76.2 | 弱項 場地適性 53.6 | risk: high_consumption_load

Actual Top 3:
- [3] Somewhere | 實際第 1 | model#10 | rank 68.12 | ability 64.12 | 強項 賽績線 69.8 | 弱項 場地適性 54.0
- [9] His Finest Hour | 實際第 2 | model#7 | rank 70.23 | ability 66.23 | 強項 級數與負重 73.8 | 弱項 形勢與走位 55.2
- [6] Make It Sweet | 實際第 3 | model#8 | rank 68.45 | ability 63.90 | 強項 賽績線 69.2 | 弱項 級數與負重 54.6

### 2026-01-10 Flemington Race 1-10 Race 3

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`3-Y-O, Fillies, Handicap`) | 場數: **12** (`Field 9-12`)
- 頭馬: **Jenni The Ninja** | model 排名: **9** | 頭馬完全跌出前6
- 初步失誤標籤: **頭馬完全跌出視野 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 0.4 / 騎練訊號 -0.0 / 段速與引擎 -0.6**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -10.6 / 級數與負重 -6.7**

Model Top 3:
- [4] She's My Ex | model#1 | rank 75.65 | ability 71.10 | 實際第 4 | 強項 賽績線 75.7 | 弱項 場地適性 56.9 | risk: high_consumption_load
- [7] Breakfast | model#2 | rank 75.56 | ability 71.56 | 實際第 11 | 強項 賽績線 76.2 | 弱項 場地適性 57.3 | risk: high_consumption_load
- [11] Seven Oceans | model#3 | rank 74.75 | ability 70.40 | 實際第 8 | 強項 狀態與穩定性 76.7 | 弱項 場地適性 61.4 | risk: high_consumption_load

Actual Top 3:
- [8] Jenni The Ninja | 實際第 1 | model#9 | rank 71.37 | ability 67.37 | 強項 賽績線 71.2 | 弱項 場地適性 58.6
- [2] Military Tycoon | 實際第 2 | model#7 | rank 71.74 | ability 67.19 | 強項 形勢與走位 68.7 | 弱項 場地適性 59.7
- [6] Conscience | 實際第 3 | model#10 | rank 71.05 | ability 67.05 | 強項 賽績線 72.0 | 弱項 場地適性 58.6

### 2026-01-10 Flemington Race 1-10 Race 8

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 2/3** (`Group 3, Handicap, Maidens Ineligible`) | 場數: **11** (`Field 9-12`)
- 頭馬: **Disneck** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 頭馬完全跌出視野 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 -1.6 / 段速與引擎 -3.5 / 級數與負重 -5.1**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -16.9 / 場地適性 -10.3**

Model Top 3:
- [3] Aviatress | model#1 | rank 75.68 | ability 71.68 | 實際第 4 | 強項 狀態與穩定性 81.7 | 弱項 場地適性 60.1 | risk: high_consumption_load
- [5] Hedged | model#2 | rank 74.99 | ability 70.79 | 實際第 10 | 強項 級數與負重 73.2 | 弱項 形勢與走位 65.3 | risk: high_consumption_load
- [9] Major Share | model#3 | rank 74.66 | ability 70.66 | 實際第 7 | 強項 場地適性 75.2 | 弱項 級數與負重 58.4

Actual Top 3:
- [6] Disneck | 實際第 1 | model#7 | rank 68.99 | ability 64.99 | 強項 賽績線 69.8 | 弱項 形勢與走位 57.1
- [10] Extratwo | 實際第 2 | model#9 | rank 67.68 | ability 64.27 | 強項 級數與負重 68.3 | 弱項 場地適性 56.6
- [11] Contemporary | 實際第 3 | model#11 | rank 60.94 | ability 59.62 | 強項 賽績線 63.9 | 弱項 狀態與穩定性 51.3

### 2026-02-14 Flemington Race 1-10 Race 6

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`Handicap`) | 場數: **10** (`Field 9-12`)
- 頭馬: **Berkeley Square** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **頭馬完全跌出視野 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 1.9 / 形勢與走位 0.5 / 段速與引擎 -1.9**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -10.1 / 賽績線 -4.9**

Model Top 3:
- [3] Newfoundland | model#1 | rank 76.62 | ability 72.07 | 實際第 9 | 強項 狀態與穩定性 78.5 | 弱項 騎練訊號 63.4
- [4] Scary | model#2 | rank 75.68 | ability 71.33 | 實際第 10 | 強項 賽績線 73.7 | 弱項 騎練訊號 63.1 | risk: high_consumption_load
- [2] Saint George | model#3 | rank 75.28 | ability 71.28 | 實際第 4 | 強項 狀態與穩定性 78.0 | 弱項 段速與引擎 62.8

Actual Top 3:
- [1] Berkeley Square | 實際第 1 | model#8 | rank 73.10 | ability 69.10 | 強項 賽績線 73.7 | 弱項 級數與負重 61.8
- [6] Garachico | 實際第 2 | model#9 | rank 71.10 | ability 66.75 | 強項 場地適性 74.7 | 弱項 狀態與穩定性 57.5
- [11] Steel Run | 實際第 3 | model#7 | rank 73.14 | ability 69.14 | 強項 場地適性 71.4 | 弱項 級數與負重 62.4

### 2026-02-28 Flemington Race 1-10 Race 6

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`3-Y-O, Fillies, Handicap`) | 場數: **11** (`Field 9-12`)
- 頭馬: **Educated** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **頭馬其實仍在視野內 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 0.7 / 場地適性 0.5 / 形勢與走位 -1.7**
- model top3 反而高估最多嘅 sections: **級數與負重 -12.3 / 狀態與穩定性 -11.2**

Model Top 3:
- [7] Befuddle | model#1 | rank 78.63 | ability 74.08 | 實際第 11 | 強項 狀態與穩定性 82.4 | 弱項 騎練訊號 63.1
- [10] Headbanger | model#2 | rank 76.71 | ability 72.16 | 實際第 5 | 強項 狀態與穩定性 78.2 | 弱項 場地適性 63.2
- [8] Gwen's Girl | model#3 | rank 76.59 | ability 72.39 | 實際第 10 | 強項 狀態與穩定性 84.7 | 弱項 場地適性 59.1

Actual Top 3:
- [6] Educated | 實際第 1 | model#4 | rank 75.16 | ability 70.61 | 強項 狀態與穩定性 73.5 | 弱項 級數與負重 58.5
- [2] Thanks Gorgeous | 實際第 2 | model#9 | rank 70.29 | ability 66.29 | 強項 狀態與穩定性 73.0 | 弱項 級數與負重 49.2
- [11] Star Of Omaha | 實際第 3 | model#11 | rank 67.08 | ability 63.08 | 強項 賽績線 69.2 | 弱項 級數與負重 55.8

### 2025-08-02 Flemington Race 1-9 Race 8

- 條件: **Good/Firm** (`Good 4`) | 班次: **BM72-84** (`BM84, Handicap`) | 場數: **15** (`Field 13+`)
- 頭馬: **Too Darn Discreet** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **場地適性低估 / 段速與引擎可能過信 / 頭馬完全跌出視野 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 4.1 / 形勢與走位 -0.1 / 騎練訊號 -1.3**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -17.7 / 賽績線 -9.1**

Model Top 3:
- [11] One Long Day | model#1 | rank 82.49 | ability 78.14 | 實際第 10 | 強項 狀態與穩定性 86.7 | 弱項 段速與引擎 68.3
- [10] Black Storm | model#2 | rank 75.67 | ability 72.02 | 實際第 7 | 強項 狀態與穩定性 84.1 | 弱項 形勢與走位 58.0
- [7] Whisky On The Hill | model#3 | rank 74.93 | ability 71.28 | 實際第 8 | 強項 狀態與穩定性 76.6 | 弱項 形勢與走位 56.2

Actual Top 3:
- [15] Too Darn Discreet | 實際第 1 | model#8 | rank 71.54 | ability 67.54 | 強項 場地適性 71.9 | 弱項 級數與負重 59.5
- [16] Farhh Flung | 實際第 2 | model#12 | rank 68.06 | ability 66.94 | 強項 賽績線 67.8 | 弱項 狀態與穩定性 62.0
- [3] Hard To Cross | 實際第 3 | model#6 | rank 72.46 | ability 68.46 | 強項 賽績線 72.3 | 弱項 形勢與走位 60.5

### 2025-10-04 Flemington Race 1-10 Race 7

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 2/3** (`Group 3, Handicap`) | 場數: **16** (`Field 13+`)
- 頭馬: **Valiant King** | model 排名: **11** | 頭馬完全跌出前6
- 初步失誤標籤: **級數與負重低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 頭馬完全跌出視野 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 3.5 / 騎練訊號 -0.9 / 段速與引擎 -3.5**
- model top3 反而高估最多嘅 sections: **場地適性 -16.2 / 狀態與穩定性 -13.9**

Model Top 3:
- [9] Sayedaty Sadaty | model#1 | rank 77.92 | ability 73.92 | 實際第 12 | 強項 狀態與穩定性 85.0 | 弱項 級數與負重 60.0
- [12] Mormona | model#2 | rank 77.80 | ability 73.45 | 實際第 14 | 強項 狀態與穩定性 83.0 | 弱項 級數與負重 60.5 | risk: high_consumption_load
- [2] Revelare | model#3 | rank 76.33 | ability 71.98 | 實際第 7 | 強項 狀態與穩定性 75.3 | 弱項 級數與負重 58.8 | risk: high_consumption_load

Actual Top 3:
- [14] Valiant King | 實際第 1 | model#11 | rank 66.64 | ability 63.19 | 強項 級數與負重 68.5 | 弱項 形勢與走位 53.0
- [10] Torranzino | 實際第 2 | model#14 | rank 64.49 | ability 63.83 | 強項 賽績線 68.4 | 弱項 場地適性 58.3
- [15] Gilded Water | 實際第 3 | model#5 | rank 74.13 | ability 70.48 | 強項 狀態與穩定性 81.2 | 弱項 場地適性 57.3

### 2025-10-04 Randwick Race 1-10 Race 9

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 1** (`Group 1, 3-Y-O & Up, Handicap`) | 場數: **18** (`Field 13+`)
- 頭馬: **Royal Supremacy** | model 排名: **9** | 頭馬完全跌出前6
- 初步失誤標籤: **騎練訊號低估 / 形勢與走位可能過信 / 頭馬完全跌出視野 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 2.3 / 段速與引擎 1.9 / 級數與負重 -0.9**
- model top3 反而高估最多嘅 sections: **形勢與走位 -7.6 / 場地適性 -7.4**

Model Top 3:
- [17] Travolta | model#1 | rank 78.68 | ability 74.13 | 實際第 6 | 強項 狀態與穩定性 85.5 | 弱項 級數與負重 62.4
- [12] Glory Daze | model#2 | rank 77.35 | ability 72.80 | 實際第 13 | 強項 狀態與穩定性 85.4 | 弱項 段速與引擎 62.1
- [11] Piggyback | model#3 | rank 76.09 | ability 72.44 | 實際第 8 | 強項 狀態與穩定性 82.6 | 弱項 級數與負重 59.8

Actual Top 3:
- [13] Royal Supremacy | 實際第 1 | model#9 | rank 73.91 | ability 69.91 | 強項 賽績線 75.1 | 弱項 形勢與走位 59.6
- [9] Soul Of Spain | 實際第 2 | model#4 | rank 75.96 | ability 71.96 | 強項 狀態與穩定性 83.0 | 弱項 場地適性 59.6
- [18] Juja Kibo | 實際第 3 | model#8 | rank 73.92 | ability 70.27 | 強項 狀態與穩定性 78.2 | 弱項 形勢與走位 60.4

### 2025-11-01 Flemington Race 1-9 Race 3

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 2/3** (`Group 3, Handicap, Maidens Ineligible`) | 場數: **13** (`Field 13+`)
- 頭馬: **Caballus** | model 排名: **6** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **賽績線 -0.5 / 段速與引擎 -0.7 / 狀態與穩定性 -0.9**
- model top3 反而高估最多嘅 sections: **級數與負重 -15.6 / 騎練訊號 -7.9**

Model Top 3:
- [10] Hedged | model#1 | rank 77.21 | ability 73.21 | 實際第 6 | 強項 狀態與穩定性 76.6 | 弱項 場地適性 59.7 | risk: high_consumption_load
- [4] Star Patrol | model#2 | rank 75.41 | ability 70.86 | 實際第 11 | 強項 騎練訊號 73.8 | 弱項 級數與負重 65.0
- [6] Ameena | model#3 | rank 73.36 | ability 69.36 | 實際第 10 | 強項 場地適性 70.3 | 弱項 形勢與走位 64.0

Actual Top 3:
- [5] Caballus | 實際第 1 | model#6 | rank 70.47 | ability 66.47 | 強項 場地適性 70.3 | 弱項 級數與負重 52.8
- [9] Geegees Mistruth | 實際第 2 | model#8 | rank 69.79 | ability 65.99 | 強項 賽績線 74.6 | 弱項 形勢與走位 55.4
- [2] Bosustow | 實際第 3 | model#12 | rank 66.55 | ability 62.55 | 強項 賽績線 69.2 | 弱項 級數與負重 47.9

### 2026-01-24 Randwick Race 1-10 Race 3

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`3-Y-O & Up, Class 3, Handicap`) | 場數: **14** (`Field 13+`)
- 頭馬: **Kingdom Undersiege** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬完全跌出視野 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 -1.3 / 形勢與走位 -1.9 / 場地適性 -3.4**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -9.4 / 賽績線 -4.9**

Model Top 3:
- [13] Nova Centauri | model#1 | rank 78.68 | ability 74.88 | 實際第 12 | 強項 狀態與穩定性 86.1 | 弱項 級數與負重 63.5
- [5] Joiselle | model#2 | rank 77.71 | ability 73.71 | 實際第 11 | 強項 狀態與穩定性 86.4 | 弱項 騎練訊號 63.1
- [12] Navy Steel | model#3 | rank 76.47 | ability 72.47 | 實際第 7 | 強項 狀態與穩定性 76.9 | 弱項 形勢與走位 59.6 | risk: high_consumption_load

Actual Top 3:
- [10] Kingdom Undersiege | 實際第 1 | model#8 | rank 73.45 | ability 68.90 | 強項 狀態與穩定性 76.8 | 弱項 場地適性 55.8
- [7] Satin Stiletto | 實際第 2 | model#7 | rank 73.87 | ability 70.22 | 強項 狀態與穩定性 78.6 | 弱項 形勢與走位 59.8
- [6] Martini Mumma | 實際第 3 | model#12 | rank 68.41 | ability 66.29 | 強項 賽績線 69.8 | 弱項 形勢與走位 56.1

### 2026-02-28 Flemington Race 1-10 Race 9

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`3-Y-O, SW + P, Inglis horses only`) | 場數: **15** (`Field 13+`)
- 頭馬: **Getta Good Feeling** | model 排名: **9** | 頭馬完全跌出前6
- 初步失誤標籤: **場地適性低估 / 騎練訊號可能過信 / 頭馬完全跌出視野 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 4.5 / 形勢與走位 -0.2 / 段速與引擎 -0.6**
- model top3 反而高估最多嘅 sections: **級數與負重 -8.5 / 狀態與穩定性 -8.2**

Model Top 3:
- [12] Toronado Queen | model#1 | rank 77.24 | ability 72.69 | 實際第 12 | 強項 狀態與穩定性 78.9 | 弱項 場地適性 59.1
- [3] Alpha Sofie | model#2 | rank 76.92 | ability 72.92 | 實際第 13 | 強項 狀態與穩定性 82.6 | 弱項 場地適性 57.3 | risk: high_consumption_load
- [4] La Astro Chat | model#3 | rank 75.44 | ability 71.24 | 實際第 7 | 強項 狀態與穩定性 83.1 | 弱項 場地適性 59.1

Actual Top 3:
- [2] Getta Good Feeling | 實際第 1 | model#9 | rank 72.18 | ability 67.63 | 強項 狀態與穩定性 74.7 | 弱項 級數與負重 51.4
- [1] Nashville Jack | 實際第 2 | model#7 | rank 72.43 | ability 68.08 | 強項 狀態與穩定性 74.4 | 弱項 級數與負重 57.1
- [13] Fundamental Nature | 實際第 3 | model#8 | rank 72.33 | ability 68.68 | 強項 賽績線 73.7 | 弱項 形勢與走位 58.0

### 2026-03-07 Flemington Race 1-10 Race 9

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 1** (`Group 1, Handicap, Maidens Ineligible`) | 場數: **14** (`Field 13+`)
- 頭馬: **Caballus** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位低估 / 段速與引擎可能過信 / 頭馬完全跌出視野 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 3.7 / 騎練訊號 1.5 / 段速與引擎 -2.2**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -9.6 / 級數與負重 -8.9**

Model Top 3:
- [2] Tentyris | model#1 | rank 81.62 | ability 77.82 | 實際第 5 | 強項 狀態與穩定性 87.3 | 弱項 形勢與走位 64.4
- [13] My Gladiola | model#2 | rank 78.82 | ability 74.82 | 實際第 10 | 強項 狀態與穩定性 86.3 | 弱項 騎練訊號 63.1
- [15] Pallaton | model#3 | rank 76.60 | ability 72.60 | 實際第 8 | 強項 狀態與穩定性 79.3 | 弱項 形勢與走位 59.6 | risk: high_consumption_load

Actual Top 3:
- [6] Caballus | 實際第 1 | model#8 | rank 74.76 | ability 70.21 | 強項 狀態與穩定性 75.3 | 弱項 級數與負重 59.9
- [10] Gallant Son | 實際第 2 | model#4 | rank 76.27 | ability 72.27 | 強項 狀態與穩定性 80.6 | 弱項 級數與負重 59.8
- [4] Angel Capital | 實際第 3 | model#5 | rank 75.55 | ability 70.95 | 強項 騎練訊號 77.2 | 弱項 場地適性 57.3

### 2026-04-18 Randwick Race 2

- 條件: **Good/Firm** (`Good 4`) | 班次: **Other** (`3-Y-O & Up, Class 3, Handicap`) | 場數: **13** (`Field 13+`)
- 頭馬: **Ishikari** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 頭馬完全跌出視野 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 0.8 / 狀態與穩定性 -0.9 / 段速與引擎 -1.1**
- model top3 反而高估最多嘅 sections: **級數與負重 -8.0 / 場地適性 -3.8**

Model Top 3:
- [14] Bonnie Murringo | model#1 | rank 76.12 | ability 71.92 | 實際第 5 | 強項 賽績線 87.0 | 弱項 形勢與走位 58.7
- [13] Andale Andale | model#2 | rank 72.92 | ability 68.37 | 實際第 9 | 強項 賽績線 71.8 | 弱項 形勢與走位 59.5
- [7] Christa | model#3 | rank 71.56 | ability 67.01 | 實際第 10 | 強項 騎練訊號 67.5 | 弱項 形勢與走位 58.3

Actual Top 3:
- [10] Ishikari | 實際第 1 | model#7 | rank 68.29 | ability 64.64 | 強項 賽績線 69.2 | 弱項 形勢與走位 54.7
- [3] Occult | 實際第 2 | model#5 | rank 69.32 | ability 65.32 | 強項 狀態與穩定性 71.5 | 弱項 級數與負重 53.5
- [17] Tanglewood Jimmy | 實際第 3 | model#10 | rank 65.33 | ability 64.06 | 強項 賽績線 74.6 | 弱項 形勢與走位 54.7

### 2026-04-18 Randwick Race 9

- 條件: **Good/Firm** (`Good 4`) | 班次: **Group 1** (`Group 1, Weight for Age`) | 場數: **13** (`Field 13+`)
- 頭馬: **Beiwacht** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **場地適性低估 / 騎練訊號低估 / 頭馬完全跌出視野 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 7.5 / 場地適性 5.7 / 形勢與走位 1.4**
- model top3 反而高估最多嘅 sections: **賽績線 -21.7 / 級數與負重 -6.5**

Model Top 3:
- [5] Half Yours | model#1 | rank 76.22 | ability 72.02 | 實際第 9 | 強項 賽績線 85.3 | 弱項 級數與負重 58.7
- [11] Fangirl | model#2 | rank 75.14 | ability 71.14 | 實際第 8 | 強項 賽績線 82.2 | 弱項 形勢與走位 62.8
- [6] Pericles | model#3 | rank 74.84 | ability 70.29 | 實際第 7 | 強項 賽績線 88.0 | 弱項 級數與負重 48.4

Actual Top 3:
- [14] Beiwacht | 實際第 1 | model#7 | rank 70.49 | ability 65.69 | 強項 騎練訊號 78.5 | 弱項 級數與負重 50.5
- [12] Lazzura | 實際第 2 | model#6 | rank 71.40 | ability 66.60 | 強項 騎練訊號 76.4 | 弱項 級數與負重 54.7
- [2] Jimmysstar | 實際第 3 | model#8 | rank 70.41 | ability 66.71 | 強項 場地適性 80.8 | 弱項 級數與負重 48.4

### 2025-08-09 Randwick Race 1-10 Race 5

- 條件: **Heavy** (`Heavy 10`) | 班次: **BM58-70** (`3yo+, BM88, Handicap`) | 場數: **11** (`Field 9-12`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / BM58-70 失手 / 中型場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 -64.7 / 段速與引擎 -65.0 / 形勢與走位 -65.5**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -79.6 / 賽績線 -76.1**

Model Top 3:
- [8] Bundeena | model#1 | rank 77.44 | ability 72.89 | 實際第 8 | 強項 狀態與穩定性 79.1 | 弱項 騎練訊號 63.1
- [3] Zouperb | model#2 | rank 76.38 | ability 72.38 | 實際第 8 | 強項 狀態與穩定性 84.0 | 弱項 形勢與走位 58.7
- [4] World Alliance | model#3 | rank 75.70 | ability 71.70 | 實際第 8 | 強項 狀態與穩定性 75.6 | 弱項 級數與負重 64.2

Actual Top 3:

### 2025-08-09 Randwick Race 1-10 Race 7

- 條件: **Heavy** (`Heavy 10`) | 班次: **BM58-70** (`3yo+, Colts, Horses & Geldings, BM78, Handicap`) | 場數: **12** (`Field 9-12`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / BM58-70 失手 / 中型場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 -61.4 / 級數與負重 -62.4 / 形勢與走位 -63.2**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -77.7 / 賽績線 -75.6**

Model Top 3:
- [2] Kerguelen | model#1 | rank 77.35 | ability 73.00 | 實際第 8 | 強項 狀態與穩定性 78.3 | 弱項 級數與負重 62.5 | risk: top_weight
- [12] Theblade | model#2 | rank 74.63 | ability 70.03 | 實際第 8 | 強項 騎練訊號 76.2 | 弱項 場地適性 59.1
- [3] Little Beginnings | model#3 | rank 73.69 | ability 69.69 | 實際第 8 | 強項 狀態與穩定性 83.9 | 弱項 場地適性 55.5 | risk: top_weight

Actual Top 3:

### 2025-12-13 Randwick Race 1-10 Race 6

- 條件: **Soft** (`Soft 5`) | 班次: **BM58-70** (`3-Y-O & Up, BM88, Handicap`) | 場數: **11** (`Field 9-12`)
- 頭馬: **Pocketing** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬完全跌出視野 / Soft 場失手 / BM58-70 失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 -2.7 / 騎練訊號 -2.8 / 形勢與走位 -3.0**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -13.9 / 賽績線 -6.6**

Model Top 3:
- [9] Rotagilla | model#1 | rank 78.31 | ability 74.31 | 實際第 4 | 強項 狀態與穩定性 80.8 | 弱項 形勢與走位 63.7 | risk: high_consumption_load
- [8] Mr Buster | model#2 | rank 77.63 | ability 73.63 | 實際第 7 | 強項 狀態與穩定性 85.6 | 弱項 場地適性 59.6
- [14] Sosino | model#3 | rank 75.06 | ability 70.51 | 實際第 10 | 強項 狀態與穩定性 74.0 | 弱項 級數與負重 63.1

Actual Top 3:
- [2] Pocketing | 實際第 1 | model#7 | rank 69.72 | ability 65.72 | 強項 賽績線 70.6 | 弱項 級數與負重 57.5
- [4] Sun God | 實際第 2 | model#4 | rank 74.42 | ability 70.42 | 強項 騎練訊號 74.1 | 弱項 場地適性 58.9
- [10] Inquiring Minds | 實際第 3 | model#10 | rank 66.62 | ability 62.27 | 強項 賽績線 67.8 | 弱項 級數與負重 50.8

### 2025-08-09 Randwick Race 1-10 Race 1

- 條件: **Heavy** (`Heavy 10`) | 班次: **BM58-70** (`3yo+, BM72, Handicap`) | 場數: **15** (`Field 13+`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / BM58-70 失手 / 大場面失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 -59.1 / 形勢與走位 -59.4 / 段速與引擎 -64.4**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -80.9 / 賽績線 -77.9**

Model Top 3:
- [3] Mal Coupe | model#1 | rank 76.11 | ability 72.11 | 實際第 8 | 強項 狀態與穩定性 83.1 | 弱項 場地適性 59.1
- [2] Desi Emperor | model#2 | rank 74.62 | ability 70.97 | 實際第 8 | 強項 狀態與穩定性 83.1 | 弱項 形勢與走位 58.0
- [13] Stratafy | model#3 | rank 74.55 | ability 70.90 | 實際第 8 | 強項 狀態與穩定性 76.4 | 弱項 場地適性 59.1

Actual Top 3:

### 2025-08-09 Randwick Race 1-10 Race 3

- 條件: **Heavy** (`Heavy 10`) | 班次: **BM58-70** (`3yo+, Fillies & Mares, BM78, Handicap`) | 場數: **8** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 -63.5 / 場地適性 -64.6 / 級數與負重 -67.1**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -77.6 / 賽績線 -75.9**

Model Top 3:
- [2] Regimental Colours | model#1 | rank 77.33 | ability 72.98 | 實際第 8 | 強項 狀態與穩定性 82.2 | 弱項 形勢與走位 61.0
- [1] Dollar Magic | model#2 | rank 76.42 | ability 72.42 | 實際第 8 | 強項 狀態與穩定性 75.9 | 弱項 級數與負重 62.5 | risk: high_consumption_load, top_weight
- [5] Berezka | model#3 | rank 75.63 | ability 71.43 | 實際第 8 | 強項 狀態與穩定性 74.6 | 弱項 場地適性 59.3

Actual Top 3:

### 2025-08-09 Randwick Race 1-10 Race 4

- 條件: **Heavy** (`Heavy 10`) | 班次: **BM58-70** (`3,4yo, BM72, Handicap`) | 場數: **8** (`Field <=8`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / BM58-70 失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 -61.7 / 場地適性 -62.3 / 級數與負重 -63.4**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -76.9 / 賽績線 -75.7**

Model Top 3:
- [5] Amreekiyah | model#1 | rank 76.53 | ability 72.18 | 實際第 8 | 強項 狀態與穩定性 80.6 | 弱項 級數與負重 58.9
- [3] Tuileries | model#2 | rank 75.80 | ability 71.80 | 實際第 8 | 強項 賽績線 73.7 | 弱項 形勢與走位 62.4 | risk: high_consumption_load
- [1] Stardeel | model#3 | rank 75.08 | ability 71.08 | 實際第 8 | 強項 狀態與穩定性 77.9 | 弱項 場地適性 58.1 | risk: high_consumption_load, top_weight

Actual Top 3:

### 2025-08-09 Randwick Race 1-10 Race 6

- 條件: **Heavy** (`Heavy 10`) | 班次: **BM58-70** (`3yo+, BM78, Handicap`) | 場數: **15** (`Field 13+`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / BM58-70 失手 / 大場面失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 -60.8 / 場地適性 -62.5 / 級數與負重 -63.7**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -82.8 / 賽績線 -78.1**

Model Top 3:
- [11] Stylebender | model#1 | rank 77.32 | ability 72.97 | 實際第 8 | 強項 狀態與穩定性 84.6 | 弱項 場地適性 61.5
- [6] Piggyback | model#2 | rank 75.94 | ability 72.29 | 實際第 8 | 強項 狀態與穩定性 82.7 | 弱項 形勢與走位 61.2
- [7] Fioprospero | model#3 | rank 75.79 | ability 71.94 | 實際第 8 | 強項 狀態與穩定性 81.2 | 弱項 形勢與走位 56.7 | risk: high_consumption_load

Actual Top 3:

### 2025-08-09 Randwick Race 1-10 Race 10

- 條件: **Heavy** (`Heavy 10`) | 班次: **BM58-70** (`3yo+, BM78, Handicap`) | 場數: **17** (`Field 13+`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / BM58-70 失手 / 大場面失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **形勢與走位 -64.0 / 場地適性 -64.2 / 級數與負重 -65.0**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -79.3 / 賽績線 -75.6**

Model Top 3:
- [3] Puntin | model#1 | rank 78.21 | ability 73.66 | 實際第 8 | 強項 狀態與穩定性 82.2 | 弱項 級數與負重 59.8
- [10] Anythink Goes | model#2 | rank 76.00 | ability 71.45 | 實際第 8 | 強項 狀態與穩定性 74.7 | 弱項 形勢與走位 64.3
- [7] Pure Alpha | model#3 | rank 75.60 | ability 71.95 | 實際第 8 | 強項 狀態與穩定性 81.1 | 弱項 形勢與走位 58.0 | risk: high_consumption_load

Actual Top 3:

### 2026-02-28 Randwick Race 1-10 Race 1

- 條件: **Soft** (`Soft 6`) | 班次: **BM58-70** (`3-Y-O & Up, BM72, Handicap`) | 場數: **13** (`Field 13+`)
- 頭馬: **Bryant** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 頭馬完全跌出視野 / Soft 場失手 / BM58-70 失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 1.3 / 級數與負重 0.8 / 騎練訊號 -2.0**
- model top3 反而高估最多嘅 sections: **形勢與走位 -5.4 / 狀態與穩定性 -4.6**

Model Top 3:
- [5] Flightcrew | model#1 | rank 74.59 | ability 70.04 | 實際第 6 | 強項 賽績線 76.2 | 弱項 場地適性 57.3 | risk: high_consumption_load
- [3] Zoutastic | model#2 | rank 73.78 | ability 69.58 | 實際第 10 | 強項 賽績線 73.2 | 弱項 場地適性 59.9
- [6] Let's Go Again | model#3 | rank 73.32 | ability 69.32 | 實際第 11 | 強項 狀態與穩定性 74.5 | 弱項 級數與負重 59.9 | risk: high_consumption_load

Actual Top 3:
- [10] Bryant | 實際第 1 | model#7 | rank 71.36 | ability 67.71 | 強項 狀態與穩定性 75.6 | 弱項 形勢與走位 55.9
- [2] Shaggy | 實際第 2 | model#6 | rank 72.65 | ability 68.45 | 強項 賽績線 71.8 | 弱項 形勢與走位 61.6
- [1] Los Padres | 實際第 3 | model#12 | rank 64.24 | ability 62.40 | 強項 賽績線 69.8 | 弱項 場地適性 53.4

### 2025-08-09 Randwick Race 1-10 Race 8

- 條件: **Heavy** (`Heavy 10`) | 班次: **Group 2/3** (`Group 2, 3yo+, open, SW+P`) | 場數: **10** (`Field 9-12`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / 中型場失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 -63.8 / 形勢與走位 -64.3 / 段速與引擎 -66.9**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -80.4 / 賽績線 -77.0**

Model Top 3:
- [6] With Your Blessing | model#1 | rank 77.34 | ability 72.79 | 實際第 8 | 強項 狀態與穩定性 76.6 | 弱項 場地適性 64.7 | risk: high_consumption_load
- [7] Romeo's Choice | model#2 | rank 77.34 | ability 73.14 | 實際第 8 | 強項 狀態與穩定性 86.8 | 弱項 級數與負重 57.7
- [2] Robusto | model#3 | rank 77.24 | ability 73.04 | 實際第 8 | 強項 狀態與穩定性 77.9 | 弱項 級數與負重 64.0

Actual Top 3:

### 2025-11-04 Flemington Race 1-10 Race 6

- 條件: **Soft** (`Soft 6`) | 班次: **Maiden** (`LR, Handicap, Maidens Ineligible`) | 場數: **9** (`Field 9-12`)
- 頭馬: **Kingswood** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **騎練訊號低估 / 形勢與走位低估 / 段速與引擎可能過信 / 頭馬其實仍在視野內 / Soft 場失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 3.5 / 形勢與走位 2.2 / 級數與負重 0.7**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -11.7 / 賽績線 -4.9**

Model Top 3:
- [13] Flying Valley | model#1 | rank 71.67 | ability 67.12 | 實際第 9 | 強項 賽績線 73.7 | 弱項 場地適性 55.8
- [9] Garachico | model#2 | rank 70.16 | ability 66.16 | 實際第 7 | 強項 狀態與穩定性 74.8 | 弱項 級數與負重 50.5
- [6] Athanatos | model#3 | rank 70.02 | ability 66.02 | 實際第 6 | 強項 狀態與穩定性 74.4 | 弱項 級數與負重 54.8

Actual Top 3:
- [3] Kingswood | 實際第 1 | model#5 | rank 68.76 | ability 64.41 | 強項 騎練訊號 71.2 | 弱項 級數與負重 50.1
- [5] Saint George | 實際第 2 | model#4 | rank 68.93 | ability 64.93 | 強項 級數與負重 72.4 | 弱項 場地適性 55.5
- [11] Shaiyhar | 實際第 3 | model#9 | rank 59.97 | ability 62.09 | 強項 場地適性 75.2 | 弱項 級數與負重 53.1

### 2025-11-04 Randwick Race 1-10 Race 6

- 條件: **Heavy** (`Heavy 8`) | 班次: **Other** (`3-Y-O & Up, Handicap`) | 場數: **12** (`Field 9-12`)
- 頭馬: **So You Pence** | model 排名: **10** | 頭馬完全跌出前6
- 初步失誤標籤: **騎練訊號低估 / 形勢與走位可能過信 / 頭馬完全跌出視野 / Heavy 場失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 2.3 / 段速與引擎 -0.8 / 級數與負重 -2.7**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -9.8 / 形勢與走位 -8.1**

Model Top 3:
- [2] Mogo Magic | model#1 | rank 77.88 | ability 73.33 | 實際第 10 | 強項 狀態與穩定性 85.5 | 弱項 段速與引擎 63.4
- [1] Gallant Star | model#2 | rank 75.72 | ability 71.37 | 實際第 4 | 強項 狀態與穩定性 76.5 | 弱項 級數與負重 56.5
- [10] Chidiac | model#3 | rank 74.98 | ability 70.63 | 實際第 5 | 強項 賽績線 75.1 | 弱項 級數與負重 59.1 | risk: high_consumption_load

Actual Top 3:
- [8] So You Pence | 實際第 1 | model#10 | rank 69.53 | ability 65.18 | 強項 賽績線 72.6 | 弱項 場地適性 53.6
- [5] Lisztomania | 實際第 2 | model#5 | rank 72.28 | ability 68.28 | 強項 狀態與穩定性 77.0 | 弱項 級數與負重 55.6
- [11] Ticklebelly | 實際第 3 | model#11 | rank 67.81 | ability 65.47 | 強項 賽績線 66.7 | 弱項 狀態與穩定性 60.2

### 2026-02-28 Randwick Race 1-10 Race 5

- 條件: **Soft** (`Soft 6`) | 班次: **Group 2/3** (`Group 2, 2-Y-O, C&G, Set Weights`) | 場數: **10** (`Field 9-12`)
- 頭馬: **Campione D'italia** | model 排名: **5** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / Soft 場失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 -2.4 / 騎練訊號 -2.4 / 級數與負重 -3.3**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -8.1 / 場地適性 -7.8**

Model Top 3:
- [4] Warwoven | model#1 | rank 77.33 | ability 72.78 | 實際第 4 | 強項 騎練訊號 74.1 | 弱項 段速與引擎 61.8
- [1] Fireball | model#2 | rank 73.16 | ability 68.91 | 實際第 6 | 強項 騎練訊號 76.7 | 弱項 級數與負重 56.4 | risk: high_consumption_load
- [2] Knightsbridge | model#3 | rank 71.73 | ability 67.38 | 實際第 8 | 強項 賽績線 72.6 | 弱項 級數與負重 53.1

Actual Top 3:
- [9] Campione D'italia | 實際第 1 | model#5 | rank 68.89 | ability 64.89 | 強項 騎練訊號 73.0 | 弱項 形勢與走位 56.0
- [11] Central Europe | 實際第 2 | model#6 | rank 68.36 | ability 64.11 | 強項 騎練訊號 75.4 | 弱項 賽績線 58.0
- [3] Star Of Jamaica | 實際第 3 | model#4 | rank 68.97 | ability 64.97 | 強項 賽績線 73.4 | 弱項 級數與負重 54.4

### 2026-03-28 Flemington Race 6

- 條件: **Heavy** (`Heavy 8`) | 班次: **Other** (`LR, 3-Y-O, SW + P`) | 場數: **9** (`Field 9-12`)
- 頭馬: **Thanks Gorgeous** | model 排名: **4** | 頭馬其實只係排第4-6
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬其實仍在視野內 / Heavy 場失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **賽績線 0.5 / 狀態與穩定性 -1.1 / 段速與引擎 -1.6**
- model top3 反而高估最多嘅 sections: **級數與負重 -10.1 / 騎練訊號 -4.3**

Model Top 3:
- [2] Legacy Bound | model#1 | rank 78.30 | ability 74.30 | 實際第 7 | 強項 狀態與穩定性 84.0 | 弱項 形勢與走位 64.9
- [10] Educated | model#2 | rank 75.50 | ability 70.95 | 實際第 6 | 強項 狀態與穩定性 79.9 | 弱項 級數與負重 55.9
- [6] Military Tycoon | model#3 | rank 74.91 | ability 70.36 | 實際第 5 | 強項 騎練訊號 70.7 | 弱項 段速與引擎 65.4

Actual Top 3:
- [9] Thanks Gorgeous | 實際第 1 | model#4 | rank 73.93 | ability 69.93 | 強項 狀態與穩定性 78.2 | 弱項 騎練訊號 61.0
- [1] Tycoon Star | 實際第 2 | model#8 | rank 70.37 | ability 66.37 | 強項 狀態與穩定性 74.6 | 弱項 級數與負重 49.7
- [4] Bacash | 實際第 3 | model#5 | rank 73.07 | ability 68.52 | 強項 狀態與穩定性 75.3 | 弱項 級數與負重 54.1

### 2026-03-28 Flemington Race 7

- 條件: **Heavy** (`Heavy 8`) | 班次: **Other** (`LR, 3-Y-O & Up, SW + P`) | 場數: **12** (`Field 9-12`)
- 頭馬: **Whisky On The Hill** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **段速與引擎可能過信 / 頭馬完全跌出視野 / Heavy 場失手 / 中型場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 1.8 / 場地適性 0.7 / 形勢與走位 -0.1**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -12.6 / 賽績線 -6.3**

Model Top 3:
- [5] Point Nepean | model#1 | rank 75.92 | ability 71.92 | 實際第 12 | 強項 狀態與穩定性 77.3 | 弱項 騎練訊號 63.1
- [12] Bright Legend | model#2 | rank 74.84 | ability 70.84 | 實際第 8 | 強項 狀態與穩定性 84.3 | 弱項 級數與負重 57.2
- [7] Highland Blaze | model#3 | rank 74.22 | ability 70.22 | 實際第 6 | 強項 狀態與穩定性 81.3 | 弱項 級數與負重 57.1 | risk: high_consumption_load

Actual Top 3:
- [3] Whisky On The Hill | 實際第 1 | model#8 | rank 68.85 | ability 64.50 | 強項 場地適性 72.0 | 弱項 級數與負重 51.4
- [13] Litzdeel | 實際第 2 | model#5 | rank 73.52 | ability 70.07 | 強項 賽績線 75.7 | 弱項 形勢與走位 56.6
- [2] Paradise Storm | 實際第 3 | model#9 | rank 64.76 | ability 62.61 | 強項 賽績線 69.2 | 弱項 場地適性 53.2

### 2025-08-09 Randwick Race 1-10 Race 2

- 條件: **Heavy** (`Heavy 10`) | 班次: **Other** (`3yo+, Class 3, Handicap`) | 場數: **16** (`Field 13+`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / 大場面失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 -64.3 / 形勢與走位 -64.5 / 級數與負重 -65.5**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -76.2 / 賽績線 -75.0**

Model Top 3:
- [9] Ditterich | model#1 | rank 77.56 | ability 73.01 | 實際第 8 | 強項 狀態與穩定性 81.7 | 弱項 場地適性 59.6
- [3] Exit Fee | model#2 | rank 76.15 | ability 72.15 | 實際第 8 | 強項 騎練訊號 74.8 | 弱項 級數與負重 61.0 | risk: high_consumption_load
- [13] Nation Changing | model#3 | rank 75.43 | ability 71.23 | 實際第 8 | 強項 賽績線 73.7 | 弱項 形勢與走位 62.2 | risk: high_consumption_load

Actual Top 3:

### 2025-08-09 Randwick Race 1-10 Race 9

- 條件: **Heavy** (`Heavy 10`) | 班次: **Other** (`3yo+, open, Handicap`) | 場數: **20** (`Field 13+`)
- 頭馬: **** | model 排名: **N/A** | winner rank unknown
- 初步失誤標籤: **形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / Heavy 場失手 / 大場面失手 / 歷史賽果資料缺口**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 -62.1 / 級數與負重 -64.1 / 形勢與走位 -64.6**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -75.6 / 賽績線 -75.2**

Model Top 3:
- [16] Saltcoats | model#1 | rank 77.92 | ability 73.37 | 實際第 8 | 強項 狀態與穩定性 77.9 | 弱項 級數與負重 65.0
- [12] Glory Daze | model#2 | rank 76.21 | ability 72.21 | 實際第 8 | 強項 狀態與穩定性 77.8 | 弱項 段速與引擎 61.9
- [5] Estadio Mestalla | model#3 | rank 73.18 | ability 69.53 | 實際第 8 | 強項 賽績線 73.2 | 弱項 段速與引擎 59.4 | risk: high_consumption_load

Actual Top 3:

### 2025-08-23 Randwick Race 1-10 Race 5

- 條件: **Heavy** (`Heavy 10`) | 班次: **Group 2/3** (`Group 3, 3-Y-O & Up, Quality`) | 場數: **7** (`Field <=8`)
- 頭馬: **Nellie Leylax** | model 排名: **6** | 頭馬其實只係排第4-6
- 初步失誤標籤: **騎練訊號可能過信 / 頭馬其實仍在視野內 / Heavy 場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **段速與引擎 -0.3 / 場地適性 -0.9 / 級數與負重 -1.1**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -7.8 / 騎練訊號 -4.4**

Model Top 3:
- [2] Saltcoats | model#1 | rank 77.37 | ability 72.97 | 實際第 4 | 強項 狀態與穩定性 77.8 | 弱項 級數與負重 64.3
- [9] Hasty Honey | model#2 | rank 75.55 | ability 71.00 | 實際第 7 | 強項 狀態與穩定性 80.5 | 弱項 級數與負重 57.7
- [5] Tajanis | model#3 | rank 75.02 | ability 70.67 | 實際第 6 | 強項 賽績線 74.3 | 弱項 場地適性 58.9 | risk: high_consumption_load

Actual Top 3:
- [7] Nellie Leylax | 實際第 1 | model#6 | rank 70.62 | ability 67.39 | 強項 賽績線 70.6 | 弱項 場地適性 59.9
- [6] Belvedere Boys | 實際第 2 | model#5 | rank 72.11 | ability 68.11 | 強項 賽績線 72.3 | 弱項 級數與負重 59.7
- [10] Good Banter | 實際第 3 | model#4 | rank 74.29 | ability 69.94 | 強項 場地適性 72.0 | 弱項 騎練訊號 63.4

### 2025-11-04 Flemington Race 1-10 Race 2

- 條件: **Soft** (`Soft 6`) | 班次: **BM72-84** (`BM80, Handicap`) | 場數: **13** (`Field 13+`)
- 頭馬: **Party Crasher** | model 排名: **8** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 騎練訊號可能過信 / 頭馬完全跌出視野 / Soft 場失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 1.9 / 級數與負重 0.7 / 段速與引擎 -1.8**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -16.0 / 賽績線 -8.2**

Model Top 3:
- [14] Giggenbach | model#1 | rank 78.07 | ability 73.72 | 實際第 8 | 強項 狀態與穩定性 82.2 | 弱項 場地適性 56.9 | risk: high_consumption_load
- [3] Makdane | model#2 | rank 78.01 | ability 73.66 | 實際第 7 | 強項 狀態與穩定性 85.6 | 弱項 場地適性 61.5 | risk: top_weight
- [7] Brave Miss | model#3 | rank 76.44 | ability 72.44 | 實際第 4 | 強項 狀態與穩定性 82.4 | 弱項 級數與負重 60.7 | risk: high_consumption_load

Actual Top 3:
- [10] Party Crasher | 實際第 1 | model#8 | rank 72.59 | ability 68.59 | 強項 賽績線 74.6 | 弱項 級數與負重 59.7
- [5] Pittsburgh Pirate | 實際第 2 | model#6 | rank 73.47 | ability 69.27 | 強項 賽績線 72.3 | 弱項 場地適性 59.1
- [20] Ghetto Supastar | 實際第 3 | model#9 | rank 68.81 | ability 65.01 | 強項 場地適性 67.6 | 弱項 級數與負重 58.4

### 2025-11-04 Flemington Race 1-10 Race 7

- 條件: **Soft** (`Soft 6`) | 班次: **Group 1** (`Group 1, 3-Y-O & Up, Handicap`) | 場數: **24** (`Field 13+`)
- 頭馬: **Half Yours** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **級數與負重低估 / 形勢與走位可能過信 / 頭馬完全跌出視野 / Soft 場失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 4.0 / 段速與引擎 0.8 / 騎練訊號 -1.8**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -9.5 / 場地適性 -9.4**

Model Top 3:
- [18] Parchment Party | model#1 | rank 77.32 | ability 72.97 | 實際第 20 | 強項 狀態與穩定性 83.9 | 弱項 段速與引擎 60.6
- [24] Valiant King | model#2 | rank 74.95 | ability 71.15 | 實際第 16 | 強項 狀態與穩定性 75.2 | 弱項 級數與負重 59.8 | risk: high_consumption_load
- [2] Buckaroo | model#3 | rank 73.91 | ability 70.46 | 實際第 24 | 強項 狀態與穩定性 81.6 | 弱項 級數與負重 56.9 | risk: high_consumption_load

Actual Top 3:
- [14] Half Yours | 實際第 1 | model#7 | rank 70.40 | ability 66.40 | 強項 賽績線 73.4 | 弱項 場地適性 53.6
- [20] Goodie Two Shoes | 實際第 2 | model#8 | rank 70.36 | ability 66.71 | 強項 狀態與穩定性 81.0 | 弱項 形勢與走位 52.4
- [7] Middle Earth | 實際第 3 | model#13 | rank 69.73 | ability 66.11 | 強項 級數與負重 75.6 | 弱項 形勢與走位 56.8

### 2025-11-04 Flemington Race 1-10 Race 9

- 條件: **Soft** (`Soft 6`) | 班次: **Group 2/3** (`Group 3, 4-Y-O & Up, Mares, SW + P`) | 場數: **13** (`Field 13+`)
- 頭馬: **Dance To The Boom** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 頭馬完全跌出視野 / Soft 場失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **騎練訊號 -1.1 / 段速與引擎 -2.0 / 場地適性 -2.8**
- model top3 反而高估最多嘅 sections: **級數與負重 -10.0 / 狀態與穩定性 -8.3**

Model Top 3:
- [7] Electric Impulse | model#1 | rank 78.07 | ability 73.72 | 實際第 11 | 強項 狀態與穩定性 77.7 | 弱項 段速與引擎 64.7
- [19] Perfect Picture | model#2 | rank 75.31 | ability 70.96 | 實際第 9 | 強項 狀態與穩定性 75.8 | 弱項 場地適性 61.0 | risk: high_consumption_load
- [1] Fancify | model#3 | rank 73.95 | ability 70.30 | 實際第 8 | 強項 級數與負重 73.2 | 弱項 形勢與走位 60.7 | risk: high_consumption_load

Actual Top 3:
- [3] Dance To The Boom | 實際第 1 | model#7 | rank 71.20 | ability 67.35 | 強項 賽績線 73.7 | 弱項 形勢與走位 55.9
- [6] Roll On High | 實際第 2 | model#12 | rank 66.60 | ability 62.60 | 強項 賽績線 68.4 | 弱項 級數與負重 53.1
- [16] Jenni The Fox | 實際第 3 | model#8 | rank 71.20 | ability 67.20 | 強項 級數與負重 69.6 | 弱項 段速與引擎 62.1

### 2026-02-28 Randwick Race 1-10 Race 2

- 條件: **Soft** (`Soft 6`) | 班次: **Other** (`3-Y-O & Up, Class 3, Handicap`) | 場數: **15** (`Field 13+`)
- 頭馬: **Brave Xena** | model 排名: **12** | 頭馬完全跌出前6
- 初步失誤標籤: **形勢與走位可能過信 / 頭馬完全跌出視野 / Soft 場失手 / 大場面失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **場地適性 -0.2 / 段速與引擎 -1.3 / 騎練訊號 -1.8**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -7.7 / 形勢與走位 -6.1**

Model Top 3:
- [1] Sir Franklin | model#1 | rank 77.32 | ability 72.77 | 實際第 4 | 強項 狀態與穩定性 84.8 | 弱項 場地適性 59.6
- [10] Mrs Goldberg | model#2 | rank 76.24 | ability 71.89 | 實際第 5 | 強項 狀態與穩定性 80.6 | 弱項 場地適性 63.4
- [16] Ishikari | model#3 | rank 75.64 | ability 71.09 | 實際第 12 | 強項 狀態與穩定性 74.6 | 弱項 騎練訊號 63.1

Actual Top 3:
- [17] Brave Xena | 實際第 1 | model#12 | rank 70.83 | ability 67.37 | 強項 賽績線 73.7 | 弱項 場地適性 58.9
- [3] Neil | 實際第 2 | model#7 | rank 72.83 | ability 68.63 | 強項 賽績線 71.8 | 弱項 級數與負重 60.2
- [2] Satin Stiletto | 實際第 3 | model#8 | rank 72.72 | ability 68.52 | 強項 狀態與穩定性 74.8 | 弱項 騎練訊號 61.0

### 2026-03-28 Flemington Race 1

- 條件: **Heavy** (`Heavy 8`) | 班次: **Other** (`4-Y-O & Up, Mares, Handicap`) | 場數: **8** (`Field <=8`)
- 頭馬: **Pop Award** | model 排名: **7** | 頭馬完全跌出前6
- 初步失誤標籤: **級數與負重低估 / 形勢與走位可能過信 / 段速與引擎可能過信 / 騎練訊號可能過信 / 頭馬完全跌出視野 / Heavy 場失手**
- 實際前三平均比 model top3 高分最多嘅 sections: **級數與負重 2.7 / 段速與引擎 -3.5 / 形勢與走位 -3.8**
- model top3 反而高估最多嘅 sections: **狀態與穩定性 -19.0 / 賽績線 -9.2**

Model Top 3:
- [5] She's An Artist | model#1 | rank 78.44 | ability 73.84 | 實際第 6 | 強項 狀態與穩定性 79.1 | 弱項 級數與負重 60.9 | risk: high_consumption_load
- [7] Fluent | model#2 | rank 74.36 | ability 70.36 | 實際第 5 | 強項 狀態與穩定性 79.7 | 弱項 級數與負重 56.9 | risk: high_consumption_load
- [3] Gentle Steel | model#3 | rank 73.89 | ability 69.89 | 實際第 4 | 強項 狀態與穩定性 79.1 | 弱項 級數與負重 57.1

Actual Top 3:
- [1] Pop Award | 實際第 1 | model#7 | rank 65.39 | ability 61.39 | 強項 賽績線 66.7 | 弱項 場地適性 53.2
- [2] Bossy Nic | 實際第 2 | model#5 | rank 69.77 | ability 66.32 | 強項 賽績線 69.2 | 弱項 級數與負重 60.7
- [4] She's Got Pizzazz | 實際第 3 | model#8 | rank 59.86 | ability 60.82 | 強項 賽績線 65.3 | 弱項 場地適性 52.8

