# Sol 揭盲後覆盤：Flemington 2026-11-07

**本文件全部屬賽後觀察。** 初選九場已先經父 agent 驗證及 SHA256 鎖定；本文件沒有改初選、重排、重設信心或改模型。原報告 R1–R5、R9 為 low，R6–R8 為 medium，原樣保留。只讀已授權的凍結輸入、原輸出、comparison.md/json 及 Wong_Choi_Attribution.json；沒有影片、當日步速、風向、走位、受阻或臨場健康證據，因此不替任何意外賽果編故事。

鎖定值：Sol_Predictions.json `50c061150afdca6c5f555dd9564656a93e7b52d2eeb5af3da3f476145d7af0a4`；Sol_Analysis.md `1b936331fa8033ccbd25370978d2f8c6ea01a628969dfc74cfd06b0d834dbb1b`。

## 看數字前先定界線

賽後 comparison 的全部105匹結果身份均對得上輸入，沒有晚退或缺結果。Sol 的前四捕捉16/27匹前三，旺財13/27；Gold為4/9對1/9、Good positional為3/9對2/9。但首選頭馬旺財3/9、Sol2/9。這天Sol較好的是前四覆蓋，並非首選勝率。四個Gold中，R8兩邊前四集合一樣；其餘三個差別分別來自R1 Goddess Kay、R7 Buckaroo、R9 Lawborough。不能將Gold差距解讀為四次獨立證明。

這是事後盲態單次分析，不是當時發布的預測；沒有概率、投注規則或賽前價格決策，不報ROI，亦不聲稱校準或統計優越。以下「判錯」只描述固定選擇與結果不符，並不自動證明當時判斷不合理，或已知因果。

## 逐場賽後檢討

### R1：Goddess Kay進前四有預先依據，Rusty Pearl則係錯選

**賽後結果：** Soldi、Goddess Kay、She's Supreme。Sol前四4/5/7/13捕捉三匹；旺財4/5/3/1捕捉兩匹，兩者首選都勝。

**鎖定前真正寫過：** Sol將Goddess Kay排第三，理由是兩次本場800米跳閘第一（R1.md:F0145、F0150），並明寫未正式上陣、0.00不代表齊頭。不是賽後才發現這兩課。Soldi正式1000米勝、She's Supreme十二駒Gimcrack季軍亦早已用作較可靠基準（F0083、F0121）。但Sol把Rusty Pearl排第四，雖已留意760米合成地跳閘勝及早前4/1異常（F0270、F0275），仍在第四席押新馬證據，結果只第十；Miss Ruthless第四則只被排第八。不能只報Goddess Kay而略去這兩項。

**旺財歸因資料：** `races[0].horses[number=7]`已有trial_score82、preparation_score64.38，matrix preparation62.19，備戰貢獻+0.41；並非完全漏讀跳閘。The Chancer相應備戰貢獻+0.32，但騎練+6.35，Goddess Kay只+1.86，兩者class_weight同為-0.61。Public Affairs騎練+4.19亦較高。可核實的差異是「已表示的準備訊號被其他合成項蓋過」。trial_score本身是否另有直接排名路徑，單憑此JSON不能證實；須父agent查code，不能稱trial_score欄存在就等於已有效入總分。

**分類：** 來源已提供、表示後組合不同；新馬噪音亦大。結果不證明兩次跳閘第一應固定加幾分，也不證明騎練訊號普遍錯誤。

### R2：兩邊同樣漏亞季；Sol並無特別優勢

**賽後結果：** Superfabulistic、He'll Rip、Options。兩邊前四各只捕捉頭馬，Sol頭馬列第二、旺財第三。Sol首選Fiorenot只第六，第四選Nation's Call包尾，Options被列第十一。

Sol早已寫Superfabulistic輕磅內檔、近期1600米接近（R2.md:F0713、R0039–R0040）；這是選對方向，未選中頭馬。對He'll Rip亦寫兩場BM84接近，但因直接後於Fiorenot、短休及一年未勝而只排第六（F0210、F0215、F0205、F0202）。Options最近跳閘勝、曾在本場勝、閹後復出變數都有寫，仍以160日未跑及之前大敗為主要疑慮（F0396、F0389、F0394、F0411）。因此是已知正面未足獲優先，不是資料全無。

