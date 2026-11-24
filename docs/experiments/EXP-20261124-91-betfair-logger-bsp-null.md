# EXP-20261124-91 Betfair 記錄器 BSP 一直係 null —— 修正＋補返 11-06 起

- 日期：2026-11-24　平台：AU　類型：數據管線修正（唔郁模型、唔郁注單）
- 起因：做市場尺（EXP-20261124-90）嗰陣發現，`au_betfair_logger.py settle` 由 11-06 到 11-23，18 晚、約 1.6 萬匹嘅 `bsp` 全部係 null。
  因為冇嘢讀呢個欄位，所以一直冇報錯。Kelvin「修 BSP 記錄器」。

## 原因（真 API 驗證）
`listMarketBook` 嘅 `priceProjection.priceData` 只放咗 `["SP_TRADED"]`。實測：
- 淨係 `SP_TRADED`：runner 冇 `sp` 欄 → `actualSP` 永遠攞唔到。
- 加 `SP_AVAILABLE`（或者淨係用佢）：有 `sp.actualSP`，收市好多日之後都仲攞到（11-06、11-12、11-20 抽樣全部有）。
- 退出馬嘅 `actualSP` 係字串 `"NaN"`。
單元測試一直綠，係因為個假 rpc 淨係用 `SP_TRADED` 都照回 `actualSP`，同真 API 唔一樣（同記憶「mock 遮住真 arity」同一個形狀）。

## 改咗乜
- `SETTLE_PRICE_DATA = ["SP_AVAILABLE"]`（weight 3 × 25 = 75，冇超過 200 上限）。
- `actual_sp()`：`"NaN"`、None、≤1 → None。
- 重新結算：結算行入面有跑嘅馬全部冇 BSP，就當未結算再問一次（新行 append）；`latest_settle()` 讀最後一行。
  `collect_counts`／`status` 改用最後一行，並加 `settled_markets`、`settled_markets_with_bsp`。
- 防線：每晚結算後 `check_bsp_present()`，當晚結算咗但冇一個市場有 BSP 就推 primary Telegram。
- 測試個假 rpc 改成同真 API 一樣（淨係 `SP_AVAILABLE` 先有 `sp`，退出馬 `"NaN"`）；加重新結算同警號測試。

## 驗證
- 沙盒（抄 11-20 目錄）用真 API 重新結算：133/133 個市場有 BSP。
- 上線後用 `settle --date` 逐日補返 11-06 → 11-23（排程只回補 7 日）。
