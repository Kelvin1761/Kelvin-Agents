# AU 逐場反推權重診斷

**賽後 oracle，唔係預測改善；禁止部署逐場權重。**

Development：1762 場，['2026-08-05', '2026-09-21']；失手 1176 場，成功 586 場。
Terminal 811 場完全冇做反推／分析；對照配對 533 組（同馬群大細、日期最近、唔重用）。

失手＝Gold、Good 兩項都未達；Gold＝實際前三全入模型 Top4；Good＝首兩揀都上名。

| 診斷 | Gold | Good | Pass | 實際前三平均模型排名 |
|---|---:|---:|---:|---:|
| 現行 baseline | 21.5% | 25.7% | 49.7% | 4.12 |
| local hindsight | 27.9% | 34.7% | 59.0% | 3.79 |
| positive hindsight | 65.6% | 72.6% | 93.5% | 2.74 |
| signed hindsight | 91.4% | 93.8% | 99.7% | 2.25 |

local：每維 ±25%；positive：非負任意配權；signed：每維可反向至 ±原有總係數。全部固定係數總和，全部 overlay 凍結。
失手場可同時達 Gold＋Good：local 19、positive 455、signed 969。
較寬鬆嘅原定 Good 標準（Gold 或 Good 任一）：搜索已搵到 local 172、positive 861、signed 1129 場。呢個係已搵到解嘅數目，唔係 exact 不可行判決。
失手場可完整排返全場賽果次序（LP）：local 0、positive 25、signed 198。
positive 仍做唔到 721 場；signed 仍做唔到 207 場；失手場有上名馬被其他馬全維度／overlay 支配：456 場。

有限搜索搵最好 primary 組合；未有 Gold＋Good 解時，枚舉線性規劃驗證。不可行只針對指定邊界、0.001 分 margin、六維同凍結 overlay，唔代表缺乏所有可用訊號。
最近權重只係已搵到解嘅距離上界；分位數係搜索雲嘅條件分布，唔係可信區間，唔代表權重可唯一識別。

## 重複方向（positive，同樣最好 primary 解）

| 維度 | 失手：所有解加／減 | 成功：所有解加／減 | 配對失手加／減 | 配對成功加／減 |
|---|---:|---:|---:|---:|
| stability | 16/195（n=1176） | 2/56（n=586） | 4/109（n=533） | 1/52（n=533） |
| pace_perf | 56/64（n=1176） | 4/26（n=586） | 24/35（n=533） | 4/24（n=533） |
| jockey_trainer | 22/183（n=1176） | 3/56（n=586） | 8/82（n=533） | 3/49（n=533） |
| class_weight | 22/66（n=1176） | 7/19（n=586） | 13/35（n=533） | 6/16（n=533） |
| track | 64/5（n=1176） | 22/2（n=586） | 29/2（n=533） | 19/2（n=533） |
| preparation | 27/2（n=1176） | 9/2（n=586） | 15/1（n=533） | 9/2（n=533） |

加／減門檻＝原係數總和 1%；少於 20 個同樣最好 primary 解唔計方向。方向只描述搜索到嘅賽後解集，唔係所有數學可行解。按失手條件篩選本身會產生偏差，唔係因果證據。

## Leaf 場內判別力（剔除任一端中性 60 嘅配對）

