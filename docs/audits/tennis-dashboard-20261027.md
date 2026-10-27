# Tennis dashboard：NBA 版式與完整投注追蹤（2026-10-27）

## 交付範圍

Tennis 沿用 NBA 工作台嘅視覺層次：頁首、今日投注／歷史投注／賽前分析／實際投注四分頁、摘要數字、累積模擬盈虧、結算進度同投注卡片；保留 Tennis 綠色識別。手機版可直接搜尋、按類型／結果／時段篩選，每次載入50筆，完整清單仍可繼續載入。所選頁籤與篩選條件可保存網址書籤。

## 完整性與資料來源

- 新增唯讀 `tennis_tracking.py`：匯出全部 value prop、全部組合層級、CLV紀錄、未有CLV鏡像嘅BET市場紀錄及最新BET勝負參考單。按來源ID去重prop／CLV鏡像，沒有頭2注／頭1組合顯示上限。
- 本機live DB實讀 **14,079筆模型紀錄**；這不是實際落注數。原本正式建議門檻、單場限制及展示額度完全不改；完整追蹤屬獨立觀察資料，不代表已放行。
- 使用 source `result_status`／P&L，不重新預測賽果。每筆$1模擬按已儲存建議注碼正規化；未有可核實賽前時間、爭議身份、未有價、未結算紀錄仍顯示，但不計ROI；作廢不計已結算注碼。賽程有aware開始時間時，以悉尼日期顯示。
- Dashboard實際投注仍由D1／既有本機ledger提供；完整API沒有新增limit。CLI記錄嘅`prop_live_bets`另作唯讀實際投注展示，與模型追蹤分開，按明確來源ID避免重複；實際投注不匯出模型模擬盈虧，避免不同落注價被混用。沒有自動新增、修改或結算任何真實投注。
- ledger短暫讀取失敗保留已載入雲端紀錄，包括已確認為空嘅清單，不會被舊local資料覆蓋。首次離線時明示雲端紀錄可能未齊。
- 其他domain發佈或局部日期來源不會清空已保存Tennis追蹤；保留記錄標示stale，當日本機覆蓋範圍仍具權威。
- 實際報價來源保持Sportsbet；沒有更改模型權重、下注額或策略放行條件。

## 發佈連動

已確認各domain排程會由自己checkout重新發佈dashboard。只部署一次HTML、卻不更新排程所用模板／exporter，下一次排程可覆蓋新版。因此activation plan遇到dashboard code改動時，同步四個自動發佈者checkout，再執行原有dashboard部署及驗證；加入對應政策測試。沒有新增排程或更改模型。

## 驗證

- 前端Node 108個測試通過；涵蓋65筆分頁、載入更多、搜尋、中文盤口索引／輸入法保護、來源失聯不偽裝零回報、書籤、PIT／無價／作廢ROI、來源文字escaping、ledger失聯保留與空雲端防舊資料復活，以及native已落注記錄。
- 新增10個Python測試通過：全部單注／組合、悉尼跨日、晚寫／爭議／缺時間、CLV去重、native實際投注、最新NO_BET不復活舊BET、唯讀、跨domain歷史保存。既有multisport／generator測試亦通過。
- release policy 21個測試通過；dashboard-only release需要同步全部自動發佈者。
- `./檢查.sh --quick`與完整`./檢查.sh`全綠；最後immutable SHA gate及activation以Central release manifest為準。
- Headless Chromium（獨立profile、所有投注API攔截為測試回應）驗證1440px桌面及390px手機：50→100筆、搜尋／重設、頁面切換、URL還原、手機無橫向溢出；無pageerror。
- 最後預覽HTML約18.5MB，低於現有Cloudflare單檔閘；沒有縮小模型清單救體積。
- 預覽及截圖：`/private/tmp/tennis-dashboard-preview/`。預覽使用現有正式snapshot保留NBA／HKJC／AU資料，只替換Tennis及模板；沒有全語料rescan。
