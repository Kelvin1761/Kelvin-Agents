# Tennis 統一研究：開工條件及交付清單

2026-10-29 Sydney。呢份係[定稿計劃](../../tennis-research-execution-plan-20261028.md)嘅執行交接；以[詳細協議](tennis-research-protocol-20261028.md)為設計、[進度審計](../audits/tennis-unified-research-progress-20261028.md)為實際證據。**來源隔離feature／head及市場批次已訓練／評估，15個候選全部REJECT_DEV；未啟動新forward，未證實現役準確度改善。**

執行更新：EXP-20261029-03／04已完成27,263場cohort、24,880 feature rows、38比較／76檢定鎖，首輪13,274場、五段dev及獨立replay。下表保留原依賴及驗收；已完成部分以實際進度為準。原價格URL404其後查明目錄改動，全12個publisher檔已完成保守identity join，C02／C01於同11,725場完成、四個候選全拒絕；原76名額family不變。26個矛盾事件於fit前連歷史輸入隔離。無captured_at／quote type證據，ROI只係hypothetical，唔再將檔案缺失當目前理由。實際開／完賽時間、PIT及live來源資格仍未解決。

來源批次更新：EXP06已全量審計MCP metadata／Overview及49站98份Slam單打檔，Slam歷年規則明示。3,902／1,872場身份點數一致但發布時鐘未驗，來源augmentation資格未過。C14全raw時鐘盤點已作STOP判決；唔再將全量capture未做當目前理由。

## 原前置工作及餘項（進度審計列最新完成狀態）

| 次序／責任範圍 | 具體工作 | 驗收／停止條件 |
|---|---|---|
| 1．F00資料與重現 | 沿用已驗證嘅完整DB snapshot，隔離爭議labels及不合格時間；逐項追查feature capture警告；分開列B_live、B_simple及B_market資格 | canonical row-flow、每項排除原因、feature輸入來源／時鐘、baseline parity ≤1e−6。不能把0份qualified feature證據報成已過關；不倒填舊snapshot |
| 2．F01–02來源與規則 | 完成MCP canonical join／選樣coverage、PBP全量成對parser及terminal-state核對；補歷年賽制mapping | 每來源有固定版本、授權限制及可用欄位；未知格式／規則留置。已過22項數學case只證明相應假設下正確，不代替真實比賽校準 |
| 3．實驗啟動鎖 | 完成B_simple固定feature schema、標準化／缺值／swap處理；一次鎖F03–F09全部arms、控制、兩個主要指標及多重比較名額 | 保存protocol hash、split IDs hash、A/A及因果時間測試。鎖定前不得fit候選；資料不足嘅比較保留名額及未執行原因，不能見結果後改設計 |

以上係工作優先次序，依賴按來源／比較判斷，唔要求所有獨立資料源一齊成功。[研究與正式採用資格澄清](tennis-research-eligibility-clarification-20261029.md)已喺候選結果前獨立記錄：每個arm先過自身前置閘；缺live證據不能稱贏現役，缺PIT或正式採用合約繼續阻止promotion。若要改判決規則，先獨立論證並版本化，再接觸候選結果。

## 模型批次嘅資料依賴

| 批次 | 已定方向 | 尚需證明嘅輸入／限制 |
|---|---|---|
| F03 去水；F09市場offset | proportional對power／Shin；固定市場logit加網球修正 | 已完成同11,725場／23,393報價比較，power／Shin／inner／offset全部REJECT_DEV；B365／PS成對，BFE合約未驗留置。無captured_at只作dev，PIT／正式採用未過 |
| F04 surface Elo | `n/(n+20)`收縮，保留舊shadow | canonical surface歷史、當時overall／surface Elo與完整原控制。參數20只係固定待驗假設 |
| F05 serve；F06對手強度；F08 H2H | recency／真實point exposure／prior七arms；最近10場對手當時Elo；H2H residual | 只讀forecast前可用歷史；同一cohort／head／fallback。與舊REJECT逐項去重，不能將重新擬合嘅收益歸功新feature |
| F07 workload | 實際14日minutes／盤數及距上場結束hours | tournament start date加21日隔離，不能提供真實14日比賽時序；無實際日期／結束時間時暫停相關arm，不造hours或用盤數充minutes |
| F09 nonlinear head | 固定同一matrix比較logistic及一個histogram boosting設定 | F04–08先有結論；輸入schema、選用features及組合／leave-one-out須喺F09結果前鎖定 |
| F10 joint props | 同一分佈推導winner／sets／games／handicap | F02及serve資格先過；各family另具market、line、retirement／void、settlement合約。PBP點數不能代替市場證據 |

其他莊家歷史逐場資料／ROI只用訓練及dev研究；全book同場總權重1，唔按ROI揀book。Sportsbet-only inference及之後新forward另驗。只得公開總ROI數字不能當逐場target；無報價時鐘亦不能稱可執行收益。

## 交付及判決

- 每批先登記實驗，再保存全部arms、paired逐場預測、五段時間fold、LL／Brier、校準、coverage、分book收益及失敗原因；不可只交最好一個數字。
- 開發期遵守詳細協議嘅五段不退步、pooled增量及Holm比較要求；不符合則REJECT_DEV。歷史資料全部SEEN_DEV，不能冒充獨立驗證。
- 最多一個候選／betting family進新forward；先凍結全部artifact及起點，再收集。每family至少600場，亦須滿足預定power；最多365日、一次正式判決。時間／樣本不足報不確定。
- 正式採用仍須frozen tennis-v1及既有guardrails。定性／缺失門檻另作規則澄清，不能與候選一齊改尺。通過僅表示可進release review。
- repo保存方法、精確來源URL／SHA、結果摘要及可重跑命令；大型raw／DB及prediction artifacts留喺已驗證外置run目錄。未完成／失敗模型只保存研究分支。

**下一批餘項**：優先追實際runtime feature-provenance／daily board缺口。F01全量審計已完成，來源發布時鐘未驗、P05仍missing；F02已補Slam2011–24規則但legacy MC無年份輸入；C14實際14日／end clock資格停止，C09各props市場／settlement合約及合格serve候選依賴未齊。已失敗候選不重跑；無單項通過就不硬合併，新forward仍未啟動。

**計劃驗收**：八個項目及C01–C17都有去向；依賴、控制、時間切分、消融、停止、判決及證據位置已寫清。**研究驗收另計**：各批有全部結果或有證據嘅暫停判決；只有真正通過新forward先可聲稱可採用嘅準確度改善。
