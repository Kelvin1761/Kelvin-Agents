# AU Auto Archive Calibration Report

- Raw sample races: **316**
- Raw sample horses: **3482**
- Clean sample races: **305**
- Clean sample horses: **3345**
- Excluded result-gap races: **11**
- Model top-1 win rate: **16.5%** raw | **17.0%** clean
- Model top-3 contains winner: **40.8%** raw | **42.3%** clean
- Model top-3 place precision: **38.1%** raw | **39.2%** clean
- Market favourite win rate: **34.8%** raw | **36.1%** clean
- Market favourite place rate: **67.1%** raw | **69.2%** clean
- Analysis profile: **Market-agnostic horse analysis**

## Condition Breakdown (Clean Sample)

| Condition | Races | Horses | Model@1 | Model@Top3 | Top3 Precision | Fav@1 | Fav@Top3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Good/Firm | 216 | 2327 | 17.6% | 43.1% | 38.9% | 35.6% | 71.3% |
| Soft | 60 | 717 | 13.3% | 35.0% | 38.9% | 33.3% | 63.3% |
| Heavy | 29 | 301 | 20.7% | 51.7% | 42.5% | 44.8% | 65.5% |

## Section Diagnostics

| Section | Current | Suggested | Delta | Pairwise | Winner@1 | Winner@Top3 | Top3 Precision | Winner Lift | Spread |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 賽績線 | 0.17 | 0.20 | +0.03 | 0.575 | 17.7% | 45.9% | 40.4% | 1.20 | 3.09 |
| 狀態與穩定性 | 0.18 | 0.20 | +0.02 | 0.574 | 17.7% | 45.2% | 39.2% | 2.87 | 6.37 |
| 騎練訊號 | 0.16 | 0.14 | -0.02 | 0.529 | 10.8% | 35.4% | 30.6% | 0.57 | 3.64 |
| 檔位形勢 | 0.09 | 0.12 | +0.03 | 0.522 | 12.5% | 27.2% | 31.5% | 0.17 | 3.06 |
| 場地適性 | 0.13 | 0.12 | -0.01 | 0.518 | 9.8% | 31.1% | 30.2% | 0.31 | 4.39 |
| 段速與引擎 | 0.21 | 0.11 | -0.10 | 0.501 | 9.8% | 31.8% | 29.9% | 0.10 | 0.83 |
| 級數與負重 | 0.06 | 0.11 | +0.05 | 0.494 | 8.9% | 29.8% | 29.8% | -0.38 | 5.09 |

## What To Raise

- `賽績線` appears under-weighted: suggested 0.20 vs current 0.17, pairwise 0.575, winner@top3 45.9%.
- `檔位形勢` appears under-weighted: suggested 0.12 vs current 0.09, pairwise 0.522, winner@top3 27.2%.
- `級數與負重` appears under-weighted: suggested 0.11 vs current 0.06, pairwise 0.494, winner@top3 29.8%.

## What To Trim

- `段速與引擎` looks overweight: suggested 0.11 vs current 0.21, pairwise 0.501, average spread 0.83.

## Blind Spots

- `賽績線` still lacks discrimination: score spread only 3.09.
- `騎練訊號` still lacks discrimination: pairwise only 0.529 and score spread only 3.64.
- `檔位形勢` still lacks discrimination: pairwise only 0.522 and score spread only 3.06.
- `場地適性` still lacks discrimination: pairwise only 0.518.
- `段速與引擎` still lacks discrimination: pairwise only 0.501 and score spread only 0.83.
- `級數與負重` still lacks discrimination: pairwise only 0.494.

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

