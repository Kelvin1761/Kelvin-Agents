# AU Auto Archive Calibration Report

- Raw sample races: **315**
- Raw sample horses: **3468**
- Clean sample races: **303**
- Clean sample horses: **3324**
- Excluded result-gap races: **12**
- Model top-1 win rate: **17.5%** raw | **18.2%** clean
- Model top-3 contains winner: **47.3%** raw | **49.2%** clean
- Model top-3 place precision: **41.1%** raw | **42.4%** clean
- Market favourite win rate: **34.9%** raw | **36.3%** clean
- Market favourite place rate: **67.0%** raw | **69.3%** clean
- Analysis profile: **Market-agnostic horse analysis**

## Condition Breakdown (Clean Sample)

| Condition | Races | Horses | Model@1 | Model@Top3 | Top3 Precision | Fav@1 | Fav@Top3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Good/Firm | 215 | 2316 | 19.5% | 49.8% | 42.5% | 35.8% | 71.6% |
| Soft | 59 | 707 | 11.9% | 45.8% | 40.7% | 33.9% | 62.7% |
| Heavy | 29 | 301 | 20.7% | 51.7% | 44.8% | 44.8% | 65.5% |

## Section Diagnostics

| Section | Current | Suggested | Delta | Pairwise | Winner@1 | Winner@Top3 | Top3 Precision | Winner Lift | Spread |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 狀態與穩定性 | 0.16 | 0.18 | +0.02 | 0.576 | 17.8% | 47.2% | 40.2% | 3.11 | 6.74 |
| 賽績線 | 0.18 | 0.18 | -0.00 | 0.575 | 17.2% | 47.2% | 40.5% | 1.62 | 3.92 |
| 段速與引擎 | 0.16 | 0.16 | +0.00 | 0.564 | 17.8% | 42.9% | 37.6% | 0.88 | 2.29 |
| 騎練訊號 | 0.16 | 0.15 | -0.01 | 0.557 | 12.9% | 42.6% | 36.7% | 1.42 | 4.30 |
| 級數與負重 | 0.12 | 0.11 | -0.01 | 0.519 | 11.9% | 33.0% | 32.0% | 0.53 | 5.76 |
| 形勢與走位 | 0.12 | 0.11 | -0.01 | 0.522 | 12.5% | 31.0% | 32.1% | 0.35 | 3.44 |
| 場地適性 | 0.10 | 0.11 | +0.01 | 0.519 | 10.9% | 32.0% | 30.0% | 0.35 | 4.36 |

## What To Raise

- No section cleared the under-weight threshold in this pass.

## What To Trim

- No section cleared the over-weight threshold in this pass.

## Blind Spots

- `賽績線` still lacks discrimination: score spread only 3.92.
- `段速與引擎` still lacks discrimination: score spread only 2.29.
- `級數與負重` still lacks discrimination: pairwise only 0.519.
- `形勢與走位` still lacks discrimination: pairwise only 0.522 and score spread only 3.44.
- `場地適性` still lacks discrimination: pairwise only 0.519.

## Coverage Gaps

- `sectional trend missing` observed **262** times in scanned archive horses.
- `formline missing` observed **125** times in scanned archive horses.
- `historical result gap races` observed **12** times in scanned archive horses.

## Interpretation

- `Pairwise` 越高，代表該 section 單獨拿出來排 horses 時，越能跟實際名次方向對上。
- `Winner@1` 代表該 section 自己的第一名直接中頭馬的比例。
- `Winner@Top3` 代表該 section 的 top-3 至少包住頭馬。
- `Top3 Precision` 代表該 section 揀出的 top-3，有幾多最終真係跑入前三。
- `Winner Lift` 代表頭馬在該 section 分數平均比全場高幾多分。
- `Spread` 太低通常代表該 section 太平，對排序幫助有限。

