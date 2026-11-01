# EXP-20261101-20：Tennis 歷史市場與 close 來源讀取

狀態：來源正確性評估；不構成準確率、盈利或模型 promotion 證據。

## 固定資料及方法

基線 `b18fe7b9b3a6b57f7667877ad430f70c692d1095`；2026-10-30 預先保存協議，2026-11-01 完成接續重播。原始完整 SQLite 備份 SHA-256：`fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`。已知來源缺陷後鎖定的 correctness 比較，並非獨立盲測。

證據目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/event-response-identity-20261030/historical-reader-guard-v1/`。保留 `protocol.json`、補充協議、baseline/candidate source、重播程式及逐行 gzip traces。原始副本隨機讀取太慢的三次未完成嘗試分別保存；工作副本只加入查詢索引。逐表對照所有欄位及 ID 順序 SHA，完整複製 9,974 matches、250,982 market snapshots、714 captures、111,464 closing snapshots，以及它們引用的 9,193 raw responses。無保留 payload archive 表的原始事實亦保持。此副本沒有抽選日期、結果或價錢。

重播所有 124 個有市場資料日期，以及 6,585 個有 stored close 的 match ID。基線及候選使用同一工作副本；保留 baseline SQL 選價，再檢查所選 row 的來源。開盤仍為原 `MIN(id)`，錯來源不會令較後價補位；close 仍先選原本最新賽前價，錯來源不會改用更早價。

## 結果

| 讀取模式 | 基線返回 | 候選返回 | 扣起 | 涉及 match |
|---|---:|---:|---:|---:|
| earliest market | 84,014 行 | 83,126 行 | 888 行 | 84 |
| current market | 77,721 行 | 76,833 行 | 888 行 | 84 |
| match winner close | 4,999 場 | 4,895 場 | 104 場 | 104 |

開盤模式 81 場失去全部所選市場行；current 模式 84 場。所有保留行逐欄與基線相同，沒有替代報價。close 基線 1,586 場無返回，候選 1,690 場無返回。候選保留的 4,895 close 中，4,817 直接 URL event ID 相符，78 個來源在本次直接 event 檢查範圍外，不能聲稱已驗證。

預先鎖定四 arm 的（開盤行數，close 場數）：baseline `(84014,4999)`、僅 market guard `(83126,4999)`、僅 close guard `(84014,4895)`、兩者 `(83126,4895)`。兩個獨立讀取器的結果分開量度；沒有用賽果或 ROI 擇參。

共用 event ID helper 亦重播之前全部 9,988 份接收回應，9,689 接受／299 拒絕，與已上線入口完全一致。針對性測試 48 passed；完整獲授權 `./檢查.sh` 全部 suite 通過，Tennis 986 passed。第一次受限環境因既有 `.agents` cache 寫入權限失敗的紀錄保留，不當作通過。

## 限制及下一步

- helper 只驗證 Sportsbet 直接數字 event URL 的回應 ID；ID 相符不能證明球員、發布時鐘或整份資料 PIT 合格。
- 缺 receipt／不支援 namespace 仍明示未驗證，保留原操作行為；可辨識 event request 的缺失／損壞 body 則扣起。其他 provider／endpoint 屬範圍外。
- 未改寫或刪除 live 歷史資料，未解除 42 個舊錯誤隔離或兩個同 ID 姓名爭議。
- `fetch_closing_odds_for_date` writer、非 match-winner `_tracker_close`、`_log_prop_prices` 及其他模型／報告讀取器仍須獨立驗證；之前追蹤到的三行非 match-winner CLV 不能宣稱已修復。
- 舊十五個 REJECT_DEV 不變。完成其他受影響讀取器與來源資格核對後，才可重跑受影響的研究；不得用補位賠率、未證實身份、或未知時鐘 ROI 當準確率／盈利證據。

最終 `result.json` SHA-256：`1ce1bd538af3f619b13e8ba270e41b03e90db4922f5e640f66bebc2b0e66aad4`；完整原始 DB 與索引副本在重播後雜湊均保持不變。
