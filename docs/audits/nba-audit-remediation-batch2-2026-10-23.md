# NBA 審核修正第二批：SGM 真實報價

起點：`0bffbeb674d32ef9cc79722c931751c35250315a`。對應原審核 F05，並處理 F11 涉及組合價格、風險／注碼同機率來源嘅部分。F06–F09 及 F11 完整規則同步仍未完成。

## 修正及證據

原本 EV、Kelly、標題及 $100 回報用單腿價格乘積，Sportsbet 另一條公開 multi-pricer 只喺事後記錄。依家選好候選後，匿名查詢同一 event／outcomes 嘅正式 SGM quote，綁定 request hash、腿 hash、quote ID、UTC 時間及五分鐘有效期。唔會落注。

真實價格唔通過組合樓底、正 EV 或正 Kelly，就移除正式組合並記錄原因。缺識別資料、來源失敗、缺 quote ID、非法數值、賽事已開始或過期都唔會用乘積冒充正式價格。長賽程完成時再檢查早段報告，過期會用快取輸入重建；compile 同 dashboard 各自重驗。renderer 的 sidecar 包含價格及報價紀錄；防火牆核對報告 hash、表格腿、價格、機率及 EV。靜態 dashboard 每次顯示及按確認時檢查到期。獨立 Banker leg 仍係該單腿價格。

同一真實價用於標題、回報、EV、Half-Kelly、匯出。風險描述採相關性調整後機率；唔再額外加一套固定 units。10-Factor 診斷同最終 calibrated 機率分開標示。結算 ROI 優先用發佈時凍結報價，後續觀察價格唔覆寫佢；舊資料保留原有參考價路徑。

合成案例：兩腿各 80%、單價各 1.8，乘積 3.24 顯示正 EV；正式報價 1.4 時 EV = -10.4%，會被剔除。報價 2.0 時 EV = +28%、Half-Kelly = 14%，報告／sidecar／dashboard 數值一致。測試亦覆蓋 event／腿改變、到期、缺價、HTTP 錯誤、非有限數值、報告／sidecar 改動、重播快取到期及凍結價格。

## 固定基準與限制

外置碟取得 228 份原始輸入／賽果，共 91,375,319 bytes，逐檔 size／SHA-256 核對，保留 Drive 來源 ID。80 份原始 game JSON 中，64 份有唯一對應盤口；16 份缺少或含糊對應，唔會靜靜刪除。immutable baseline `0bffbeb6` 實際 renderer 重播 64／64 成功，10,450 個盤口腿；原本冇任何正式組合。

基準 manifest SHA-256：`c36df013217d64882442ea6725581e681076e952911f2a980f12bad4ae270023`。詳細命令入口及資料 hash 見 `docs/experiments/patches/nba_audit_20261023/capture_replay.py` 及 `docs/audits/nba-remediation-replay-baseline-20261023.json`。外置根目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-remediation-20261023`。

舊盤口多數缺少 event_start_time／SGM outcomes IDs，亦冇歷史正式 quote。因此呢份語料只作軟件基準，唔可以回填今日傷停或捏造歷史 SGM ROI。今次證據證明價格計算及發佈邊界修正，唔證明命中率或盈利改善；冇改 C 層係數、權重或評估判決規則。未取得新賽前實價及賽果之前，相關表現仍屬未驗證。

驗證：NBA 三組測試及 dashboard exporter 最終 429 項通過；static template 80 項通過；quick gate 通過。最終全量測試及部署狀態以 exact-scope `保存.sh` 產生嘅 immutable release manifest 為準。
