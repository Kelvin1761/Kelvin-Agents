# AU Auto Target Gap Report

## Target Standard

- Gold: Top 3 picks 全部跑入實際前三，目標 >= 30%
- Good: Top 1 + Top 2 picks 同時跑入實際前三，目標 >= 40%
- Pass: Top 3 picks 至少 2 匹跑入實際前三，目標 >= 60%
- Top 3 Place Precision: Top 3 picks 單入位率，目標 >= 80%

## Current Overall

- Races: **136**
- Gold: **1.5%**  | gap to target: **+39 races**
- Good: **5.9%**  | gap to target: **+47 races**
- Pass: **21.3%**  | gap to target: **+53 races**
- Top 3 Place Precision: **30.1%**  | gap to target: **+204 placing hits**
- Top 1 Hit Rate: **14.7%**
- Top 3 Contains Winner: **33.1%**

## Miss Profile

- 0-hit races: **44**
- 1-hit races: **63**
- 2-hit races: **27**
- 3-hit races: **2**

Interpretation: 要追近 Pass 60%，最實際係先將大量 `1-hit` race 推上 `2-hit`。要追 Gold，就要大幅提升 `3-hit` race 數量。

## By Condition

| Group | Races | Gold | Gap | Good | Gap | Pass | Gap | Top3 Place | Slot Gap | Top1 | Top3冠軍 | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Good/Firm | 82 | 1.2% | 24 | 6.1% | 28 | 19.5% | 34 | 29.7% | 124 | 12.2% | 30.5% | 26 | 40 | 15 | 1 |
| Heavy | 21 | 4.8% | 6 | 9.5% | 7 | 33.3% | 6 | 33.3% | 30 | 23.8% | 38.1% | 8 | 6 | 6 | 1 |
| Soft | 33 | 0.0% | 10 | 3.0% | 13 | 18.2% | 14 | 29.3% | 51 | 15.2% | 36.4% | 10 | 17 | 6 | 0 |

## By Race Class

| Group | Races | Gold | Gap | Good | Gap | Pass | Gap | Top3 Place | Slot Gap | Top1 | Top3冠軍 | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM58-70 | 61 | 1.6% | 18 | 4.9% | 22 | 19.7% | 25 | 29.5% | 93 | 11.5% | 34.4% | 20 | 29 | 11 | 1 |
| BM72-84 | 10 | 0.0% | 3 | 0.0% | 4 | 10.0% | 5 | 20.0% | 18 | 30.0% | 30.0% | 5 | 4 | 1 | 0 |
| BM88+ | 3 | 0.0% | 1 | 0.0% | 2 | 33.3% | 1 | 33.3% | 5 | 0.0% | 33.3% | 1 | 1 | 1 | 0 |
| Group 1 | 9 | 0.0% | 3 | 0.0% | 4 | 22.2% | 4 | 33.3% | 13 | 11.1% | 33.3% | 2 | 5 | 2 | 0 |
| Group 2/3 | 14 | 0.0% | 5 | 0.0% | 6 | 21.4% | 6 | 31.0% | 21 | 14.3% | 42.9% | 4 | 7 | 3 | 0 |
| Maiden | 5 | 0.0% | 2 | 20.0% | 1 | 40.0% | 1 | 46.7% | 5 | 40.0% | 40.0% | 0 | 3 | 2 | 0 |
| Other | 34 | 2.9% | 10 | 11.8% | 10 | 23.5% | 13 | 30.4% | 51 | 14.7% | 26.5% | 12 | 14 | 7 | 1 |

## By Field Size

| Group | Races | Gold | Gap | Good | Gap | Pass | Gap | Top3 Place | Slot Gap | Top1 | Top3冠軍 | 0-hit | 1-hit | 2-hit | 3-hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Field 13+ | 10 | 0.0% | 3 | 0.0% | 4 | 10.0% | 5 | 26.7% | 16 | 10.0% | 20.0% | 3 | 6 | 1 | 0 |
| Field 9-12 | 27 | 0.0% | 9 | 3.7% | 10 | 18.5% | 12 | 32.1% | 39 | 22.2% | 40.7% | 6 | 16 | 5 | 0 |
| Field <=8 | 99 | 2.0% | 28 | 7.1% | 33 | 23.2% | 37 | 30.0% | 149 | 13.1% | 32.3% | 35 | 41 | 21 | 2 |

## What The Archive Is Saying

- 最大 condition gap 來自 **Good/Firm**：Pass 尚差 **34 races**。
- 最大 class gap 來自 **BM58-70**：Pass 尚差 **25 races**。
- 最大 field-size gap 來自 **Field <=8**：Pass 尚差 **37 races**。
- 目前最重要唔係再追 Top 1，而係先將 `0-hit / 1-hit` race 壓低。
- 如果要上 Gold/Good/Pass 標準，模型核心任務應明確定義為：`提升 place-hit density`，而唔係單純拉高冠軍命中率。
