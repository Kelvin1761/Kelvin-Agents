# EXP-20261125-03 NBA 歸檔搬走預測快照 → research-review 由 10-21 起日日 failed（修正）

- 日期：2026-11-25　平台：NBA　類型：數據管線修正（唔郁模型、唔郁注單、唔郁 dashboard 顯示）
- 起因：系統升級第 4 項（`job_freshness.py`）第一次跑就標 `central-wong-choi.research-review` ❌；Kelvin「can you fix them all?」。

## 原因（逐步核實）
1. research-review NBA 狀態 `review_cursor_verification_failed`，真正例外係 `NBA monitoring sample report differs from source evidence`
   （`research_nba_monitoring_samples.py:399`；`research_review_cursor.py` 嘅 blanket except 吞咗訊息）。
2. 封印咗嘅 10-21 報告同重砌嘅只差三個子報告 hash；重砌時 10-21 嗰兩個 prediction record 嘅 17 個 artifact 全部 `unavailable`。
3. 證據記錄（`evidence/records/prediction/*`）用絕對路徑 `/Users/imac/wongchoi-scheduler/<日期> NBA Analysis/_prediction_snapshots/...`
   ＋sha256。`nba_daily_review_archive._archive` 賽後用 `shutil.move` 成個資料夾搬去 `~/WongChoiData/Wong Choi NBA Analysis/` →
   **每一日**嘅證據路徑都斷（10-21 → 11-24，5,651 個檔）。即係就算修好 10-21，之後每日都會再壞。

## 修正
- `_archive`：`_prediction_snapshots` **抄**去歸檔、原位留低；其他照搬。
- 「證據殼」= live 位置淨係剩 `_prediction_snapshots`（＋.DS_Store）**而且嗰日已經有歸檔**。`nba_daily_schedule.is_live()`、
  歸檔腳本 `_is_live()` 都唔當佢係 live —— 否則 7 日 catch-up 會對已歸檔日子重跑 postgame。
  **Dashboard 唔改**：exporter 本身會由快照還原已發佈分析（`test_nba_published_analysis`），淨係快照嘅資料夾對佢有用；
  tracking 連殼／冇殼輸出逐字一樣。
  冇歸檔嘅（快照寫咗、報告未出）照舊當 live，現有 424 個 schedule 測試唔變。
- 一次性還原：由歸檔逐 byte 抄返 5,651 個 artifact 去記錄路徑，每個核 sha256（0 個對唔上）；1 個指去系統 tmp 嘅測試殘留冇得還原
  （10-21 封印時已經係 unavailable，唔影響）。11-13 → 11-24 嘅殼喺 guard 上線前暫存喺 `WongChoiControl/nba-restored-snapshots-holding/`，
  上線後放返。

## 驗證
- 還原 10-21 後唯讀重驗：NBA cursor `state`／`sample`／`storage`／`liveness` 全部 OK（之前 state＋sample 拋例外）。
- Dashboard NBA tracking（連殼 vs 冇殼）：205 records／79 featured，逐字一樣。
- 新測試：歸檔保留證據 bytes、殼唔算 live、未歸檔照舊 live。

## 未做
- 網球 research-review（11-15 起）：128KB 報告上限，要搬去分頁 runtime（AU／HKJC 已經用緊）—— 另一個改動。
