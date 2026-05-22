# AU Engine Version Comparison

- Sample races: **136**
- Sample horses: **986**
- Legacy engine: **Legacy/Mainline**
- Trial engine: **SIP-AU-V22 / Shadow**

## Recommended Scoreboard

| 指標 | 原始 (Legacy/Mainline) | 優化後 (SIP-AU-V22 / Shadow) | 改善幅度 |
|---|---:|---:|---:|
| 🏆 Gold (3/3) | 1.5% | 1.5% | +0.0pp |
| ✅ Good (Top1+Top2 入前三) | 5.9% | 5.9% | +0.0pp |
| ⚠️ Pass (2/3) | 21.3% | 19.9% | -1.5pp |
| 🥇 Champion | 14.7% | 13.2% | -1.5pp |

## Metric Crosswalk

| 指標 | Legacy/Mainline | SIP-AU-V22 / Shadow | 改善幅度 |
|---|---:|---:|---:|
| Top3 Contains Winner | 33.1% | 34.6% | +1.5pp |
| Top3 Place Precision | 30.1% | 30.6% | +0.5pp |
| 0-hit | 32.4% | 29.4% | -2.9pp |

## Notes

- `Good` 固定指 Top 1 + Top 2 picks 同時跑入實際前三。
- `Pass (2/3)` 指 Top 3 picks 入面至少 2 隻跑入實際前三。
- 如果之後要用 `SIP-AU-V22` 做正式發布，建議先決定官方到底用邊個 Good 定義，避免報告同實驗表口徑打架。

