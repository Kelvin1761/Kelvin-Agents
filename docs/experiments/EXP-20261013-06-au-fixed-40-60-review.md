# EXP-20261013-06 — 固定 FORM40／PQ60 深入覆核

## 登記範圍（新重播結果未開前）

用戶要求認真覆核 EXP-03 全 dev Good +14、Gold +1。
只測已曝光、已選定嘅固定40:60對60:40，不新增配比或找最佳門檻。
先重現舊1762場嘅淨改善，拆開修好／損害場數、五個原日期fold、賽日bootstrap、
來源缺值分層。自動選配比策略嘅失敗不能充當固定40:60嘅失敗。

再以已發佈 main a0bf0f388bd6053641cc08d41b2915ee73bb7c5f 同一批2533場
完整舊eligibility（1762 dev＋771後段；曝光Tamworth meeting仍排除）重新取
production scoring projection。baseline 必須逐匹分數及最終renderer排名完全一致；
candidate 只替換stability內FORM:PQ40:60，保留原矩陣係數、其他維度、原始overlays、
production rounding、完整賽前field同thin-evidence ranking policy。
結果/SP只喺完成評分後join；無新抽取、無賠率入分。

兩邊同樣以原已對齊賽果馬作評估，亦記完整field與未join馬數。
Primary Gold／Good；配對賽日bootstrap2000 seed7，六個連續日期塊；
四個field-size、五個baseline首選SPcohort、venue／going、前後資料格式period。
Transition counts與逐場差異只作機制說明，不能拿嚟追加新rule。

40:60係已經由舊grid結果揀出嘅假設；以下全期重播係覆核同診斷，不能事後叫做
預先固定、未接觸結果嘅獨立測試。現行v3全紀錄把尺照用，不修改promotion要求。
本輪不改live模型，不push；若有值得追蹤訊號再明確報未驗證前瞻證據需求。

## 結果

原數字重現：Good47修好／33失去，淨+14；Gold33／32，淨+1。
原features＋現行class_weight配方Good+9；完整現行main原dev Good+5／Gold−1；
後段771 Good−7／Gold+6；全2533 Good−2／Gold+5。
primary點估計Good負、六塊只3/6非負；不能promotion。不是用CI跨零單獨判死。
Gold-or-Good supplementary舊淨+30、新淨+15，double-success分別−15／−12；
這是post-hoc診斷，唔改把尺救候選。
舊matrix同現行main唯一配方差異class_weight多class_score .15；源features也不同。
完整結果、來源限制及命令見docs/audits/au-race-weight-oracle-20261013/FIXED_40_60_REVIEW.md。
**決定**：保留研究候選；未改live、未commit/push。下一次驗證須用新日期及凍結版本。

## 用戶追加：訊號強度與設計（新source分層結果未開前）

進一步只作診斷，不擬合權重。以現行main projection先評分，再join賽果：
1. FORM、PQ、class、rating及整體ability嘅場內配對AUC（全樣本及去中性口徑）。
2. FORM與PQ排序衝突嘅正／負樣本pairs；baseline與PQ排序衝突pairs。
3. 重新捕捉PQ完整來源／fallback、PQ真實run_count、FORM有效名次行數，並逐匹
核對分數同既有projection完全一致。
4. 指標按PQ來源（完整與fallback）同前後日期段列出；不從結果挑門檻、cohort或ratio。

這些只量訊號/增量/來源，不替代原primary閘。新設計文件會分清已量證據與未試假設，
特別避免把固定ratio、自動選ratio、來源可靠度三件事混在一起。

## 訊號診斷結果

完整PQ 21708匹、fallback 2569匹。只比較同場同來源、實際top3對非top3配對，
完整PQ AUC .6455（day CI .6358–.6551），FORM .6255；
fallback PQ .5403（.5107–.5726），FORM .5748。AUC並非命中率或機率校準。
後段完整PQ .6454、FORM .6446；fallback PQ .5535、FORM .6266。
全模型排序AUC baseline .6813→uniform40 .6800。PQ與FORM排序衝突時，
PQ正確比例dev .5333、後段 .4818。強單項訊號不等於提高權重有增量。
場內中心化相關PQ／FORM .556、PQ／class .269；相關本身不證明重複計分。
來源分流單一候選另登記EXP07，完整結果及後續測試設計見STABILITY_DESIGN_REVIEW.md。
