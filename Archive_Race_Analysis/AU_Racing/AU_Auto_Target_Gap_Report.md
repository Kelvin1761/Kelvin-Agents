# AU Auto Target Gap Report

## Target Standard

- Gold: Top 3 picks 全部跑入實際前三，目標 >= 30%
- Good: Top 1 + Top 2 picks 同時跑入實際前三，目標 >= 40%
- Pass: Top 3 picks 至少 2 匹跑入實際前三，目標 >= 60%
- Top 3 Place Precision: Top 3 picks 單入位率，目標 >= 80%

## Current Overall

- Races: **315**
- Gold: **3.8%**  | gap to target: **+83 races**
- Good: **16.5%**  | gap to target: **+74 races**
- Pass: **35.9%**  | gap to target: **+76 races**
- Top 3 Place Precision: **41.1%**  | gap to target: **+368 placing hits**
- Top 1 Hit Rate: **17.5%**
- Top 3 Contains Winner: **47.3%**

## Miss Profile

- 0-hit races: **52**
- 1-hit races: **150**
- 2-hit races: **101**
- 3-hit races: **12**

Interpretation: 要追近 Pass 60%，最實際係先將大量 `1-hit` race 推上 `2-hit`。要追 Gold，就要大幅提升 `3-hit` race 數量。

## By Condition

| Group | Races | Gold | Gap | Good | Gap | Pass | Gap | Top3 Place | Slot Gap | Top1 | Top3冠軍 | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Good/Firm | 216 | 5.1% | 54 | 17.6% | 49 | 35.6% | 53 | 42.4% | 244 | 19.4% | 49.5% | 29 | 110 | 66 | 11 |
| Heavy | 40 | 2.5% | 11 | 20.0% | 8 | 37.5% | 9 | 34.2% | 55 | 15.0% | 37.5% | 15 | 10 | 14 | 1 |
| Soft | 59 | 0.0% | 18 | 10.2% | 18 | 35.6% | 15 | 40.7% | 70 | 11.9% | 45.8% | 8 | 30 | 21 | 0 |

## By Race Class

| Group | Races | Gold | Gap | Good | Gap | Pass | Gap | Top3 Place | Slot Gap | Top1 | Top3冠軍 | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM58-70 | 124 | 4.0% | 33 | 17.7% | 28 | 37.1% | 29 | 41.4% | 144 | 16.1% | 46.8% | 21 | 57 | 41 | 5 |
| BM72-84 | 17 | 5.9% | 5 | 11.8% | 5 | 35.3% | 5 | 41.2% | 20 | 5.9% | 47.1% | 3 | 8 | 5 | 1 |
| BM88+ | 5 | 0.0% | 2 | 20.0% | 1 | 40.0% | 1 | 46.7% | 5 | 20.0% | 80.0% | 0 | 3 | 2 | 0 |
| Group 1 | 28 | 10.7% | 6 | 39.3% | 1 | 57.1% | 1 | 53.6% | 23 | 28.6% | 57.1% | 2 | 10 | 13 | 3 |
| Group 2/3 | 59 | 1.7% | 17 | 15.3% | 15 | 33.9% | 16 | 40.7% | 70 | 18.6% | 50.8% | 8 | 31 | 19 | 1 |
| Maiden | 9 | 0.0% | 3 | 11.1% | 3 | 22.2% | 4 | 33.3% | 13 | 33.3% | 44.4% | 2 | 5 | 2 | 0 |
| Other | 73 | 2.7% | 20 | 8.2% | 24 | 28.8% | 23 | 36.5% | 96 | 15.1% | 39.7% | 16 | 36 | 19 | 2 |

## By Field Size

| Group | Races | Gold | Gap | Good | Gap | Pass | Gap | Top3 Place | Slot Gap | Top1 | Top3冠軍 | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field 13+ | 81 | 0.0% | 25 | 6.2% | 28 | 16.0% | 36 | 29.2% | 124 | 7.4% | 28.4% | 23 | 45 | 13 | 0 |
| Field 9-12 | 181 | 4.4% | 47 | 19.9% | 37 | 37.0% | 42 | 42.7% | 203 | 21.0% | 51.9% | 24 | 90 | 59 | 8 |
| Field <=8 | 53 | 7.5% | 12 | 20.8% | 11 | 62.3% | 0 | 53.5% | 43 | 20.8% | 60.4% | 5 | 15 | 29 | 4 |

## What The Archive Is Saying

- 最大 condition gap 來自 **Good/Firm**：Pass 尚差 **53 races**。
- 最大 class gap 來自 **BM58-70**：Pass 尚差 **29 races**。
- 最大 field-size gap 來自 **Field 9-12**：Pass 尚差 **42 races**。
- 目前最重要唔係再追 Top 1，而係先將 `0-hit / 1-hit` race 壓低。
- 如果要上 Gold/Good/Pass 標準，模型核心任務應明確定義為：`提升 place-hit density`，而唔係單純拉高冠軍命中率。
