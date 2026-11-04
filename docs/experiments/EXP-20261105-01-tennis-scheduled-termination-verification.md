# EXP-20261105-01 Tennis 18:00 排程終局核對

2026-11-05 Sydney 唯讀覆核。Central `fb72eca5` 於 2026-11-04 06:32:35 UTC 啟用後，正常 18:00 Sydney daily attempt 1 於 07:00:03.251 UTC 啟動，07:00:50.117 UTC 完結。Central run manifest 為 `failed`，唯一操作 `settle`，狀態 `adapter_exception:SchedulerTerminated`，操作 artifacts 0。真實排程已驗證收到中斷後可落終局。中斷來源未識別，今次 run 未完成定價。

只讀 live DB 同報告目錄所得：

- TennisExplorer 原文收據 26503 於 07:00:09 UTC 保存，HTTP 200，match_history，正文 JSON object 約 873 KB。現存連結有 414 條 ATP 同 10 條 WTA ACTIVE 履歷。
- 11 月 4 日有 11 場 ACTIVE composite fixture，全數無 start_time_utc。11 月 5 日 ACTIVE 0。呢啲係覆核時資料庫狀態。
- 11 月 4 日報告及 odds 檔係前一晚寫入，已存在嘅 prediction snapshot 目錄同樣係前一晚建立。本次 manifest 無賽前輸出。獨立 Sportsbet 合格新增 0。

LaunchAgent 現時 loaded、not running、`runs=0`。歷史 run manifest 已明確有啟動記錄，現存 launchd counter 唔可以代替歷史 run 狀態。狹窄時段冇取到可識別訊號發起者嘅 launchd 記錄。前輪舊收據候選掃描嘅 process handle 已失效，無驗證結果可引用，與今次實際排程核對分開。未改模型、未回跑舊卡。下一次正常 card 睇能否完成 pregame，並保持原 forward 追蹤資格。