Nation's Call之前本場13/14的反證亦已註明（F0162），但我仍讓最新勝仗支配第四席，結果錯。37.77馬位大敗不能自行歸因傷患、步速或資料bug。**分類：** Sol組合判錯／未能驗證的當日變數；沒有足夠證據指向旺財獨有盲點。

### R3：King Pedro升首係Sol失手，旺財首選較好

**賽後結果：** Pinhole、Manzor Blue、Torranzino。旺財首選Pinhole勝，Sol只排第二；兩邊前四均只中Pinhole。

我將King Pedro由直接比較推成首選：MV Cup第四先Pinhole、六月Stayers Cup曾勝Pinhole近三馬位（R3.md:F0201、F0226–F0227），明知十一檔、實負56公斤含超磅、未試2600米，仍選其先。Pinhole近期Herbert Power勝及回56公斤都有記錄（F0143、R0011），但我偏重兩次舊對賽，未讓其較近的勝仗在最後取捨佔先。King Pedro結果第七，並非僅差一席。

旺財亦不是完全反對King Pedro：總分Pinhole78.3802、King Pedro77.6045，只差0.7757。後者stability90.18、pace91.08比Pinhole84.23、65.27更高；Pinhole騎練貢獻+8.74對+6.24、proven_class調整+0.5793對-0.1528等，最終令其稍先。這是同批有力馬的組合取捨，旺財這次結果較好，不能因Sol全日Gold多而略去。

Manzor Blue3200米勝亞、Torranzino去年Geelong Cup勝/Melbourne Cup第五都在初選寫過（F0478、F0473、F0299、F0294）。我因前者近期本地第13、後者今季大敗而排第九及第七；兩者分別亞季，說明「寫過耐力」不等於「已預見入位」。**分類：** Sol對直接對賽的相對重視失手；共同低估舊長途能力的當日重現。是否存在可泛化回勇規律尚未驗證。

### R4：共同排Watchme Win第十，Sol加重Grand Impact更錯

**賽後結果：** Watchme Win、Inkaruna、Photograph。Sol首選Inkaruna亞，旺財第二選亦亞；兩邊前四各中一匹。Sol次選Grand Impact第十三，旺財首選Grand Larceny第五。

初選對Watchme Win確曾寫最新Rising Fast第七只輸2.41、明顯先Grand Larceny（R4.md:F0205），但以本場三戰未入位、一年未勝而排第十（F0198、F0202）。Photograph從第16位至第五、輸2.16及Alinghi第三也已寫，仍因好地未勝及之前落後Inkaruna而只排第六（F0647、F0652、F0662、F0641）。這不是「Sol識得而模型唔識」；Sol同樣排唔入前四。

旺財Watchme Win form_quality runs包含最新7/19：value1.007874；最後stability47.08貢獻-4.34，pace62.60貢獻+0.23，track51.19貢獻-0.85。Photograph已有stability79.90、pace73.44，貢獻+6.68/+1.18，卻被騎練-0.69、class_weight-0.84、track-0.85等拉低至第七。故不是漏掉近期追近。form_line98.5/99.5雖高，但解釋貢獻表未見獨立該項；是否有效入總分須查code。

我反而將同一Rising Fast第四的Grand Impact升第二，忽略了我自己列出的本場未勝與好地勝績稀少反證。結果它遠後於上仗排其後的Watchme Win，說明「同一場先到＋低磅」不足穩定決定下仗。**分類：** 共同合成/判斷失手；當日路線或步速原因無證據，不能補故事。

### R5：Sun Gift排第十五是共同嚴重失手，不能用Too Darn Discreet亞軍遮掩

**賽後結果：** Sun Gift、Too Darn Discreet、Perfect Ten；Classic Gem第四。兩邊前四只中Too Darn Discreet。Sol首選亞，旺財首選Soverato包尾。Sol第三選Vivy Air第十五，第四選Ocean Bay第十二，表現同樣差。

