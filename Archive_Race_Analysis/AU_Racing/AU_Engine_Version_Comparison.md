# AU Engine Version Comparison

- Sample races: **315**
- Sample horses: **3468**
- Legacy engine: **Legacy/Mainline**
- Trial engine: **SIP-AU-V22 / Shadow**

## Recommended Scoreboard

| 指標 | 原始 (Legacy/Mainline) | 優化後 (SIP-AU-V22 / Shadow) | 改善幅度 |
|---|---:|---:|---:|
| 🏆 Gold (3/3) | 3.2% | 4.1% | +1.0pp |
| ✅ Good (Top1+Top2 入前三) | 14.9% | 16.8% | +1.9pp |
| ⚠️ Pass (2/3) | 31.4% | 31.4% | +0.0pp |
| 🥇 Champion | 15.6% | 14.3% | -1.3pp |

## Metric Crosswalk

| 指標 | Legacy/Mainline | SIP-AU-V22 / Shadow | 改善幅度 |
|---|---:|---:|---:|
| Top3 Contains Winner | 41.9% | 42.9% | +1.0pp |
| Top3 Place Precision | 37.9% | 37.7% | -0.2pp |
| 0-hit | 21.0% | 22.5% | +1.6pp |

## Notes

- `Good` 固定指 Top 1 + Top 2 picks 同時跑入實際前三。
- `Pass (2/3)` 指 Top 3 picks 入面至少 2 隻跑入實際前三。
- 如果之後要用 `SIP-AU-V22` 做正式發布，建議先決定官方到底用邊個 Good 定義，避免報告同實驗表口徑打架。

