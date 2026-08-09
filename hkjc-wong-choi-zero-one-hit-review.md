# HKJC Wong Choi 0／1 Hit Review Plan

## Goal

找出模型頭兩選在 0 hit／1 hit 場次的可重複失誤模式，先改善第二推薦位及第三選升格判斷，再用時間外樣本證明不是賽果倒推。

## Scope Lock

- 主口徑：模型 Top 2 有幾多匹跑入實際前三（0／1／2 hit）。
- 對照口徑：現有 Reflector `Miss / 1 Hit / Pass / Good / Gold`，避免破壞歷史比較。
- 研究訊號：段速／speed、form line、班次、路程、risk、confidence、資料缺失。
- 「冷門」只指模型第三選或低評級但具上限馬，不用賠率／市場資料。
- 不研究：天雨／場地轉變、檔位、第四至第七名近分馬 tie-break、投注注碼。
- 每完成一步先交付結果及建議；未獲確認不進入下一步，亦不改正式模型。

## Steps

- [x] 1. 鎖定樣本與標籤：建立所有可配對 `Logic + scoring + results` 賽事清單，分開 Top 2 hit count 與 Reflector label，列出缺檔／死熱處理。→ 驗證：每場推薦、名次及標籤可由原始檔重算一致。
- [x] 2. 建立 0／1 hit 基線圖：按日期、場地、班次、路程、馬數、信心及頭三名分差統計比例，但不調參。→ 驗證：總場數與各 bucket 相加一致，並列明樣本過細項目。
- [x] 3. 逐場覆盤 0 hit：比較實際前三與模型頭三在六項研究訊號的差異，分類為資料缺失、上限壓低、context錯配、風險判斷錯誤或整體辨識失敗。只記錄實際頭馬是否落在模型頭三之外，不做第4至第7名 tie-break。→ 驗證：每個 0 hit 場只有一個主因及最多兩個副因，附原始數值證據。
- [x] 4. 逐場覆盤 1 hit：集中檢查第二推薦位，量化第二選與第三選的段速、form line、班次／路程、risk／confidence差，找可安全升格的第三選。→ 驗證：分清「可交換排序」與「前三名單本身錯誤」，不可事後只挑中馬例子。
- [x] 5. 建立評分矩陣跨時段審核：以純矩陣總分及各dimension檢查development／近期AUC、Top 2覆蓋、neutral-60與權重對齊；排除micro tie-break、盲換、賠率／市場，stored going／draw維度只作結構審核。→ 驗證：候選方向須跨archive及近期同向，單一賽事故事不升格為規則。
- [x] 6. 提出小量完整矩陣候選：固定四個非grid-search方案，依次測試speed-only替換、穩定性增權、穩定性／級數平衡及5%路程context；保留初出馬公式，race-shape權重凍結，不使用micro tie-break或盲換。→ 驗證：已列development、temporal holdout、近期獨立及07-15的helped、harmed、0→1、1→2及頭馬 Top 2變化；四案均未通過跨段硬閘，正式模型不變。
- [ ] 7. 做 walk-forward 防過擬合測試：規則在 development 定義，temporal 只驗證，再凍結到未見 future meetings；禁止按測試結果反覆微調同一 holdout。→ 驗證：至少30場新賽事、5次觸發，helped−harmed為正；未增加3次有效升格前若先踢走2匹第二選入前三馬即否決。
- [ ] 8. 最終驗證與決策：同正式模型比較 0 hit率、1 hit率、Top 2頭馬覆蓋、兩選同入前三、觸發穩定性及各子群傷害。→ 驗證：測試及 Auto validation全過後，才決定保持 shadow、局部啟用或完全否決。

## Done When

- [ ] 每個改善建議都有跨時段證據、明確傷害上限及可重跑輸出。
- [ ] 0 hit／1 hit改善不是靠賠率、場地天氣或第4至第7名重新排序。
- [ ] 未通過 future shadow gate 前，正式 HKJC Wong Choi分數與排名保持不變。
