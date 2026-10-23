# NBA Wong Choi 全面審核計劃（2026-10-23）

目標：追查現役 NBA 資料、模型、SGM、排程同結算嘅實際缺陷，將正確性修正同未驗證模型假設分開。
基準：`origin/main` `8f09e341`；獨立分支 `codex-nba-full-audit-20261023`（remote 已有 `codex`，故唔可用 slash namespace）。

- [x] 固定現役版本、設定、既有實驗及測試基準，確認舊問題是否已修。
- [x] 追蹤 Sportsbet、球員身份／傷停、L10、跨季補數據及 cache 嘅來源與截止。
- [x] 核對機率層、10-Factor、ML train/serve、MC、edge／EV 數學及實際接線。
- [x] 核對 Banker／SGM 揀腿、相關性、真實 SGM 價及 Kelly 計算。
- [x] 檢查回測切分、point-in-time、資料洩漏及已有實驗嘅可信範圍。
- [x] 追查排程刷新、immutable snapshot、賽果 finality、DNP、ledger 同匯出。
- [x] 為確認 bug 建最小重現、修正及回歸測試；其餘列入分級報告。
- [x] 跑 NBA 專項（351 passed）、`./檢查.sh --quick` 及完整 `./檢查.sh`（16 suite 全過）；建立可重現證據與交付報告。

限制：今次唔調權重、唔重訓、唔以兩日結果揀參；live ledger 只讀。大型回放另行設計，先確認完整 HOT／WARM 語料及外置碟。
交付：`docs/audits/nba-full-model-audit-2026-10-23.md`、審核數據摘要、測試及經驗證嘅工程修正。未有同語料 out-of-sample 評估，唔聲稱模型表現改善。
