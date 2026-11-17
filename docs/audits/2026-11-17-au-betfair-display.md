# AU dashboard：Betfair 價做細灰字顯示（2026-11-17）

Kelvin：「primarily use sportsbet odds as ROI and dashboard display, but start seeing if we can display the betfair odds
probably bottom of the box in a smaller grey text that is not editable」。

- **核實**：main 上 AU ROI（`au_betting`、`wongchoi_roi`）同 dashboard 賠率由頭到尾都係 Sportsbet；Betfair 策略研究
  （EXP-20261116-25）同自動落注模組只喺分支。所以「轉返 Sportsbet」唔使改。
- **新**：排程喺 22:00 分析同朝早覆核影 Sportsbet 賠率嗰兩個位，順手用 Betfair（只讀，`au_betfair/au_betfair_prices.py`）
  影最佳買入價 → 場次資料夾 `betfair_odds_history.json`（追加、按馬名）。dashboard `enrich_betfair_odds` 貼
  `betfair_win_odds/betfair_place_odds`；落注格最底一行細灰字 `Betfair 贏 $x · 位 $y · HH:MM`，唔預填、唔入 ROI、唔入評分。
- **對馬**：Betfair AU `runnerName` 冇馬號，唔帶 description 時市場名亦冇場次號 → 同場地同日按馬名對；場地前綴配對
  （Sandown ↔ Sandown Lakeside）要唯一；同名兩場唔貼。
- **部署指紋**：加入每場「有 Sportsbet 價／有 Betfair 價」嘅馬匹數（唔係價錢）。2026-11-17 早上冇位置價嘅 dashboard
  修好後冇再發佈，就係因為指紋只睇排名。
- **已知限制**：2026-11-17 19:00 起 Betfair `listMarketCatalogue` 加任何 description 投影都 `UNEXPECTED_ERROR`
  （60 秒記錄器一樣），所以上線時未能實測真數據；失敗只會記 `betfair-prices skipped`，Sportsbet 唔受影響。
  前端用假數據喺本機預覽過（桌面同手機）。
