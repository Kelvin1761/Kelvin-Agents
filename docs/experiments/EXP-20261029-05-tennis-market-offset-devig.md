# EXP-20261029-05：歷史去水及固定市場offset

2026-10-29 Sydney；Tennis賽前勝負。**於任何本批價格候選擬合／結果前登記**。

原38比較／76檢定family預留C02／C01／C13，方法見[market protocol](../../research/tennis_unified/protocol_market.json)。舊PROP市場residual／surface-conditioned失敗保持原判；今次係match-winner、獨立原始價格來源及固定七個tennis signed features，唔重試舊props候選。已查EXP-20260826-09、EXP-20261027-05／08／09及EXP-20261029-03／04；亦不選回首輪點估計最好嘅失敗feature。

原publisher2020–25 ATP/WTA十二份XLSX、27,795 raw rows已凍結。B365／PS同書兩邊成對；Max／Avg不當book，2025新增BFE合約／commission未驗先留置。Vig域事前固定`1−1e−12 <= sum inverse odds <=1.30`，不按ROI或候選表現揀book／年份／quote版本。

先用唯一name alias、unordered pair、event name/location、輪次與draw-size、surface、best-of及`0 <= book_date−source_tournament_start <21d`選身份；之後先核對winner及逐盤比分。歧義／source衝突留置，不用比分揀個吻合結果。原始locator只供已驗body hash追溯，唔係跨provider身份。日期跨season年界不因檔名年份直接剔走；source context晚過book event day嘅case仍留置，唔倒改forecast context。所有模型／去水方法同群體及同book pairs。

F03：現有proportional控制，power／Shin各一arm；一個global inner選法只讀外層之前兩個完整半年度及已按原21日政策可用labels，先LL、再Brier、再固定method order，同match多book總權重1；不按ROI選法。

F09 C01：`logit(p)=logit(raw proportional fair market p)+beta*x`，市場係明示輸入、offset係數固定1；七欄原B_simple，無截距、ridge1。Proportional anchor獨立於C02結果，唔將兩個改動綁埋。與同報價市場及同群體tennis-only logistic各比較；tennis-only控制按unique matches fit，offset各book權重1/k，scaler同由training unique matches計。

C13只報training encompassing raw-unit coefficients，市場係數可自由估；不產生另一組test候選、不揀係數救模型。新模型只需同一Sportsbet兩邊價及原七欄即可推論，其他book僅歷史訓練用途。

五段2023H1／H2、2024H1／H2、2025H1及原source tournament-start split不變；2021 expanding train、label`start+21d<fold_start`。全部已看資料SEEN_DEV。**價格無captured_at／quote type證據，估計目標只係given歷史公開quote嘅conditional dev；唔係較早已發出嘅預測、已證PIT、CLV或可執行ROI。** Formal promotion仍被PIT／live provenance／新forward及原ruler擋住。

先逐book算LL／Brier，再同場平均loss，最後match bootstrap4,000次／95%／seed20260826；唔以平均probability代替平均loss。原已執行比較raw p照帶入76名額，剩餘名額p=1，不重新開alpha。每個候選五fold兩項不退步、pooled正且Holm支持先ADVANCE_DEV_ONLY；offset兩個控制都要過。全部分層／校準／coverage／hypothetical ROI照報，失敗不掃參或換窗。

**目前狀態：本批已完成，power／Shin／inner選法／offset全部REJECT_DEV。** Immutable價格cohort、method/source/runtime／測試log lock及全部結果保存在同一外置run嘅`market-phase/`；原首輪REJECT及artifact不覆寫。

價格資格先得到23,225場／46,169同書配對觀察。亦發現26個已唯一識別但winner／比分有矛盾或無法核對嘅canonical keys；於任何本批fit前隔離，**不只剔走target，連歷史Elo／rank／prior等輸入亦重建排除**。原source-only首輪保持原資料及REJECT結論，不能用清理後資料去救舊候選。原source fixtures／raw回應不改；新clean cohort／features及identity lineage另存`qualified-inputs/`。

## 結果及判決

65項研究測試及quick通過後，於`2026-10-28T23:00:14.440794Z`寫入market lock，SHA256 `63e262a1df0f419946093afb2d5eee9cc8ca374e97a118ddbb8ec3534edbf092`，先鎖再fit。Clean source cohort 27,237場、24,857 feature rows。五段dev同11,725場／23,393個book observations；各段N=2,592／1,896／2,596／1,943／2,698，train N=8,091／10,364／12,579／14,878／17,012。

