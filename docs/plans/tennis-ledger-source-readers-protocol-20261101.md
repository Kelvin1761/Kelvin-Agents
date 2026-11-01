# Tennis remaining ledger source consumers — fixed protocol

2026-11-01；在更改餘下三條路徑之前鎖定。屬來源正確性工作，不是獨立盲測、準確率提升或投注策略 promotion。

## 輸入及範圍

基線研究分支 `320442e2`，已包括 origin/main 的 fixture quarantine 及第一組來源 guard。完整凍結備份沿用 SHA-256 `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`（2026-10-29 as-of）。較新的 live rows 不在這個固定比較內；不能把快照當成 live DB。

工作副本放已掛載的 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/ledger-source-guard-v1/`。先檢查掛載、內置碟至少 10GB。全部 matches、odds_snapshots、preclose_odds_snapshots、market_odds_snapshots、preclose_market_odds_snapshots、market_captures、closing_odds_snapshots、clv_tracker、prop_tracker、prop_price_log，以及所有引用的 raw receipts 都保留；任何 native function 需要的額外表亦完整保存。逐表全部欄位、ID 順序、行數及 SHA 對照原始快照，不按結果或已知錯來源篩選。若使用 archived body，須保存必要 refs/blobs 並經 accessor 驗證。

## 三個獨立候選

1. `fetch_closing_odds_for_date`：先用原本排序選最後賽前 snapshot，再驗證來源；扣起時寫有原因的 NO_CLOSE，不能用較早／較後價補位。若為 NO_CLOSE，仍保存可追溯的被拒來源證據，不能把無效來源標成可用 close。
2. `_tracker_close` 非 match-winner 分支：market union 必須帶 raw_response_id，按原身份及時間規則選一行後檢查；錯來源返回 None 及明確原因，不補位。
3. `_log_prop_prices`：原先的 earliest 和 latest 各自選完再檢查；兩者可獨立失效，保留有效一邊。原始快照數量和有效來源數量分清楚，不能只因有兩行而聲稱有兩個有效 pre-start observations。無 close 時不計 CLV；price log 不反向改投注策略。

共用直接 Sportsbet URL event ID 判斷須保持與已保存 9,988 回應的 9,689／299 決定一致。matched ID 不是身份／PIT 全面認證；範圍外、缺 receipt 或 namespace 未確認的來源須另報，不能計入已驗證樣本。

## 比較及判決

在任何 model code 修改之前保存確切命令、基線檔案 hash、輸入表指紋及 native 行為。全部日期／tracker／prop 都跑，不能只跑已知三個錯 event tracker。writer 寫入只准用工作副本；若為隔離 writer 而停用其他 settlement side effects，須在報告明示並另做原生整合測試。

三個 guard 分別跑及組合，八個 arm（baseline、每個單獨、每兩個、全部）固定；記錄來源分類、逐行 before/after、NULL／原因、缺失與保留覆蓋、原始及工作副本 hash。所有未被扣起的報價／時間／身份必須逐欄相同，不應出現新補位價格。任何未預期改價或其他現役行為回歸都先停下調查。

測試需涵蓋：錯 first 後有 valid later、錯 last 前有 valid earlier、同時間 ID/preclose tie-break、缺 start time、body 缺失／損壞／archived、同 ID 但名字爭議不解除、不同 provider／namespace 明示未驗證、NO_CLOSE 重跑冪等。按 repo 規則跑 quick/full gate。

這些比較不使用賽果或 ROI 擇參，不變更原本十五個 REJECT_DEV、不改 frozen ruler、不打開或調整 holdout。完成全部讀取器資格核對後，另行核對受影響模型研究的完整依賴及語料，按原命令重跑；新的準確率候選須另有預先登記及獨立驗證。其他莊家歷史資料仍只按既定 training/research 合約使用，未知報價時鐘的 ROI 不視為可執行回報。
