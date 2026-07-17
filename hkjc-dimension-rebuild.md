# HKJC Rating Matrix Dimension重建

## Goal

重建不含going／draw嘅評分dimension，保留現有12項公開feature，加入內部證據量與可靠度收縮；首先降低Top 2零命中，若零命中未跌，則改善「模型第三選實際入前三、原Top 2其中一匹甩出前三」嘅有效升格，同時不傷害頭馬及Top 2總命中。

## Tasks

- [x] 1. 鎖定來源契約：盤點12項feature、derived signal、7個dimension嘅原始來源、公式、缺失／中性率、重疊及going／draw污染。→ Verify：245場／3054匹可重跑、0錯誤；確認draw↔race-shape相關0.956、form↔consistency相關0.766，並發現speed及form-line有明顯engine版本漂移，已列每項可用／需重建／排除判斷。
- [x] 2. 建立無賽果洩漏嘅replay資料層：由archive materialized snapshot與近期Logic共同structured primitives建立統一horse-row，保留source mode、provenance group及7組evidence coverage；結果與原模型rank獨立隔離。→ Verify：25日／245場／3054匹、每場恰有3個實際前三label及完整原rank 1–3，0 build/schema error；going／draw／barrier／track bias／pace／run style／odds／market／ROI／edge全部不在primitive白名單。
- [x] 3. 定義重建dimension：建立純L400 speed-engine、無draw distance-context、拆重後stability／class-weight／trainer／readiness／form-line，以及逐項可靠度向60收縮；初出／薄資料馬保持中性upside。→ Verify：3054匹、7維、0 validation error；輸出完全無label／原rank、going／draw／barrier／pace／市場欄位，reliability=0必定60；公開12-feature schema及正式Auto保持不變。
- [x] 4. 在development做單項診斷與ablation：只解封9日／88場／1093匹，量化AUC、可靠樣本、逐賽日方向、單項Top2及七維等權移除影響；無搜尋權重。→ Verify：stability（Top3 AUC 0.689、9/9正向）、trainer（0.609、8/9）及speed-only（0.565、5/9）通過核心閘；distance、class-weight、readiness及form-line暫緩／否決；temporal／近期／07-15賽果未載入，公式及threshold無按結果修改。
- [x] 5. 凍結三個完整矩陣候選：balanced core（各約1/3）、stability-led（20/50/30）及winner-guard（15/40/45），非初出只用speed／stability／trainer；初出統一50%中性＋50% trainer，整場重排。→ Verify：3054匹／245場完整deterministic排名、0錯誤及0邊界同分；三候選development均傷害總hits／頭馬，第三選有效升格淨值亦全負，因此無候選獲准解封Step 6，未按結果再調權。
- [x] 5b. 沿現行官方outer weights做三個固定外科式替換：先以純L400 speed取代sectional並將race-shape中性化，再依次加入重建trainer及stability；其餘class／health／form-line不變，無權重搜尋。→ Verify：全245場排名先凍結、88場development雙基準審核、0 load／validation error及0邊界同分；三案雖有一案將0-hit由21降至15，但總hits由94跌至84、頭馬Top2由39跌至32，另外兩案亦傷害總hits／頭馬，第三選有效升格淨值全負，故無候選解封Step 6；獨立重跑CSV／JSON／report SHA-256完全一致。
- [x] 5c. 對0／1-hit及原模型第2／第3選固定邊界做dimension失誤分型，分開「第三選入位／第二選甩位」可救案例與相反嘅必須保護案例；量化現行及重建dimension嘅AUC、class-balanced方向、逐賽日方向、可靠樣本及dominant blocker。→ Verify：88場中0／1-hit共61場，第三選正確升格理論上可令10場0→1、7場1→2；現行純矩陣可救方向只有23.5%但保護方向93.8%，確認結構性偏保守。現行form-line平衡方向61.9%應保留；重建readiness-risk全配對58.2%／AUC 0.615，可靠配對58.8%／0.619，係唯一值得進入下一個細幅結構候選；speed、distance、trainer不晉級，class-weight只救唔守。0 validation error，獨立重跑四份輸出SHA-256完全一致，正式Auto不變。
- [x] 5d. 凍結三個不確定性槽候選：readiness取代health槽、現行trainer按既有pre-race可靠度向60收縮，以及兩者合併；沿用官方一般／初出outer weights，無搜尋倍率或threshold，全245場先重排再載入development結果。→ Verify：readiness-only令0／1／2 hit由21/40/27改善至18/43/27，總hits +3、頭馬Top2 +2、0-hit -3；14場Top2變動帶來6 helped／3 harmed，第三選有效／有害升格7/3、淨值+4，0邊界同分，通過LOWER_ZERO_HIT gate。改善分散於4個正向／4持平／1負向賽日；0-hit賽日3改善／6持平／0轉差；只有1個變動場次涉及初出馬且無造成命中得失。兩個trainer收縮案均傷害總hits及頭馬而否決。0 load／validation error，獨立重跑三份輸出SHA-256完全一致；只解封readiness-only進入Step 6，正式Auto不變。
- [x] 6. 只對Step 5d凍結嘅readiness-only做跨時段驗證，分開temporal holdout、近期獨立及07-15，再合併157場量化0→正數、1→2、錯誤升格、頭馬及總hits；任何一段轉差都不可由合併樣本遮蓋。→ Verify：temporal 39場hits +1／頭馬+1／0-hit持平；近期109場hits持平／頭馬+1／0-hit持平；07-15九場hits +1／頭馬+1／0-hit -1，三段全部通過non-harm。合併由54/77/26變53/77/27，總hits +2、頭馬+3、0-hit -1，第三選有效／有害升格3/2、淨值+1，18場Top2變動及0邊界同分，通過LOWER_ZERO_HIT gate。限制係近期有兩個單日轉差，而場地分拆跑馬地61場完全持平、主要淨改善來自沙田96場；07-15第8場就由4/2改2/3，升格3號翠紅（頭馬）取代5名嘅4號競駿輝煌。0 validation error，獨立重跑三份輸出SHA-256完全一致；准入Auto shadow但未改正式主線。
- [x] 7. 將readiness-only移植為Auto內部`readiness_health_slot` shadow profile，精確重現休賽日數／體重波幅domain bands、證據量/2可靠度及向60收縮；只替換shadow health槽，加入Top2進出記錄及內部CSV欄位，正式Markdown不展示。→ Verify：5檔compile、32/32 unit／integration、engine／formula／report validation全過；一般馬、初出馬、缺資料60、outer formula及mainline isolation都有測試。07-15 Race 8真實Logic主線／shadow雙跑成功，正式matrix／分數／rank／Top2／verdict及Markdown完全相同；但現役引擎其他dimension已較歷史存檔矩陣漂移，shadow現時保持4/2而無重現歷史2/3，因此只批准內部shadow，未改正式health槽。下一步須用現役引擎版本重跑既有歷史樣本，唔需要硬等30場future，但不可直接以舊matrix版本結果上線。
- [x] 8. 用現役引擎、現行兩季pre-race priors及凍結`readiness_health_slot`重跑近期109場加07-15九場；原meeting唯讀，Logic／Facts／racecard及priors只下載到`/tmp`，每個meeting連續重跑兩次。→ Provisional result：118場／12日、0 source error、兩次結果完全一致；當時錄得總Top2 hits +4、頭馬Top2 +3、0-hit -1及gate PASS。但正式晉升前做mainline parity audit發現，舊shadow喺SIP enhancement之前分支，而mainline其後獨立取得SIP加分；因此候選並非「只替換health槽」，+4／+3混入咗壓低shadow SIP嘅效果。呢份結果已標記為失效promotion evidence，只保留作root-cause audit，唔可作上線依據。
- [x] 9. 修正shadow isolation：mainline及每個shadow profile各自按本身ability／grade獨立套用同一SIP規則，再以legacy mainline對readiness shadow重跑同一118場。→ Verify：修正後0/1/2由34/59/25變33/61/24，總Top2 hits 109→109、頭馬Top2 45→45、第一選中頭馬30→29；9場Top2變動係3改善／3轉差，現行第3選有效／有害救援3/3。07-15九場仍由5/1/3變4/2/3（hits +1、0-hit -1），但獨立近期109場由29/58/22變29/59/21（hits -1），所以split non-harm失敗，正式promotion gate FAIL。官方default已安全保留`legacy_health_v2`，readiness只保留explicit opt-in／內部shadow；default Top2與晉升前baseline 118/118場完全一致。35/35 regression tests及compile通過。

## Done When

- [x] 新dimension完全不以going、draw、賠率、市場、pace或micro tie-break改善排名。
- [ ] 有通過SIP-matched isolation嘅可重跑證據顯示0-hit下降，或第三選有效升格改善而不傷頭馬與Top 2總hits；目前readiness候選係3改善／3轉差，未達晉升標準。
- [x] 同一holdout不因結果反覆改公式；future shadow只係可選額外確認，唔係硬性完成條件。
