# AU Wong Choi — Top 2 各 $1 @ Racenet Odds 策略測試

## 結論先行

- 呢個方向值得做 forward test，但現有證據唔支持即時實盤盲買所有場。
- 直接 Racenet SP 樣本：34 場、68 注，P&L -0.35 units，ROI -0.5%。
- 大樣本 pre-play WAP proxy：708 場，ROI -4.2%；早段 morning WAP 則為 -31.2%。
- 真正關鍵係取得分析發布一刻嘅 Racenet odds，並持續量度相對 SP 嘅 CLV。

## 價格口徑

| 價格 | 場次 | 冠軍在 Top 2 | P&L | ROI | 95% CI |
|---|---:|---:|---:|---:|---:|
| Betfair morning WAP（早盤 proxy） | 708 | 39.0% | -441.62 | -31.2% | [-39.4%, -22.5%] |
| Betfair pre-play WAP（近開跑 proxy） | 708 | 39.0% | -58.71 | -4.2% | [-17.5%, +11.1%] |
| Betfair BSP（5% commission） | 707 | 38.9% | +108.58 | +7.7% | [-9.5%, +28.2%] |
| Racenet result SP（直接、細樣本） | 34 | 41.2% | -0.35 | -0.5% | [-48.6%, +61.8%] |

Racenet result SP 係收市／賽果價格，唔證明分析發布一刻可以買到同一價格。

## 價格要求

| 樣本 | 命中場次平均勝馬價 | 打和所需平均勝馬價 | 差額 |
|---|---:|---:|---:|
| 歷史 pre-play WAP | 4.918 | 5.130 | -0.212 |
| 最近 Racenet SP | 4.832 | 4.857 | -0.025 |

## Racenet SP 分場

| 場地 | 場次 | 命中 | P&L | ROI |
|---|---:|---:|---:|---:|
| Caulfield | 8 | 7 | +11.80 | +73.8% |
| Eagle Farm | 9 | 2 | +2.60 | +14.4% |
| Randwick | 10 | 3 | -5.30 | -26.5% |
| Warwick Farm | 7 | 2 | -9.45 | -67.5% |

## 簡單 price gates（只作診斷）

| Gate | 歷史 pre-play WAP ROI | Racenet SP ROI | 判斷 |
|---|---:|---:|---|
| 兩匹都 ≥ $4 | +4.8% (308場) | -35.0% (17場) | 未通過跨樣本穩定性 |
| 兩匹 implied probability 合計 ≤ 35% | +0.2% (283場) | +16.4% (18場) | 未通過跨樣本穩定性 |
| #1 ≥ $3 且 #2 ≥ $4 | +1.5% (404場) | +3.4% (22場) | 未通過跨樣本穩定性 |

冇一個簡單 price gate 同時喺大樣本時序分段及最新 Racenet 樣本穩定勝出；
因此唔應該由呢 34 場反推門檻。

## 建議 forward protocol

1. 模型繼續 odds-blind 排名；每場固定記錄 #1、#2。
2. 分析發布時保存 Racenet decimal odds、bookmaker、timestamp。
3. Paper bet：#1、#2 各 $1 WIN；唔用賽後 SP 回填作買入價。
4. 賽後保存 Racenet SP，計每注 CLV、P&L、最大回撤。
5. 50 場只做 checkpoint；100 場先決定正式啟用或加 price gate。

Accountant 狀態：repo 冇 betting_record.md，因此按 failure protocol 視為審慎模式；
本報告只批准 paper test，唔批准實盤放大注碼。