| Leaf | 失手 AUC／對數 | 成功 AUC／對數 | 失手中性率 |
|---|---:|---:|---:|
| class_score | 0.540 / 10557 | 0.650 / 4365 | 37.3% |
| confidence_score | 0.517 / 24876 | 0.557 / 10020 | 0.0% |
| consistency_score | 0.546 / 24882 | 0.653 / 10023 | 0.0% |
| distance_score | 0.543 / 18129 | 0.590 / 7382 | 15.7% |
| form_score | 0.568 / 21844 | 0.758 / 8614 | 7.2% |
| formline_score | 0.513 / 18464 | 0.548 / 7165 | 16.3% |
| health_score | 0.506 / 13186 | 0.496 / 5068 | 29.3% |
| jockey_horse_fit_score | 0.549 / 18102 | 0.638 / 7023 | 15.0% |
| jockey_score | 0.552 / 24069 | 0.674 / 9715 | 2.1% |
| pace_figure_score | 0.559 / 23651 | 0.712 / 9553 | 2.9% |
| pace_map_score | 0.526 / 24882 | 0.534 / 10023 | 0.0% |
| performance_quality_score | 0.580 / 24882 | 0.785 / 10023 | 0.0% |
| preparation_score | 0.519 / 4301 | 0.546 / 1708 | 65.2% |
| rating_score | 0.546 / 23306 | 0.684 / 9185 | 3.8% |
| sectional_score | 0.529 / 8682 | 0.558 / 3358 | 46.0% |
| track_score | 0.528 / 24882 | 0.585 / 10023 | 0.0% |
| trainer_score | 0.563 / 20994 | 0.706 / 8476 | 9.4% |
| trial_score | 0.550 / 15175 | 0.605 / 6373 | 26.0% |
| weight_score | 0.500 / 617 | 0.500 / 222 | 86.7% |

## 只用過去 dev 失手共識，測下一個 dev fold

| Fold | 測試場數 | Gold Δ | Good Δ | Pass Δ |
|---|---:|---:|---:|---:|
| 2 | 401 | -2.49pp | +0.50pp | +0.25pp |
| 3 | 291 | -4.12pp | -2.75pp | -1.37pp |
| 4 | 377 | +0.27pp | -0.53pp | +0.00pp |
| 5 | 339 | +0.29pp | -0.59pp | -0.88pp |

呢個係預先固定嘅可轉移性 sanity check，冇 bootstrap／promotion 判決；唔用嚟揀新配置。

## 場次切片

| Cohort | 場數 | 失手 | positive 同達 Gold＋Good |
|---|---:|---:|---:|
| distance:1201-1600 | 727 | 512 | 199 |
| distance:1601-2000 | 176 | 117 | 38 |
| distance:2001+ | 106 | 60 | 24 |
| distance:≤1200 | 753 | 487 | 194 |
| field:11-12 | 430 | 337 | 109 |
| field:13+ | 166 | 137 | 39 |
| field:9-10 | 591 | 407 | 158 |
| field:≤8 | 575 | 295 | 149 |
| going:Good | 47 | 28 | 14 |
| going:Good 4 | 615 | 405 | 185 |
| going:Heavy 10 | 41 | 25 | 12 |
| going:Heavy 8 | 83 | 56 | 15 |
| going:Heavy 9 | 40 | 25 | 11 |
| going:Soft 5 | 389 | 269 | 95 |
| going:Soft 6 | 257 | 169 | 53 |
| going:Soft 7 | 150 | 109 | 34 |
| going:Synthetic | 104 | 62 | 22 |
| race_class:Unknown | 203 | 137 | 48 |
| track:Ballarat Synthetic | 44 | 26 | 8 |
| track:Belmont | 52 | 37 | 12 |
| track:Bendigo | 33 | 21 | 9 |
| track:Bunbury | 21 | 13 | 5 |
| track:Cairns | 24 | 18 | 7 |
| track:Canberra | 30 | 19 | 8 |
| track:Canterbury | 25 | 16 | 8 |
| track:Caulfield | 29 | 24 | 7 |
| track:Coffs Harbour | 22 | 16 | 6 |
| track:Devonport | 28 | 14 | 6 |
| track:Doomben | 49 | 36 | 12 |
| track:Eagle Farm | 44 | 33 | 9 |
| track:Geelong | 26 | 21 | 8 |
| track:Gold Coast | 24 | 12 | 6 |
| track:Grafton | 20 | 12 | 5 |
| track:Hawkesbury | 30 | 11 | 8 |
| track:Ipswich | 43 | 27 | 14 |
| track:Kalgoorlie | 31 | 27 | 7 |
| track:Kembla Grange | 23 | 15 | 5 |
| track:Morphettville | 52 | 35 | 14 |
| track:Newcastle | 27 | 20 | 11 |
| track:Northam | 28 | 18 | 4 |
| track:Pakenham Synthetic | 25 | 20 | 7 |
| track:Randwick | 39 | 31 | 13 |
| track:Rosehill | 20 | 15 | 7 |
| track:Sandown | 42 | 33 | 13 |
| track:Seymour | 24 | 18 | 6 |
| track:Sunshine Coast | 39 | 29 | 8 |
| track:Townsville | 37 | 28 | 9 |
| track:Warrnambool | 23 | 14 | 4 |
| track:Wodonga | 23 | 18 | 4 |
| track:Wyong | 24 | 12 | 5 |

