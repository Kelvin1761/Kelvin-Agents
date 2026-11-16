# EXP-20261116-23 — Tennis：Sportsbet 對 Betfair 即時價，紙上前向測試（預先登記）

- 編號：原本用 -18、-19，兩個都同 HKJC／AU 同日撞號，2026-11-17 改做 -23（第一個決定之前；規則冇改）。
- 日期：2026-11-16（喺第一注之前鎖定）；平台：Tennis；類型：**紙上前向測試**（唔落真錢、唔發 card、唔改精選）。
- 背景：EXP-20261116-15 用 Betfair **收市價**量到 Sportsbet 約 9% 嘅邊有正 EV（平均 +4.6%），但收市落注嗰刻唔知，
  holdout 59 注 −3.9% INCONCLUSIVE。Kelvin 已經有 Betfair AU 帳戶（AU 記錄器用緊，只讀，delayed key），所以而家可以
  喺落注一刻同 sharp 價比。
- Kelvin 問「會唔會一路換注？ROI 點計？」：**唔會**。每場最多一個決定，喺下面嘅決定時間做一次就凍結，之後價點郁都唔改。
  ROI 只計呢批凍結注。

## 數據

- Betfair：`scripts/tennis_betfair_tick.py`，每 15 分鐘（:00 :15 :30 :45 悉尼）抓未來 36 個鐘所有網球 `MATCH_ODDS`
  單打盤（`listMarketCatalogue`＋`listMarketBook` EX_BEST_OFFERS，delayed key 價延遲 1–180 秒）。表
  `betfair_markets`、`betfair_price_snapshots`（價冇變就只更新 `last_seen_at`，唔加行）。
- Sportsbet：現有 `odds_snapshots`（`match_winner`）。

## 決定規則（一場一次，凍結）

1. 決定時間：每場第一個喺**悉尼 20:45–22:30** 抓到、而且早過開賽 5 分鐘以上嘅 Sportsbet 獨贏快照（即係 21:00 card 嗰輪）。
   冇呢個快照嘅場唔入測試。
2. 對應 Betfair 盤：開賽時間相差 ≤ 6 個鐘，兩個球員名都對得上（`name_matching.match_pair_score`），而且只得一個候選。
3. Betfair 價：決定時間 ±20 分鐘內嘅快照（價喺嗰刻仍然有效）；兩邊都要有 back 同 lay，而且 lay/back ≤ 1.10。
   每邊 mid = (back+lay)/2，p = (1/mid) 按兩邊比例正規化。
4. EV = Sportsbet 價 × p_Betfair − 1。揀 EV 大嗰邊；**EV > 0 就落 1 單位（紙上）**，否則記錄做「唔落」（分母用）。
5. 寫入 `sharp_forward_picks`（UNIQUE match_id），之後永遠唔改。

## 結算

`match_results` 嘅勝方（所有來源一致先結算；唔一致或者冇賽果就等）。退賽照勝方結算（同 Sportsbet 一盤完成先算嘅規則
可能有出入，記低做已知限制）。

## 判決（夠數 Telegram 推 Kelvin，primary）

- 300 注：中期檢查，只報唔判（除非 CI 全負 → REJECT）。
- 1,000 注：ROI 95% bootstrap CI（按注，4000 次，seed 20260826）下限 > 0 → ELIGIBLE_FOR_RELEASE_REVIEW；上限 < 0 → REJECT；
  否則 NOT_PROVEN。
- 描述性（唔計判決）：EV 門檻 0.02／0.05 嘅子集；CLV = Sportsbet 價 × 開賽前最後一個 Betfair p − 1。
- 功效：真 EV +4% 要大約 2,400 注先可以 CI 下限 > 0，所以 1,000 注好可能係 NOT_PROVEN；呢個係預先講明嘅。

## 上線前實測（2026-11-16 23:08 悉尼）

一次真 Betfair 抓價：119 個單打盤。今晚 21:00 嗰輪 57 場：29 場已經開波；未開波 28 場入面 23 場係 ITF／UTR／
巴西低級別賽，Betfair 冇盤（正常，唔入測試）；1 場名字太長被截（Maristany Zuleta De Reales）→ 加咗寬鬆配對（短名每個字都喺長名、
最少兩個字、頭一個字一樣）。第一批真決定由 2026-11-17 21:00 開始。

## Code

`tennis-wong-choi/src/tennis_wc/sources/betfair_prices.py`（抓價＋去重存）、`select/sharp_forward.py`（決定、凍結、結算、判決）、
`scripts/tennis_betfair_tick.py`、`launchd/com.antigravity.tennis-wong-choi.betfair.plist.template`、
`publish/telegram.py::sharp_forward_milestone`（18:00 daily 跑）。測試 `tests/test_sharp_forward.py`。

改任何規則 = 開新 arm／新 EXP，唔准改呢份。
