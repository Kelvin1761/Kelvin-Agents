# EXP-20261030-20：Sportsbet 單場回應身份核對

**狀態：資料正確性修正；未證實預測準確率或 ROI 改善。** Baseline `9b23c083de5c35a379c2bb3ac0533c603a310a0b`。此研究由已觀察到的 fixture 衝突引發，結果屬事後診斷，並非盲測或 model promotion 證據。未改模型權重、frozen ruler、下注政策或歷史原文。

## 發現與完整來源

在單一只讀 transaction 盤點當時全部 9,988 份保留的 Sportsbet `/event-odds`、`/event-odds-preclose` receipt：9,689 個直接 Sportsbet URL 的請求 ID 與回應 ID 相同，299 個不同，範圍為 2026-06-18 至 2026-10-30。所有原始 receipt、request 及回應本文，以及受影響的 odds／market rows，已凍結至外置 `WongChoi-Archive/scratch/tennis-unified-20261028/event-response-identity-20261030/`；原始 9,988 份 gzip JSONL SHA-256 `c3be8a8eaf43d90c543be42525226795ca73addcaefd0d0bf7ad49fb242edb08`。來源 ID、完整 row-flow、提取腳本及 manifest 同存。掃描時已有新 receipt 持續追加；此數字只描述固定的 9,988 個 ID。

實例：要求 Sportsbet URL 尾碼 `11101541`，收到的 JSON 卻係另一個 event `11101508`。若直接將回應球員與原有 fixture 比較，現役身份守衛會錯誤地將原 fixture 標記 `DISPUTED`；即使回應與原 fixture 姓名巧合同一，亦不能證明兩個 event 相同。

在原有 44 宗已保存的 `EVENT_PAIR_CONFLICT` 中，42 宗當時記錄的 fixture event ID 跟回應不同；另兩宗 ID 相同但球員名稱不同。新流程在保存原始回應後，先驗證明確的 Sportsbet URL 數字 ID，再交原有球員配對守衛：前 42 宗拒絕錯誤回應但不隔離原賽事；其餘兩宗保留原有 `DISPUTED` 行為，**沒有**按姓名猜測放行。直接 URL 之外的其他來源／引用不作未證實的 ID 轉換。

## 凍結對照與限制

固定完整 9,988 份 receipt，候選 ID 守衛接受 9,689 同 ID 回應、拒絕 299 不同 ID 回應。這只表示來源 ID 守衛接受／拒絕；接受後仍需通過原有賽事身份守衛。以 44 份保留原文重建隔離記憶體 SQLite、直接跑 native resolver：baseline 44 個均標爭議；candidate 42 個先因錯 event ID 拒絕而保留原狀，2 個同 ID／不同姓名仍標爭議；**44 個都沒有將不符資料放行**。逐份 receipt／逐宗 fixture 的 replay、候選 source SHA、兩份來源 SHA 同 code 留於 `replay-v3/`。`replay-v1` 因隔離 DB 未建 fixture schema 失敗，錯誤已保留；v2 補 schema，v3 再鎖定兩份輸入。

`ingest_event_odds` 保留完整 HTTP 200 原始 response，再針對可辨識的 Sportsbet URL 檢查 event ID；不同或缺 ID 明確報錯，不入賠率表，亦不寫入 fixture quarantine。未知／非 Sportsbet URL 保留既有處理，**不代表已證實安全**。另修正 enrichment／preclose 將 native 返回 `0`（身份拒絕）錯算作成功的計數。正反例涵蓋不同 ID、相同 ID 不同球員、相同 ID 對調順序、缺 ID、非 Sportsbet 來源及兩條 market 寫入路徑。

## 已有歷史資料：未修復

299 個錯 event receipt 中，113 個曾連接一般 `odds_snapshots`、對應 3,049 行一般 market；104 個曾連接 preclose odds、對應 434 行 preclose market。這些是已保存的原始行數，不能從名字相似或不同推斷所有下注／結算已受影響。113 行一般 match-winner odds 均非其 match/book/market 最早行；104 行 preclose odds 都是其組合最早行。**最早 match-winner 規則不代表其他 market 安全。**

對全部涉及該 113 場的五個賽日，直接執行 native `_rows_for_date(..., earliest_only=True)`：讀取器返回 3,002 行，其中 **888 行、84 個 match、84 個錯 event receipt** 被選中；2026-06-17 650/650 行全部來自這類 receipt。逐行結果及原有資料保存在 `historical-reader-audit-v1/`。這證明讀取層暴露錯 event 資料；沒有重算最終 prop、投注、ROI 或模型判決，不能聲稱 84 個模型結果必然受影響，也不能假定既有研究全部無效。

**本改動只防止新入口寫入；既有 217 份已連結的 odds snapshot 與對應 market 行並未清理或修改。** 後續須在保留原始 `MIN(id)`／真實賽前時鐘的前提下，獨立審計歷史市場／close／研究讀取器，標記或排除錯誤 source receipt，重跑受影響研究並記錄 row-flow；不能靜靜取較後一個價格冒充開盤。缺失 receipt、不同 ID namespace、event 重用及同名球員須 fail closed 或列為未驗證。相關舊研究及結果在受影響 scope 未審清前不能用作新的準確率／ROI 證據。