我預先指出Too Darn Discreet從60降56、Soverato從54升57，7公斤相對轉移，以及前者2000米四戰三勝（R5.md:F0269、R0016、F0205、R0013、F0262）；結果這項取捨比單跟Tesio名次好，但不能據此聲稱磅位是亞軍原因，更不能推出固定磅值。

Sun Gift的2000米十三戰四勝五亞與10月2025米亞軍已在初選支持欄（F0705、F0722）；我仍把11月4日重地第六輸7.6、三日再出當體力疑問，排尾二（F0712）。Tesio第七實際只輸1.54亦在引用F0717，但我敘述只寫「只第七」，沒有像處理某些其他馬般突出窄負。這是Sol敘事選擇不對稱，值得自我檢查；賽後並不能把三日再出改寫成預先看好的復甦訊號。

旺財亦有其最新六場，包括11月4日6/8、Tesio7/15、10月9日2/11。Sun Gift stability37.45貢獻-7.57、pace27.65貢獻-2.84、class_weight-2.02；track67.40其實加+0.71。不是完全沒表示適性，是長期/近期相對分蓋過了適性。Perfect Ten Sol第十、旺財第六；我已寫Lady's Day Vase季及全年佳績，卻強調Tesio第十及2000米未證（F0780、F0772、F0775）。Classic Gem舊Oaks第四輸1.64亦早知，仍排末（F1000）。

**分類：** 共同判錯與同源名次/近況壓力；「場地由重轉好」「三日再出仍能保持體力」只是這次結果相容的假說，不是已確證因果，更不是應普遍加分的規律。

### R6：全日前四覆蓋最差一場，medium信心亦必須原樣承擔

**賽後結果：** Point Barrow、Plaintiff、Skybird；Headwall第四僅輸0.56。兩邊前四全失。Sol將頭馬排第六、亞軍包尾、季軍第七；旺財第七、第十、第九。Sol首選Tempted第五、次選Joliestar第六、第三選Caballus包尾。

我用近期Everest/Premiere/Concorde的直接勝出與級數優先Tempted及Joliestar（R6.md:F0207、F0212、F0222、F0270），信心medium。Point Barrow同程六戰四勝及連勝How Now、Northwood Plume明明早已列支持，仍因牝馬賽轉頂級開放及Sangster曾輸而壓至第六（F0515、F0532、F0527、F0552）。Skybird本場四戰全部入位、Gilgai勝亦已列，仍只第七（F0389、F0401）。Plaintiff PJ Bell勝、Sheraco輸0.86已知，卻以Premiere第九輸Tempted4.48等作決定性反證（F0616、F0596、F0591）。這是「事前知道但冇揀」，不能冒認先見之明。

旺財三匹正面也不是全缺：Point Barrow兩次近期同程勝在form_quality runs中，但相對stability45.47貢獻-4.88、class_weight-1.53；Skybird track69加+0.86，卻stability45.83及pace19.33合計貢獻-8.34；Plaintiff近績/舊勝均在runs中，但stability32.79、pace34.70、class_weight51.60合計貢獻-14.51。相反Tempted stability93.72，Joliestar88.43。JSON的form_quality紀錄明示獎金z值，Everest2000萬的z_prize_raw7.6599，與20–24萬牝馬賽約2.02–2.24相差大；這支持檢查「獎金/級數與相對標準化如何影響升班連勝馬」，不支持直接定論大獎金造成失手。

pace來源明示sportsbet_race_context，而basis寫own；不能據basis標籤就稱真個體末段。所有十匹race_shape均60，究竟因直路策略設計中性還是資料通路缺失須code/來源稽核；結果檔沒有當日走位，無法判定步速或分組造成爆冷。Skybird到Headwall只有0.10馬位，亦提醒前四截點會放大很小的名次差。**分類：** 共享級數/近績偏好在這場失手，兼有待驗證的相對分與來源語意疑點；不是LLM解救模型的一場。

### R7：Buckaroo取代Pounding有事前證據，但並非模型漏讀最新一哩

