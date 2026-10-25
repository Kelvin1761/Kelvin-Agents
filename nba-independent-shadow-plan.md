# NBA 獨立概率模型研究計劃

- [x] 搜尋既有 C／RF／Poisson-NB／角色研究；確認舊RF本身無價格，不能假裝首次移除價格。
- [x] 固定來源、既有19日開發／5日已見terminal界線及五折時間OOS，記錄C歷史重疊限制。
- [x] 同一母體先量 raw market／C／原始L10 baseline；不用最後5日調參或新增盲測聲稱。
- [x] 建立每stat正則 logistic，以count分布及近期命中為底，分開分鐘、角色、對手環境及休息特徵；無價格預測輸入。
- [x] Full／core及逐block消融，同日cluster不確定性、機率校準、選擇覆蓋與單腿價格診斷；不冒充SGM聯合EV。
- [x] 寫工程測試、跑quick及full；結果不夠／失敗只保存研究分支，正式C及EV門檻不變。
- [x] 保存模型、source/code/protocol hash、OOF預測、報告與下一階段前瞻方案。

- [x] 額外擷取41類NBA基本／進階／tracking／對手原始表：40成功、1明列不支援，不倒填歷史。
- 完整測試及研究分支SHA以外置Final_Verification.json為準；正式C及EV不變，不能聲稱盈利改善。
