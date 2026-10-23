# NBA 審核修正第一批：F04／F10／F12

起點 `2a6695e9`；總目標仍係修正 F04–F12，本批唔代表其他六項已完成。

## 修正內容

- **F04**：傷停／陣容有獨立 verified contract、完整名單指紋及 UTC 來源時間。
  30 分鐘係配合排程嘅固定營運時限，唔係調出嚟嘅模型參數。快資料過期只刷新
  ESPN 名單／傷停，唔重抓全部 L10；名單改變或舊 cache 冇來源指紋先重建歷史包。
  網絡／HTTP／缺名單／含糊身份／缺傷停狀態一律唔當健康。失敗保留原 JSON 同報告，
  唔發布；已開賽唔讀新傷停亦唔覆寫賽前資料。寫檔採 atomic replace。
- **F10**：C 層機率帶版本＋係數／clip SHA-256 身份，傳入 sidecar 同 append-only
  market ledger。Evaluator 先選實際最新賽前 observation，再按身份分組，避免
  篩選版本後倒退揀舊快照。Reliability 只用現役身份；legacy、其他係數、未知身份
  仍保留背景結果同排除數。冇補造舊資料身份，亦冇改歷史 ledger。
- **F12**：區分刻意 disabled 同設定損壞／讀檔失敗。缺版本、缺 stat、非法 clip、
  非有限係數均拒絕；報告 CLI 在讀輸入前核對設定。壞設定唔再靜默退 legacy。
  明確 `NBA_WC_PROB_LAYER=0`／`enabled=false` 保留原功能，監察會顯示 disabled。

機率公式及係數冇改；sigmoid 用穩定計法避免極端有限係數 overflow。呢批係工程
正確性修正，唔聲稱 Brier／命中／ROI 改善。資料刷新令新傷停可以影響選腿，
但唔以賽後傷停重建歷史預測；因此冇將當前傷停拿去做歷史 A/B。

## 驗證證據

- 起步 quick gate 通過；NBA 起步 351 個測試，新增案例後第一輪 388、加刷新接線後
  390 個測試通過，最終數量以本批 full gate 為準。
- 合成案例覆蓋：30 分鐘邊界／未來時間、健康空傷停名單、網絡／HTTP 失敗、缺名單／
  身份撞名／缺狀態、只換快資料而歷史不變、名單改變要求重抽、已開賽不讀來源、
  刷新失敗原檔逐 byte 不變，以及舊報告唔可因刷新失敗而重用。
- 身份案例覆蓋：同日舊係數、缺身份嘅 calibrated 標籤、最新快照改用 legacy 時
  唔倒退揀之前嘅 C 快照、係數變更與純註解變更，以及 disabled 狀態。
- 設定案例覆蓋：缺檔、JSON 錯誤、錯誤 schema、NaN／Inf、clip、恢復重試、
  CLI 發佈阻擋；獨立公式測試仍通過。
- **真實來源唯讀 smoke（2026-10-23 06:08 UTC）**：ESPN BOS 回 17 個陣容身份／
  1 項傷停，GSW 回 18 個身份／5 項傷停（Out／Day-To-Day）；兩個回應均通過新 parser。
  只讀來源，冇生成 live 預測或覆寫任何生產資料。
- **真實 ledger 唯讀**：23 日 evaluator 選中嘅 579 條 unversioned calibrated 同
  3 條 legacy 均唔冒充有完整係數身份嘅現役樣本；現役統計回 insufficient_n。
  全世代背景仍保留 3,331 條已結算腿，冇藉刪資料令指標變好。

## 下一批所需語料

本機 local NBA archive 只有 21／22 日。原 Google Drive File Provider 路徑
即使提高 shell 權限仍拒絕讀取，已改用 Google Drive connector，找到原 archive
33 個直接項目（含 32 個目錄）及 12,753,138-byte 舊 ML dataset。Catalog audit
已知 1 個 reflector DB 可由已驗證 WARM 讀取，冇 unresolved artifact；呢個唔等於
所有舊預測已經核對完整。後續要逐項清點及驗證，唔准縮細成兩日本機語料。

## 發佈與剩餘工作

本批以 exact-scope `保存.sh` 對固定候選 SHA 跑完整 gate，成功先 merge／activate；
實際狀態以 Central immutable manifest 為準。總目標保持 active。
F05（實價）、F06（訓練／評估）、F07／F08／F09（模型接線／來源）同
F11（真實規則／機率／注碼描述）仍要繼續做，唔係被本批取代。