**賽後結果：** Autumn Glow、Lindermann、Buckaroo；Tom Kitten第四。兩邊首兩揀均正確；Sol第四席Buckaroo捕捉季軍，旺財第四席Pounding只第七。

我事前以Buckaroo最新Crystal Mile同場1600米第二輸0.5、Futurity亞軍作第四席（R7.md:F0143、F0188），同時保留Turnbull大敗與今多2公斤風險。對Pounding寫Coongy第四輸0.85及Feehan季，但指出一年十二戰未勝、Feehan僅六駒（F0270、F0275、F0267）。這才是原比較，不能賽後補稱已看透其長途血統或真實步速。

旺財Buckaroo form_quality第一項正是10月24日2/11，value1.916534；所以最新一哩亞軍有被讀入。其前次Turnbull12/13亦入列且value-0.501391，最終stability52.20、pace43.12，貢獻-2.62/-1.48。Pounding stability57.24、pace73.85貢獻-0.93/+1.22；form_quality詳情更已有2000縮1600的trip_change -5，不能聲稱縮程完全沒處理。兩者track同69，Buckaroo class_weight62.24亦優於Pounding57.29，仍總分59.8254對63.7326。

**分類：** 有表示但不同取捨，特別是近期特定途程回勇與較長往績窗口的比較。是否需要新的路徑，須先驗證現有路徑行為；本場只提出檢查題，不證明應改時間窗。

### R8：兩邊同一前四，Sol亦未選中頭馬

**賽後結果：** Birdman、Cosmic Crusader、Sir Delius；Aeliana第四。兩邊均Gold，前四集合完全相同。Sol把Birdman排第二、旺財第三，首選同為Cosmic Crusader。

原分析已指出Birdman在Underwood曾勝首選、最新Cox Plate只輸0.75（R8.md:F0279、F0269）；Cosmic Crusader近期本場雙勝仍令我取其先（F0016、F0026）。結果顯示競爭可逆，但不能把一檔慳程、首選恢復或步速情境說成已驗證原因。Sir Delius首次眼罩只列未知，沒有自動加分；其第三不證明眼罩有效。

**分類：** 同組有力馬次序誤差與單場波動；不是Sol獨有覆蓋成功，亦沒有明確新增模型盲點。

### R9：Lawborough第四席正確，Educated首選大失，Torsheen下調並非全勝

**賽後結果：** Lawborough、Tres Magnifique、Esmahli；Royal Rendezvous第四。Sol前四全含前三，旺財漏Lawborough。SolLawborough只排第四，沒有選中頭馬；Sol首選Educated第十一，旺財首選Torsheen第六，旺財在首選實際名次較好。

原分析以Lawborough最新好地1100米BM78勝、一馬位先Fission、好地五戰三勝取第四（R9.md:F0845、F0846、F0839），並明寫今多3公斤、上仗同組曾後於Tres Magnifique，沒有把它當穩膽。Torsheen第八是因195日未賽、首次本場/1100米、多件裝備移除及最新跳閘名次矛盾；同時承認Typhoon Tracy亞及Mornington勝（F0143、F0138、F0134、F0145–F0146、F0170、F0160）。這些並非遺漏資料。

旺財Lawborough form_quality明示10月28日同程勝、原value1.190895，stability68.17與pace76.07已有正貢獻+2.74/+1.41，距離score66亦非中性；但騎練-2.00、class_weight-0.69、track-0.08等，總分62.0627排第七。Torsheen stability92.81貢獻+11.01、pace85.64貢獻+2.25，總79.7231排第一。故「漏了Lawborough最新勝」不成立。

可查的疑點：Torsheen的form_quality六場全是2–4月，最近一場仍獲序列weight1.0；pace run_dates含兩個2026-01-21，對應凍結輸入重複行F0185/F0190。這支持檢查去重及曆日陳舊度是否進有效排名，但尚不能證明重複導致首選錯，或所有舊績沒衰減（可能其他路徑已有處理，待父agent查code）。health59、preparation60存在亦不足證明195日風險已有效反映。

