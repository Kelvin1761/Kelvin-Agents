# Tennis Wong Choi：統一研究執行計劃

2026-10-28 建立；2026-10-29 執行更新。**計劃已完成；研究執行中，暫時未證實準確度改善。** 八個外部項目嘅 URL／固定版本及資料用途已保存；已測 15 個候選全部 REJECT_DEV，無新候選入 forward。

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

**完成研究嘅定義**：每個候選有去向、每個實驗有事前協議及全部結果，或者有明確暫停原因。可以得出「冇候選值得升級」。訓練及模型 promotion 各自須過相應資料／證據閘，唔將計劃完成當模型已改善。

**目前執行狀態**：已凍結一份 DB、重現 baseline、完成五段 dev 特徵／head 及多 book 市場比較、MCP／49站 Slam 全量審計與 kernel 正確性核對。歷史比較只屬 SEEN_DEV；15 個候選未過穩定性／市場增量要求。來源發布時鐘及實際 workload 結束時間未驗證，相關 arms 停止；未有合格 serve 候選／joint props 合約，故 C09／新 forward 未開始。完整失敗研究與證據已保存本 repo 非 main 分支 `codex-tennis-unified-research-20261028`（checkpoint `69f7674f3bd842e3871e3f98a183b10613e1d247`）；唔部署該分支模型。

**下一步**：依序處理已重現嘅輸入缺口。已交付[被拒絕投影嘅原樣診斷保存](docs/audits/tennis-observation-diagnostics-20261029.md)，今次[修正 Toray 當屆 metadata](docs/audits/tennis-toray-metadata-20261029.md)並量度輸入影響；其餘 identity／資料過期問題按正常 run 證據逐項處理。修正資料唔自動證明準確度提升，原拒絕判決、Sportsbet forward 要求及 frozen ruler 均不變。

**身份來源跟進**：[排名／canonical 目標修正](docs/audits/tennis-player-source-integrity-20261029.md)在固定 2,160 行真實來源上，原版只更新 77 行；修正可更新 2,153 行，7 行保持明確留置，來源仍報 partial/error。已重現及阻止錯 canonical 姓名返回、同批兩個來源身份覆蓋同一排名。無改寫 live legacy history／Elo，未證實模型準確度改善；舊混合身份仍須有原始證據、備份及 exact-plan 修復。
