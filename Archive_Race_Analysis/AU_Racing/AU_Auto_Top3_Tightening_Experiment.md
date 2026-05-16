# AU Auto Top3 Tightening Experiment

Comparison: 用 clean archive 比較舊 live `rank_score`（未計 place tightening），對上現行 `rank_score`（已加入 archive-derived place tightening layer）之後，前三收窄有冇改善。

## Live Tightening Formula

- Scale: **1.40**
- `form_score`: **+0.103**
- `trial_score`: **+0.199**
- `trainer_score`: **+0.234**
- `jockey_horse_fit_score`: **+0.170**
- `consistency_score`: **+0.093**
- `distance_score`: **-0.033**
- `confidence_score`: **+0.027**
- `weight_score`: **-0.141**

## Clean Sample Overall

- Races: **303**
- Top 1: **20.5%** -> **20.8%**
- Top 3 包頭馬: **49.2%** -> **49.2%**
- Top 3 Place Precision: **42.2%** -> **42.4%**
- Gold: **3.0%** -> **3.0%**
- Good: **16.2%** -> **16.2%**
- Minimum: **38.0%** -> **38.3%**
- 0-hit races: **43** -> **43**
- 1-hit races: **145** -> **144**
- 由 rank 4-6 拉返入 top3 並脫離 0-hit: **0** 場

## Core Bucket: Good/Firm + BM58-70 + Field 9-12

- Races: **54**
- Top 1: **20.4%** -> **22.2%**
- Top 3 包頭馬: **50.0%** -> **50.0%**
- Top 3 Place Precision: **41.4%** -> **41.4%**
- Gold: **3.7%** -> **3.7%**
- Good: **11.1%** -> **11.1%**
- Minimum: **35.2%** -> **35.2%**
- 0-hit races: **8** -> **8**
- 1-hit races: **27** -> **27**
- 由 rank 4-6 拉返入 top3 並脫離 0-hit: **0** 場

## Changed Races

- Top3 組合有變動嘅 clean races: **7**

- 2025-11-04 Randwick Race 1-10 Race 9: hits **1 -> 2**, `Well Timed(5) / Magnatear(1) / Belleistic Kids(6)` -> `Well Timed(5) / Magnatear(1) / Rock Empire(2)`
- 2026-02-28 Randwick Race 1-10 Race 1: hits **0 -> 0**, `Flightcrew(6) / Jambalaya(4) / Zoutastic(10)` -> `Flightcrew(6) / Zoutastic(10) / Let's Go Again(11)`
- 2026-01-03 Randwick Race 1-10 Race 9: hits **1 -> 1**, `Hawker Hall(4) / Candlewick(3) / Massira(8)` -> `Hawker Hall(4) / Candlewick(3) / Manwari(9)`
- 2025-12-26 Randwick Race 1-8 Race 5: hits **1 -> 1**, `Who But Roo(6) / Power Of The Brave(1) / Indefensible(5)` -> `Power Of The Brave(1) / Who But Roo(6) / Indefensible(5)`
- 2025-12-13 Randwick Race 1-10 Race 7: hits **1 -> 1**, `Future History(1) / Hollywood Hero(4) / Age Of Sail(6)` -> `Future History(1) / Hollywood Hero(4) / Speycaster(5)`
- 2025-12-13 Randwick Race 1-10 Race 5: hits **1 -> 1**, `Bohemian Rhapsody(8) / Internal Affairs(2) / Sheza Boom(6)` -> `Bohemian Rhapsody(8) / Internal Affairs(2) / Elio(4)`
- 2025-10-04 Randwick Race 1-10 Race 1: hits **0 -> 0**, `Sunset Park(5) / Magic Pharoah(4) / Dr Evil(7)` -> `Sunset Park(5) / Dr Evil(7) / Magic Pharoah(4)`