Educated被我首選，是好地三戰三勝、同場1100米勝、最新勝Electric Elvis/Fission（F0202、F0243、F0208–F0209），結果第十一；這再次顯示我同樣會將小樣本不敗與直接對賽過度外推。**分類：** Lawborough/Torsheen為有表示但組合不同，另有待核實去重/陳舊度路徑；Educated為Sol明確失手。

## 哪些是已見合成抵消，哪些仍只是假說

| 題目 | 本次能確認 | 本次不能確認 |
|---|---|---|
| R1 Goddess Kay跳閘 | trial/preparation已有值，騎練貢獻相較弱 | trial_score是否直接入總分、兩次跳閘勝應增加多少權重 |
| R7 Buckaroo近期一哩 | 最新2/11已進form_quality，舊大敗及race-context pace一起合成；Pounding有縮程處理 | 是否需更短窗口、是否有「回勇」獨立路徑、哪個改動能OOS改善 |
| R9 Lawborough近勝 | 已進form_quality及正pace分，仍受其他項及Torsheen高舊績分拉開 | 是否缺曆日衰減；重複一日造成多少影響 |
| R4 Photograph、R5 Sun Gift、R6 Skybird適性 | 適性/近況至少部分有正表示，被其他項抵消 | 不能把失手全叫抽取缺欄；需counterfactual/ablation才能量因果 |
| form_line高分、trial_score高分 | 欄位存在；所給contributions未展示相應獨立項 | 未見貢獻不等於已證死code；須查完整排名公式及呼叫路徑 |
| race-context pace與basis own | JSON同時出現兩種語意；凍結輸入標RaceL600 | 是否實際使用個體資料、語意差異是否改排名及造成失手 |
| R6直路race_shape全60 | 本場十駒一致中性 | 是設計上有意中性、來源缺失還是故障；當日步速原因 |

沒有一項可僅憑本次賽果直接判作「已證明應新增特徵」。較清楚的候選資料品質項是重複往績與來源語意；較清楚的模型研究項是回勇/專項近期表現與混合往績、獎金相對化的取捨。兩者都要先沿現役code追到實際排名通路。

## 可重現後續問題，不是本日調參清單

1. **來源/語意稽核，先不改分：** 對R9 Torsheen的一月廿一日重複、R1矛盾跳閘、race-context L600與own標籤，逐條核對原始不可變快照及現役讀取路徑；缺證據就保留未知。建立重現例與錯誤類型，先分清數據bug或設計。
2. **排名可達性稽核：** 分別追trial_score、preparation、form_line、distance、health及曆日間距如何到最終分，核對所給contributions是否完整。只有真正缺通路才稱缺通路；有通路但被蓋過則保留該分類。
3. **預先註冊研究問題：** 在獨立開發語料檢查「新近相同場地/途程回勇能否在壞舊績後保有價值」「升班連勝馬是否受獎金相對分壓低」「短休與轉地況的風險是否校準」。不能用本九場決定時間窗、條件、門檻或權重；若進入模型候選，另走既定baseline/OOS/ablation/holdout紀律。
4. **同時量Sol失誤：** 原樣保留R3 King Pedro錯升首、R4 Grand Impact錯升第二、R5 Vivy Air與Ocean Bay高排/Sun Gift低排、R6全失、R9 Educated錯首；不要只收集三匹有利divergence。將來若做多meeting盲測，預先固定相同輸入、指標及置信/缺資料標準。

目前結論只到：這天Sol的三個第四席取捨多捕捉三匹前三；旺財多中一匹首選頭馬；兩者共享多個嚴重失手。沒有提出新排序、權重、模型改動、promotion或自動開forward測試。

## 證據索引

- 初選依據：Sol_Predictions.json的`races[場次-1].runner_assessments`與Sol_Analysis.md；每項R/F引用指向inputs/RN.md的實際標籤。
- 賽後結果及指標：comparison.json的`races[].actual_results`、`metrics`與`summary`；comparison.md的全日比較。
- 旺財可見分解：Wong_Choi_Attribution.json的`races[].horses[number=馬號]`下`matrix_scores`、`contributions`、`stability_form_quality.runs`、`pace`及`preparation`。本覆盤沒讀code，因此所有「通路可能缺失」均明確待code覆核，沒有當作已證明。