| 同一群體及同書報價 | Log loss | Brier | 命中率（輔助） |
|---|---:|---:|---:|
| Proportional市場 | .58497479 | .20106651 | 68.2516% |
| Power | .58442390 | .20099174 | 68.2644% |
| Shin | .58449858 | .20098009 | 68.2516% |
| Inner去水選法 | .58442390 | .20099174 | 68.2644% |
| 固定市場offset＋網球七欄 | .58507150 | .20117815 | 68.1365% |
| 同群體純網球logistic研究控制 | .62044135 | .21615562 | 64.8273% |

Gain定義control−candidate；95% CI未作多重比較調整，判決用原76名額Holm。

| 比較 | LL gain［95% CI］ | Brier gain | LL／Brier不退步段數 | 判決 |
|---|---|---:|---|---|
| Power vs proportional | +.00055089［−.00006120,+.00115107］ | +.00007477 | 4/5；2/5 | REJECT_DEV |
| Shin vs proportional | +.00047621［+.00010353,+.00084539］ | +.00008642 | 4/5；4/5 | REJECT_DEV |
| Inner選法 vs proportional | 同Power；五次inner均只讀過往並選Power | 同Power | 4/5；2/5 | REJECT_DEV |
| Offset vs市場 | −.00009671［−.00056180,+.00034604］ | −.00011164 | 3/5；3/5 | REJECT_DEV |
| Offset vs純網球 | +.03536984［+.03139778,+.03944038］ | +.01497747 | 5/5；5/5 | 單項通過；offset整體仍拒絕 |

Shin LL未調整CI雖高於0，Holm p=.755811，Brier CI跨0，2025H1兩項均退步；不能只選好看指標。Offset相對純網球兩項Holm p=.018995，但相對市場兩項均退步；呢個顯示加入市場資訊嘅貢獻，**唔係證明網球修正令市場更準**。其他價格比較Holm p均1。C13只保存五份training encompassing coefficients，不作另一個test arm或以係數揀模型。

Hypothetical同場加權ROI：offset −100.035u／1,152.5u＝−8.6798%，95% match CI［−13.9392%,−3.4854%］；純網球 −1,021.675u／9,964u＝−10.2537%。Offset按book：B365 295注、−19.3864%；PS 2,005注、−7.0379%。無報價時鐘／類型證據，呢啲係as-if研究回報，唔係實際可落注ROI、CLV或盈利證據。

另發現共用事前clip[.02,.98]可令極端價產生數值假edge：純市場三種去水喺B365零注，PS有6注全輸，全部係clipping-created（raw去水本身無正EV）。完整輸出已逐arm標記`clipping_created_edge_quote_count`；**唔喺睇過結果後改clip／政策重跑救結果**，亦唔將呢6注解讀成真實市場策略。正式產品是否要分開loss clipping與下注概率，須另立正確性／政策scope，唔喺本次研究暗改。

## 獨立重現及交付

額外身份scope audit將未完成／比分無效等原始紀錄全部放回候選身份宇宙：30,879行均可讀identity，23,225個已配對match冇額外歧義。呢項核對唔依賴只保留completed嘅cohort，報告`full-identity-universe-audit.json`為PASS。

獨立script不import候選runner，重建全24,857行原七欄、quarantine歷史輸入、五fold training scales／ridge一階條件、inner選法、23,393個物理workbook quotes及概率、全11,725場loss、4,000次bootstrap及76名額Holm；亦重算每book／加權ROI及clipping edge數。PASS：價格誤差0，最大feature誤差2.70e−15、概率1.84e−13、fit gradient6.37e−13、bootstrap3.47e−16。只證明計算重現，PIT FLAG照留。

`report-export/`交付exact nested round-trip Parquet、paired_metrics.json、subgroups.csv、calibration.csv、roi_by_book.csv、cohort-flow、排除及feature-availability報告；9份產物逐項SHA核對。Formatter只用外置隔離PyArrow18.1.0，shared model runtime未改。方法、source、測試、全部失敗結果及獨立script均保留；最終完整16組suite全通過。未開新forward、未activate或更換正式模型。

```bash
P=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
RUN='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/market-phase'
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$P" -m research.tennis_unified.market_study run --lock "$RUN/market-lock.json" --output "$NEW_CREATE_ONLY_REPLAY_DIRECTORY"
```

**結論：本批四個候選全部拒絕，不調參／換窗／選回失敗feature。** 原10個feature及1個head拒絕保持不變。未完成F01全量資格、F02歷史規則、C14真實workload時鐘及C09 props合約另見進度表；統一研究及改善目標仍未完成。
