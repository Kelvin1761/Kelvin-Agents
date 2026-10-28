# Tennis Wong Choi：統一研究執行計劃

2026-10-28｜計劃已完成；用戶其後已授權執行，F00–F02進行中。實際完成證據及餘項見[執行進度](docs/audits/tennis-unified-research-progress-20261028.md)。目標係用八個外部項目嘅方法／資料，驗證有冇可重現嘅增量；唔預先聲稱改善。

依據：[比較筆記](docs/plans/tennis-external-project-review-notes-20261028.md)、[URL／版本 manifest](docs/plans/tennis-external-project-sources-20261028.json)、[詳細協議](docs/plans/tennis-research-protocol-20261028.md)。沿用 frozen `tennis-v1`，唔改正式模型、下注政策或現有 shadow。

| 次序 | 工作／依賴 | 完成證據 |
|---|---|---|
| 1 | 鎖定實際 runtime、approved baseline、ruler／guardrail 版本及舊實驗排除清單 | `run_manifest.json`；未解決嘅基準／數值門檻衝突會阻止模型實驗 |
| 2 | 唯讀凍結一次語料；canonical match 去重、時間及多 book 審計（C04/10/17） | source/data SHA256、完整 row-flow、研究／PIT／settlement eligible 分流 |
| 3 | 重現完整 baseline，再建立同特徵簡單研究控制 | 保存方向及 risk shrink 後誤差 ≤1e−6；不合格紀錄逐項列出 |
| 4 | 做 MCP／兩套 PBP schema 品質盤點（C07/16），及獨立 kernel 正確性核對（C08） | coverage／時間／授權限制表；規則 invariants、DP/MC 誤差及耗時報告 |
| 5 | 先登記再跑有限單項實驗：去水、surface Elo、serve recency/exposure、對手強度、workload、H2H（C02/03/06/12/14/15） | 相同 match IDs、時間 folds、配對 LL/Brier、全部 arms／缺值／失敗結果 |
| 6 | 固定特徵做 logistic vs 非線性 head、市場 offset／條件增量；合格候選才做合併及逐項消融（C01/11/13，C05 去重） | 分清 feature/head/market 增量；舊 REJECT 不重開；開發失敗即停止 |
| 7 | kernel 過關後，另批驗聯合 props 一致性（C09）；資料合約不足嘅 family 暫停 | winner／set／games 邊際一致；每個 family 獨立市場及 settlement 證據 |
| 8 | 凍結最多一個候選／family，預先鎖 N、期限及新 forward 起點 | immutable predictions；match bootstrap 4,000 次、95% CI、seed 20260826；每 family ≥600 場且有 power |
| 9 | 最後覆核時間洩漏、消融、收益及重現證據，記錄判決並保存 | `REJECT`／`NEEDS_MORE_TESTING`／`ELIGIBLE_FOR_RELEASE_REVIEW`；通過先另行 release gate |

允許其他莊家歷史賠率、逐場賽果及開發期 ROI 作訓練／研究；無報價時鐘嘅 ROI 唔當可執行回報。Sportsbet forward 另驗。同一場多 book／多 point 只算一個 match cluster。

**完成研究嘅定義**：每個候選有去向、每個實驗有事前協議及全部結果，或者有明確暫停原因。可以得出「冇候選值得升級」。模型實驗須依次通過資料及baseline前置閘，唔直接跳去訓練；研究進行中不等於準確度已改善。
