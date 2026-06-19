# AU Auto Archive Calibration Report

- Raw sample races: **316**
- Raw sample horses: **3482**
- Clean sample races: **305**
- Clean sample horses: **3345**
- Excluded result-gap races: **11**
- Model top-1 win rate: **24.4%** raw | **25.2%** clean
- Model top-3 contains winner: **50.3%** raw | **52.1%** clean
- Model top-3 place precision: **42.6%** raw | **44.0%** clean
- Market favourite win rate: **34.8%** raw | **36.1%** clean
- Market favourite place rate: **67.1%** raw | **69.2%** clean
- Analysis profile: **Market-agnostic horse analysis**

## Condition Breakdown (Clean Sample)

| Condition | Races | Horses | Model@1 | Model@Top3 | Top3 Precision | Fav@1 | Fav@Top3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Good/Firm | 216 | 2327 | 26.9% | 51.4% | 44.4% | 35.6% | 71.3% |
| Soft | 60 | 717 | 11.7% | 50.0% | 41.1% | 33.3% | 63.3% |
| Heavy | 29 | 301 | 41.4% | 62.1% | 47.1% | 44.8% | 65.5% |

## Section Diagnostics

| Section | Current | Suggested | Delta | Pairwise | Winner@1 | Winner@Top3 | Top3 Precision | Winner Lift | Spread |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 狀態與穩定性 | 0.28 | 0.19 | -0.09 | 0.579 | 18.0% | 44.3% | 40.8% | 1.85 | 4.30 |
| 騎練訊號 | 0.17 | 0.17 | -0.00 | 0.549 | 18.7% | 43.0% | 37.5% | 0.76 | 2.27 |
| 場地適性 | 0.12 | 0.15 | +0.03 | 0.537 | 16.7% | 38.4% | 34.3% | 0.81 | 3.60 |
| 檔位形勢 | 0.21 | 0.14 | -0.07 | 0.541 | 17.4% | 34.4% | 32.7% | 0.35 | 1.45 |
| 賽績線 | 0.06 | 0.13 | +0.07 | 0.503 | 13.1% | 39.0% | 35.4% | 0.01 | 0.50 |
| 級數與負重 | 0.03 | 0.12 | +0.09 | 0.524 | 8.9% | 34.8% | 31.7% | -0.06 | 1.13 |
| 段速與引擎 | 0.13 | 0.11 | -0.02 | 0.507 | 11.5% | 29.5% | 31.6% | 0.05 | 1.19 |

## What To Raise

- `場地適性` appears under-weighted: suggested 0.15 vs current 0.12, pairwise 0.537, winner@top3 38.4%.
- `賽績線` appears under-weighted: suggested 0.13 vs current 0.06, pairwise 0.503, winner@top3 39.0%.
- `級數與負重` appears under-weighted: suggested 0.12 vs current 0.03, pairwise 0.524, winner@top3 34.8%.

## What To Trim

- `狀態與穩定性` looks overweight: suggested 0.19 vs current 0.28, pairwise 0.579, average spread 4.30.
- `檔位形勢` looks overweight: suggested 0.14 vs current 0.21, pairwise 0.541, average spread 1.45.

## Blind Spots

- `騎練訊號` still lacks discrimination: score spread only 2.27.
- `場地適性` still lacks discrimination: pairwise only 0.537 and score spread only 3.60.
- `檔位形勢` still lacks discrimination: score spread only 1.45.
- `賽績線` still lacks discrimination: pairwise only 0.503 and score spread only 0.50.
- `級數與負重` still lacks discrimination: pairwise only 0.524 and score spread only 1.13.
- `段速與引擎` still lacks discrimination: pairwise only 0.507 and score spread only 1.19.

## Coverage Gaps

- `sectional trend missing` observed **124** times in scanned archive horses.
- `formline missing` observed **71** times in scanned archive horses.
- `historical result gap races` observed **11** times in scanned archive horses.

## Interpretation

- `Pairwise` 越高，代表該 section 單獨拿出來排 horses 時，越能跟實際名次方向對上。
- `Winner@1` 代表該 section 自己的第一名直接中頭馬的比例。
- `Winner@Top3` 代表該 section 的 top-3 至少包住頭馬。
- `Top3 Precision` 代表該 section 揀出的 top-3，有幾多最終真係跑入前三。
- `Winner Lift` 代表頭馬在該 section 分數平均比全場高幾多分。
- `Spread` 太低通常代表該 section 太平，對排序幫助有限。

