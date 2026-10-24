# NBA 全面修正完成審核（2026-10-24）

原始審核 F01–F12 已逐項修正及驗證，修正已合併入 main，生產 NBA runtime 已接通。呢個結論係工程及評估流程正確性，唔係命中率／盈利提升聲稱。

## 交付證據

- 最後 code release：`81b5c6428223e6a52368cb106628298abf242774`；完整閘 735.978 秒通過，全部 suite 通過（NBA 459 tests）。
- 22 個交付 runtime 檔案同 scheduler 逐 byte 一致；生產 HEAD `81b5c6428223e6a52368cb106628298abf242774` 包含主要 runtime 修正。
- 6 批 exact-scope release 都有固定 SHA 完整閘、push 成功、merge 及 activation event；最終補強同步 NBA，包含已合併 backtest CLI。
- 13 份研究證據 SHA 全部一致；C JSON 同 v3 shadow 模型／metadata hash 保持基準值。RF 候選不晉升，權重只留外置碟。
- 完整機器核對：`docs/audits/nba-remediation-completion-verification-20261024.json`。原始審核同早前批次報告保留，唔覆寫審核歷史。

## 逐項完成核對

| Finding | 已完成行為 | 驗證依據 |
|---|---|---|
| F01 cache 身份 | 模型／shadow runtime 開關入 cache 指紋，舊模式報告失效 | report cache 開關回歸；最終全量閘 |
| F02 unresolved 結算 | 未配對項目留待重試，唔佔首次結算 key | 空球員→補齊→重跑測試；本機 ledger 唯讀掃描冇舊 unresolved |
| F03 Final | 缺失／否定／pending 狀態拒絕結算，合法 OT 格式可用 | Final 狀態矩陣及重試測試 |
| F04 傷停／陣容 | 獨立 30 分鐘來源驗證、原子刷新、換 roster 重抽；離隊球員不能入組合或當傷兵分球權；跨入口 FW-14 | availability／來源失敗／roster／已開賽／發佈測試 |
| F05 SGM 真價 | 發佈前綁定 event／腿／真實 quote；過期、缺價、非正 EV 停；同一價格供 Kelly／報告／dashboard／凍結 ROI | 合成乘價正而真價負案例、quote／渲染／dashboard／結算測試 |
| F06 ML 方法 | 真對手、共用特徵、賽前來源／Final 標籤、整日時間切分、train-only imputer、artifact hash、strict post-training backtest；未合資格 ML 不能主導正式輸出 | 8,286 labels 固定評估、資料重建 SHA 一致、temporal／serving／CLI tests；RF 拒絕結果照記 |
| F07 大勝風險 | adj_breakdown 傳入候選，原有額外 5% 修正能觸發 | source→candidate→correlation integration、9-arm 重播 |
| F08 usage／pace／MC | 確認缺陣才提供紅利、復出清紅利、傳己隊 pace、MC 將 USG 百分點轉 stat units | marginal／joint 呼叫及單項／移除項消融；C 最終機率不變 |
| F09 defender | Totals／20 total attempts／單位及來源記錄；cache、新抽取及 FW-14 共用來源成功檢查，API 失敗停止發布 | 同截點 576 位官方回應核對：0→523 合格、PCT 值一致；新抽取分支及三入口測試 |
| F10 模型世代 | 先選實際最新 snapshot，再按 C 係數身份分組；MC 版本寫入 observation | 同日混代、未知身份、唔倒退舊快照測試；ledger 唯讀核對 |
| F11 描述一致 | selector／描述共用門檻及 fallback tag；腿數／波動／目標／最終機率來源如實；風險及 Kelly 同一 adjusted joint／真價 | policy／quote／完整報告及 dashboard 測試 |
| F12 設定失敗 | 缺檔／JSON／非法係數停止；刻意 disabled 明示；explicit ML 不合資格或失敗亦停止 | 設定矩陣、獨立公式、恢復重試及 CLI tests |

## 模型證據與限制

新 RF terminal Brier 0.182219，現役 C 同列 0.171071，候選較差，所以不晉升。終端只有 5 場獨立比賽，而且係已檢視歷史窗，唔係新盲測；舊 v3 隨機切分高 AUC 唔作 OOS 證據。現役 C 亦唔因今次工程修正而被當成已獨立證實優於市場。

9-arm × 50 captures 共 450 次 real renderer 全部成功；8,606 個 capture×leg C 最終機率同組合不變。full MC ΔBrier −0.000688，按日 CI 跨零，唔聲稱 MC 表現改善。新來源閘只阻擋失敗／未驗證輸入，冇調權重或揀更有利時間窗。

研究協議／重現命令／來源與消融：`EXP-20261023-06`、`EXP-20261023-07`；F09 新抽取補強另見 `nba-completion-boundary-fix-2026-10-24.md`。下一輪模型研究需要新 forward 證據及獨立晉升判決，唔係本次未修嘅程式 bug。