## 最難修復嘅場次

| 場次 | baseline | local／positive／signed 可同達 |
|---|---|---|
| 2026-08-15 Caulfield Race 1-9 R2 | Miss | 不可／不可／不可 |
| 2026-08-08 Townsville Race 1-8 R2 | Miss | 不可／不可／不可 |
| 2026-08-15 Warracknabeal Race 1-7 R6 | Miss | 不可／不可／不可 |
| 2026-09-05 Randwick Race 1-10 R2 | Miss | 不可／不可／不可 |
| 2026-08-15 Rosehill Race 1-10 R3 | Miss | 不可／不可／不可 |
| 2026-08-23 Kalgoorlie Race 1-8 R3 | Miss | 不可／不可／不可 |
| 2026-09-06 Kalgoorlie Race 1-8 R8 | Miss | 不可／不可／不可 |
| 2026-09-13 Northam Race 1-7 R6 | Miss | 不可／不可／不可 |
| 2026-08-09 Kalgoorlie Race 1-8 R8 | 1 Hit | 不可／不可／不可 |
| 2026-08-30 Strathalbyn Race 1-8 R7 | Miss | 不可／不可／不可 |
| 2026-09-12 Flemington Race 1-10 R10 | Miss | 不可／不可／不可 |
| 2026-09-12 Morphettville Race 1-9 R4 | Miss | 不可／不可／不可 |
| 2026-08-08 Eagle Farm Race 1-9 R4 | Miss | 不可／不可／不可 |
| 2026-08-08 Morphettville Race 1-9 R7 | Miss | 不可／不可／不可 |
| 2026-08-19 Belmont Race 1-8 R5 | Miss | 不可／不可／不可 |
| 2026-09-02 Belmont Race 1-7 R3 | Miss | 不可／不可／不可 |
| 2026-09-05 Gold Coast Race 1-8 R8 | Miss | 不可／不可／不可 |
| 2026-09-10 Bunbury Race 1-7 R7 | Miss | 不可／不可／不可 |
| 2026-09-18 Ballarat Race 1-9 R4 | Miss | 不可／不可／不可 |
| 2026-09-18 Ballarat Race 1-9 R5 | Miss | 不可／不可／不可 |
| 2026-08-15 Doomben Race 1-9 R6 | Miss | 不可／不可／不可 |
| 2026-08-27 Northam Race 1-8 R7 | Miss | 不可／不可／不可 |
| 2026-09-04 Canberra Race 1-8 R7 | Miss | 不可／不可／不可 |
| 2026-09-17 Illawarra Grange Race 1-7 R5 | Miss | 不可／不可／不可 |
| 2026-08-15 Caulfield Race 1-9 R3 | Miss | 不可／不可／不可 |

## 證據限制

- 用現行引擎重建歷史分數；唔係當日已發佈預測。舊檔、mutable J/T／draw 等來源未逐欄證明 PIT，leakage audit＝FLAG。
- 預設只診斷 2026-08-05 起嘅 dev；日期篩選喺完整語料日期切分之後做，唔改 terminal 邊界。
- 只查六個現行維度，唔重啟退役特徵；常數／中性率唔足以單獨證明管線故障。
- 所有 oracle 權重用咗賽果，絕對唔可以當賽前配置；輸出只供提出新假設。

Dataset SHA256：`db0ffe220069c1c8e3b40275a5e497355c95ed977b3505d2e578a541c12f9519`
Engine SHA256：`5e644ed3b23827f6c43d0e8b49c2e90ee1cf05449ef0378e30d4a0cac80a7f86`
Commit：`0116c740330db7f02f9d04d2884e211b1d494517`（另記完整 dirty status）
