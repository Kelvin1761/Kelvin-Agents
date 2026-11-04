# EXP-20261104-15 Tennis 四組跨來源賽事官方對照

2026-11-04 06:38 UTC 研究覆核。固定沿用 [EXP-20261104-14](EXP-20261104-14-tennis-cross-provider-point-overlap.md) 嘅四個跨來源匯入 key，原證據 manifest `e6dbf1f4a0a63ef007c58f5431488d58a555a7790412046582e6fbb7cb969a61`。逐場按官方籤表階段、球員、勝方同比數確認。官方網站資料經網頁讀取，下面記錄可見數字同 URL。

| Edition / round | 官方賽事日（當地） | Sackmann 日期 / row key | TML 日期 / row key | 官方結果 |
|---|---|---|---|---|
| ATP-2026-1536 F | 05-03 | 04-22 / 369 | 05-03 / 95 | Sinner 勝 Zverev，6-1 6-2。[ATP 賽果](https://www.atptour.com/en/news/madrid-2026-results) |
| ATP-2026-580 SF | 01-30 | 01-19 / 224 | 01-30 / 125 | Alcaraz 勝 Zverev，6-4 7-6(5) 6-7(3) 6-7(4) 7-5。[澳網賽事報道](https://ausopen.com/articles/news/alcaraz-survives-zverev-longest-ao-semifinal-reach-first-final-melbourne) |
| ATP-2026-580 SF | 01-30 晚場 | 01-19 / 225 | 01-30 / 126 | Djokovic 勝 Sinner，3-6 6-3 4-6 6-4 6-4。官方報道發表於 01-31，描述星期五晚場。[澳網賽事報道](https://ausopen.com/articles/news/legend-lives-on-djokovic-stuns-sinner-returns-australian-open-final) |
| ATP-2026-580 F | 02-01 | 01-19 / 226 | 02-01 / 127 | Alcaraz 勝 Djokovic，2-6 6-2 6-3 7-5。[澳網決賽報道](https://ausopen.com/articles/news/patience-pace-precision-how-ao-2026-mens-final-was-won) |

四場官方賽事日全部同 TML 一致。馬德里官方賽果同時列 04-22 為賽事開幕日。澳網三筆 Sackmann 共享 01-19，今次證據只確認呢個值同三場實際賽事日有差別。賽事日粒度未能證實完場時刻或來源何時首次提供點數。

| 賽事 | 官方一發入／發球總分、贏一發／一發入、贏二發／二發總分（勝方在先） | 對照 |
|---|---|---|
| Madrid F | Sinner 贏一發 27/29 | 同兩來源一致，其餘欄位未獨立核實。[ATP 報道](https://www.atptour.com/en/news/sinner-zverev-madrid-2026-final) |
| AO MS601 | 121/187、89/121、41/66；149/207、106/149、31/58 | 兩側四個點數欄位全部同 Sackmann 一致。TML Zverev 記 203、146、105、31。發球局數仍待獨立驗證。[澳網官方 Match Centre](https://ausopen.com/match/2026-carlos-alcaraz-vs-alexander-zverev-ms601) |
| AO MS602 | 未讀到官方比分頁嘅完整點數欄位 | Djokovic 159/158 發球總分同 24/23 二發贏分仍未裁決。[澳網官方 Match Centre](https://ausopen.com/match/2026-novak-djokovic-vs-jannik-sinner-ms602) |
| AO MS701 | 66/101、51/66、20/35；85/123、56/85、20/38 | 兩側四個點數欄位全部同 Sackmann 一致。TML 兩側分別記 101、67、52、20 同 122、85、57、20。發球局數未獨立驗證。[澳網官方 Match Centre](https://ausopen.com/match/2026-carlos-alcaraz-vs-novak-djokovic-ms701) |

下輪研究採用逐欄來源核對。用官方賽事日輔助合併候選，用同一官方賽後版本核對雙側發球分子分母。未有可追溯完場同觀測時刻嘅欄位保持隔離。樣本係四組有重疊線索嘅比賽，未能據此為全庫設定供應商優先次序。原歷史列保留，新增合資格舊預測樣本 0，未訓練或評估準確度。
