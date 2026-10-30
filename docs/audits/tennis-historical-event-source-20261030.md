# Tennis 歷史 event ID 錯配：讀取器及 close 後續核對

基於 [EXP-20261030-20](../experiments/EXP-20261030-20-tennis-event-response-identity.md) 的固定 9,988 份原始回應及 299 份請求／回應 event ID 不一致來源。本次為**只讀事後診斷**，不是模型準確率、投注收益或已部署的歷史修復。新入口修正已於 `c1c354641fe9f3a89f0133626b14523e11b9eb6c` 通過完整閘並啟用，正式狀態以 immutable release manifest 為準；舊來源及所有原始 odds、close、tracker、prediction 均沒有被改寫。

## 固定案例及影響

- 受影響的 113 份一般 match-winner odds receipt 和 104 份 preclose odds receipt，一共曾形成 1,398 行 `closing_odds_snapshots`，涉及 217 場。按每場最新 stored close：113 行 close status 為空、104 行標為 `PRE_START`；這些行的 raw ID 都指向已知不同 event 的 receipt。
- 對相同 217 場直接執行 native `_match_winner_close`：113 場返回無 close，104 場返回錯 event 來源的 close。完整 match／close 輸入與逐場選擇保存在外置 `event-response-identity-20261030/native-close-reader-v1/`。
- 在隔離 SQLite 上以相同輸入重現原生選擇，模擬不採用已知錯 event 的 close：104 場變成未知，其餘 113 場仍為未知；**零個改採另一個價格**。逐案及 SHA 保存在 `close-mask-simulation-v1/`。這只係候選行為，尚未修改正式讀取器。
- 217 場同時有 17 行 CLV tracker、102 行 prop price log、146 行 prop tracker 及 884 行 prediction；這些是 match-level 連結，不是受污染注單數。再對 104 場已確認現役 match-winner close 取錯來源的場次追蹤：4 行 CLV tracker 當中，按現役 `_tracker_close` 有 3 行選中錯 event 來源、1 行選中其他來源；3 行保存值亦與現時讀取值相同，但舊 tracker 沒有 source raw ID，不能據此證明當年唯一 lineage 或損益。102 行 prop price log 依相同 feed market／selection／line 及賽前時間條件重現，現時首價及 close 均來自其他來源，保存 close 的數值和時間亦與現時結果一致；同樣不能單憑此保證其來源已完整驗證。逐行證據保存在 `clv-source-trace-v1/` 及 `prop-price-source-trace-v1/`。
- 原生 `_rows_for_date(..., earliest_only=True)` 在所有五個相關賽日讀出 3,002 行，其中 888 行／84 場連到錯 event。保留原 `MIN(id)` 後排除這些行的離線模擬，保留 2,114 行；84 場中 81 場沒有剩餘 market 行。沒有以後價補開盤。逐行原始及模擬結果分別在 `historical-reader-audit-v1/` 和 `historical-earliest-mask-simulation-v1/`。保留的 2,114 行只是沒有此已知錯配，並不自動符合賽前、身份或結算要求。

## 42 宗 fixture 的來源脈絡

固定原有 44 宗衝突中的 42 宗（10 月 28／29 日）現仍為 `DISPUTED`。只讀逐宗核對：42 宗原始 Sportsbet listing 均包含唯一相同 event ID 及原有完整球員組合；亦各自找到在衝突前、完整 JSON 一致的另一 event 回應。初版用 10 秒時間窗只找到 40／42；補充比對改用完整回應 JSON 一致及先後時間，找到 42／42；兩版原始資料及限制均保存於 `fixture-provenance-audit-v1/`。同一 provider 的列表和 event 回應並非獨立身份證明；尚未解除任何隔離，也未確認賽事可用於 point-in-time 訓練。

## 後續安全處理

1. 統一驗證原始 receipt 的請求／回應 event ID，保留可讀原文、時間及明確的 mismatch／missing／unsupported 狀態；其他 ID namespace 不猜轉換。已知錯 event 不進價錢與 close。archive 原文必須用無損 accessor；缺失或過大要明確 fail closed，不能截短。
2. 原有 earliest `MIN(id)` 先按現行完整群體選出，再檢查該行來源；錯誤就標缺失，**不**挑後一行冒充開盤。Close 只用有證據的 pre-start 來源；若原本選中錯來源，標未知，不把較早 quote 宣稱為 close。
3. 分開檢查 live card、歷史 props、match winner、preclose、已物化 close、tracker／研究 evaluator 等全部消費者；修讀取器不代表已清除歷史 tracker，也不代表既有實驗有效或無效。每一路保留完整 row-flow、缺值及原始 source。
4. 每項修正用相同凍結語料逐行配對，比對無錯來源不變、錯來源不被使用、名稱／event 重用及空來源反例；針對多個讀取路徑分別做 ablation。任何時間與 source 未證實的資料不提升為 PIT 或 forward。修復 42 個 fixture 須另行完整備份、驗證及逐項 exact plan。
