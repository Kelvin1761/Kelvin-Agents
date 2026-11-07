# Sol 獨立盲態分析：2026-11-07 Flemington

本報告固定九場排序，供之後揭盲與旺財及賽果比較。採質性證據評估，並未使用旺財排名、賽果、賠率、外部來源或評分引擎。這是 retrospective input-blind 診斷，並非當時發出的預測。

模型要求：`gpt-6.1-sol`。只讀 protocol 及 `inputs/R1.md` 至 `inputs/R9.md`；九份完整閱讀。沒有認出今日任何賽果。

方法：先比較近期實戰、同場直接對賽、班次及途程適合，再考慮現行磅、復出進度與可能形勢；唔把歷史名次、勝率或評分單獨當答案。所有新馬、首次裝備、跨地及復出推測都保留反證。沒有數字勝率或ROI。

共同限制：Good 4只係凍結輸入；天氣未知、rail空白，當日風與跑線偏差未知。RaceL600係全場而非個體末段，PF欄標明race_context亦不作個體末段。Stewards空白唔代表冇受阻。跳閘0.00唔係齊頭證據，跨場地/日期時間不直接比較。現行負磅與歷史負磅分開；不自行猜學徒減磅。

以下引用均為凍結輸入的實際R/F行標，JSON保留每條引用的原文。完整排序包含快照當時全部active runner；早已Scratched不列，晚退馬日後只能另作刪除後比較，不能改原選。

| 場 | 頭二（固定） | 前四（固定） | 信心 |
|---|---|---|---|
| R1 | 4 → 5 | 4 → 5 → 7 → 13 | low |
| R2 | 2 → 13 | 2 → 13 → 1 → 3 | low |
| R3 | 5 → 4 | 5 → 4 → 3 → 8 | low |
| R4 | 6 → 8 | 6 → 8 → 1 → 5 | low |
| R5 | 5 → 4 | 5 → 4 → 8 → 15 | low |
| R6 | 6 → 7 | 6 → 7 → 4 → 3 | medium |
| R7 | 8 → 2 | 8 → 2 → 1 → 3 | medium |
| R8 | 1 → 5 | 1 → 5 → 10 → 3 | medium |
| R9 | 6 → 10 | 6 → 10 → 2 → 19 | low |

## R1

**完整固定排序：** 4 Soldi → 5 She's Supreme → 7 Goddess Kay → 13 Rusty Pearl → 10 Natural Emotion → 3 The Chancer → 1 Public Affairs → 9 Miss Ruthless → 8 Jacquets Off → 11 Naughty May → 2 Steel Point

**信心：low**。頭二：[4, 5]；前四：[4, 5, 7, 13]。

### 形勢及主要比較

- **Soldi與She's Supreme同時爭先**：兩匹有正式領放證據，快步速增加新馬追入機會，但新馬跑法未知。（R1.md:F0083；R1.md:F0121）
- **Soldi順利掌速**：已有好地1000米取勝經驗最有用，維持首選。（R1.md:F0083）
- Soldi正式勝績勝於純跳閘；She's Supreme十二駒入位較有可核實性。
- Goddess Kay與Rusty Pearl跳閘勝出只作準備訊號，不用跨場時間排名。

### 逐匹分析

**第1位｜4. Soldi** — 首選；唯一正式勝馬，已證1000米可領可贏。

支持：Debutant Stakes 領放以0.10馬位勝出。

風險：只一場、贏距窄，九檔及其他前速可能令領放更辛苦。

證據：R1.md:F0083；R1.md:F0084；R1.md:R0015。

**第2位｜5. She's Supreme** — 次選；已有大場1000米入位證據。

支持：Gimcrack 十二駒跑第三，最近再試閘第二。

風險：曾領放最後落後2.64馬位；好地適應未實證。

證據：R1.md:F0121；R1.md:F0116；R1.md:F0110。

**第3位｜7. Goddess Kay** — 新馬中優先；兩次本場跳閘第一。

支持：9月及10月800米跳閘均第一。

風險：0.00輸距唔係齊頭；未有正式賽可比。

證據：R1.md:F0145；R1.md:F0150；R1.md:F0136。

**第4位｜13. Rusty Pearl** — 近期十駒跳閘勝出，列第四。

支持：760米合成地跳閘第一。

風險：早前4/1不可能記錄；草地實戰未明。

證據：R1.md:F0270；R1.md:F0275；R1.md:F0261。

**第5位｜10. Natural Emotion** — 近期兩次跳閘頭二，可爭四席。

支持：750米十三駒第二；800米四駒第一。

風險：合成地與草地不能直接比時間；首次多件裝備。

證據：R1.md:F0217；R1.md:F0222；R1.md:F0206。

**第6位｜3. The Chancer** — 有短程跳閘勝績，列新馬中游。

支持：650米跳閘第一，800米第三。

風險：跳閘勝負唔足以證實實戰水平，首次綁舌。

證據：R1.md:F0060；R1.md:F0065；R1.md:F0049。

**第7位｜1. Public Affairs** — 兩次本場跳閘有基本準備，暫列中後。

支持：兩次800米跳閘第二、第三。

風險：未正式上陣；首次眼罩效果未知。

證據：R1.md:F0017；R1.md:F0022；R1.md:R0006。

**第8位｜9. Miss Ruthless** — 正式試閘接近，屬可進步冷門。

支持：Gosford 八駒第四僅輸1.07。

風險：只有一次試閘，軟地轉好地未知。

證據：R1.md:F0198；R1.md:F0189。

**第9位｜8. Jacquets Off** — 試閘有勝但證據薄，排後。

支持：最近本場800米跳閘第一。

風險：僅兩駒；此前六駒第五，十三檔跑線未明。

證據：R1.md:F0169；R1.md:F0179；R1.md:R0025。

**第10位｜11. Naughty May** — 記錄矛盾，暫列較後。

支持：近期750米跳閘有前列記錄。

風險：finish寫2/3但名次列第一；早前本場第四。

證據：R1.md:F0246；R1.md:F0247；R1.md:F0251。

**第11位｜2. Steel Point** — 現有試閘證據較弱，列末位但新馬變數大。

支持：840米試閘第三。

風險：輸6.05馬位，冇正式賽績。

證據：R1.md:F0041；R1.md:F0032。

### 可能改變排序的缺失資訊

- 當日風、直路跑線偏差、馬匹狀態及實際出閘未提供。
- Stewards 空白唔代表冇受阻；RaceL600 係全場而非個體。
- 現行磅按Racecard；歷史行是來源記錄負磅，未明示減磅時不假定已扣，也不對不明現役claim自行扣重。

### 資料品質

- Soldi 9月24日跳閘疑似重複且starter數不同。
- Naughty May finish與名次互相矛盾；Rusty Pearl出現4/1。
- 大多數係新馬，信心低；0.00跳閘輸距不可信作量化。
- Natural Emotion F0227記3/6但F0228列第二；只把該早期跳閘當作準備，不作精確排名依據。

## R2

**完整固定排序：** 2 Fiorenot → 13 Superfabulistic → 1 Roulette King → 3 Nation's Call → 11 Mount Bona → 4 He'll Rip → 9 Grand Omaha → 5 Test Of Love → 6 Dirty Old Town → 8 Silvasista → 7 Options → 10 Hiyaam Proud

**信心：low**。頭二：[2, 13]；前四：[2, 13, 1, 3]。

### 形勢及主要比較

- **Test Of Love外檔搶放，Superfabulistic守前**：持續步速有利Fiorenot、Roulette King追；Superfabulistic需避免鬥快。（R2.md:F0269；R2.md:F0718；R2.md:F0079）
- **前列互讓、步速平和**：二檔54公斤Superfabulistic更具威脅；Fiorenot須提早發力。（R2.md:R0039；R2.md:R0040；R2.md:F0713）
- Fiorenot兩度直接勝He'll Rip，可靠度較高。
- Superfabulistic比Roulette King輕7.5公斤，但前者班次較低、後者復出大敗；選擇現況穩定者在先。

### 逐匹分析

**第1位｜2. Fiorenot** — 首選；近兩場BM84第一、第二，穩定且本場有勝績。

支持：最近兩次都先於He'll Rip，本場四戰兩勝。

風險：常居後列要步速配合；今60比上次59.5略增。

證據：R2.md:F0079；R2.md:F0084；R2.md:F0072；R2.md:R0007。

**第2位｜13. Superfabulistic** — 次選；輕磅內檔與穩定近況有利。

支持：最近1600米負60.5第三輸0.91；今54及二檔。

風險：主要BM72往績，上升競爭；Test Of Love或搶放。

證據：R2.md:F0713；R2.md:R0039；R2.md:R0040；R2.md:F0718。

**第3位｜1. Roulette King** — 第三選，憑較高級舊勝績押第二次上陣反彈。

支持：Alister Clark 2000米勝；過去兩次第二仗都勝。

風險：復出1300米第12輸7.59；今負61.5最高。

證據：R2.md:F0041；R2.md:F0012；R2.md:F0016；R2.md:R0004。

**第4位｜3. Nation's Call** — 第四選；近況回勇兼1600米專長。

支持：最近1600米BM78勝、之前BM84第二。

風險：本場8月同類途程曾13/14；Logan Bates減磅未明，不自行扣磅。

證據：R2.md:F0142；R2.md:F0147；R2.md:F0162；R2.md:R0010。

**第5位｜11. Mount Bona** — 第五選；第二仗加至不敗途程有上升空間。

支持：1600米兩戰兩勝，第二仗有勝亞。

風險：復出BM74六駒第四輸4.55；升班不確定。

證據：R2.md:F0642；R2.md:F0645；R2.md:F0649。

**第6位｜4. He'll Rip** — 位置候補；同場比較稍遜Fiorenot。

支持：兩次BM84亞季均接近。

風險：11月3日剛跑，短休；一年未勝，今58.5高於上次55.5。

證據：R2.md:F0210；R2.md:F0215；R2.md:F0205；R2.md:F0202；R2.md:R0013。

**第7位｜9. Grand Omaha** — 降班加程可回升，列中段。

支持：1600米三戰勝亞季齊；The Coast第三。

風險：復出兩戰大敗，十三檔可能耗力。

證據：R2.md:F0516；R2.md:F0553；R2.md:F0523；R2.md:F0528；R2.md:R0029。

**第8位｜5. Test Of Love** — 可領放改善，但外檔加程要付代價。

支持：Randwick BM88領放第四輸2.32；有1600米勝績。

風險：十一檔，與Superfabulistic前速相撞；今58高於上次56。

證據：R2.md:F0269；R2.md:F0262；R2.md:R0015；R2.md:R0016。

**第9位｜6. Dirty Old Town** — 中後選；最近盃賽接近但班底比較仍有疑問。

支持：Gawler Cup第四輸1.45；1600米三戰一勝一季。

風險：外檔，近期勝仗來自BM72，今55.5高於上次54。

證據：R2.md:F0332；R2.md:F0342；R2.md:F0325；R2.md:R0020。

**第10位｜8. Silvasista** — 後選；有質素但此次一哩復出未見充分證據。

支持：VOBIS Guineas1600米第二；St Leger勝。

風險：153日未跑，近三跳閘未入前二；以長途勝績不能當作今次速度。

證據：R2.md:F0505；R2.md:F0490；R2.md:F0458；R2.md:F0460。

**第11位｜7. Options** — 後選；閹後復出有變數，未足押重。

支持：最近1000米跳閘第一，有本場勝績。

風險：160日未賽，前四場實戰均落敗且多大敗，十二檔。

證據：R2.md:F0396；R2.md:F0389；R2.md:F0394；R2.md:F0411；R2.md:R0022。

**第12位｜10. Hiyaam Proud** — 最低優先；內檔輕磅仍不足抵消近期弱勢。

支持：一檔54.5；歷史BM84有亞軍。

風險：最近BM78第12輸9.72，一哩九戰未勝。

證據：R2.md:R0032；R2.md:R0033；R2.md:F0626；R2.md:F0586；R2.md:F0579。

### 可能改變排序的缺失資訊

- 當日風、直路跑線偏差、馬匹狀態及實際出閘未提供。
- Stewards 空白唔代表冇受阻；RaceL600 係全場而非個體。
- 現行磅按Racecard；歷史行是來源記錄負磅，未明示減磅時不假定已扣，也不對不明現役claim自行扣重。

### 資料品質

- Nation's Call試閘RaceL600 52.92異常，不作能力依據。
- Days欄可能與日曆差一天；短休依具體日期判讀。

## R3

**完整固定排序：** 5 King Pedro → 4 Pinhole → 3 Berkeley Square → 8 Litzdeel → 1 Defiantly → 7 Valiant King → 6 Torranzino → 11 Bella Montagna → 9 Manzor Blue → 10 Newlook

**信心：low**。頭二：[5, 4]；前四：[5, 4, 3, 8]。

### 形勢及主要比較

- **Torranzino沿用近期前置，Litzdeel跟前**：King Pedro可跟隨前組節省追趕距離；真正持續步速亦利Defiantly耐力。（R3.md:F0264；R3.md:F0390；R3.md:F0201）
- **步速放緩、最後短衝**：Pinhole及Berkeley Square後置有位置風險；Litzdeel前置更有利，Defiantly縮程風險放大。（R3.md:F0138；R3.md:F0075；R3.md:F0390；R3.md:F0021）
- King Pedro對Pinhole有六月及十月兩次直接先到證據，兩匹今實負同為56。
- Berkeley Square最新先Litzdeel半馬位，今相對減磅較多；惟Litzdeel本場長途穩定度更高。

### 逐匹分析

**第1位｜5. King Pedro** — 首選；近期同場比較領先，長途穩定。

支持：MV Cup第四先Pinhole；Stayers Cup曾勝Pinhole近三馬位。

風險：十一檔，實際56公斤已含0.5超磅；2600米未試。

證據：R3.md:F0201；R3.md:F0226；R3.md:F0227；R3.md:R0014；R3.md:F0194。

**第2位｜4. Pinhole** — 次選；近勝Herbert Power，回56公斤具競爭力。

支持：2400米十三駒勝，最近MV Cup第七只輸3.41。

風險：兩次勝仗贏距極窄；今再加程，常後追受步速影響。

證據：R3.md:F0143；R3.md:F0148；R3.md:F0138；R3.md:R0011。

**第3位｜3. Berkeley Square** — 第三選，最新反彈可信，今較同場對手磅位有利。

支持：Bendigo Cup負59.5第二、先Litzdeel半馬位，今57.5。

風險：此前多場不入位，可能只是短暫回勇；2600米未勝。

證據：R3.md:F0075；R3.md:F0076；R3.md:R0008；R3.md:F0068。

**第4位｜8. Litzdeel** — 第四選；前置位置及本場長途穩定有力。

支持：本場六戰一勝四亞，Roy Higgins2600米第二，最新Bendigo第三。

風險：近一年未勝；比Berkeley Square最新相對磅位變差1.5公斤。

證據：R3.md:F0383；R3.md:F0430；R3.md:F0390；R3.md:R0023。

**第5位｜1. Defiantly** — 有潛在最高耐力水平，惟首次本地上陣列第五。

支持：最近2999米勝5.5馬位，再前4149米十八駒勝。

風險：75日未賽，2600米相對偏短，59.5最高磅，跨國班底不可直接換算。

證據：R3.md:F0016；R3.md:F0017；R3.md:F0021；R3.md:F0014；R3.md:R0004。

**第6位｜7. Valiant King** — 可爭位置但勝出信念有限。

支持：Bart Cummings第三；MV Cup第八僅比Pinhole差0.06馬位。

風險：28戰只兩勝，最近一年八戰未勝；Litzdeel同場明顯先到。

證據：R3.md:F0332；R3.md:F0327；R3.md:F0324；R3.md:F0318。

**第7位｜6. Torranzino** — 舊級數足但近期未回復，列第七。

支持：去年Geelong Cup勝及Melbourne Cup第五。

風險：今季三戰全敗，最近領放退第12；加程不保證翻身。

證據：R3.md:F0299；R3.md:F0294；R3.md:F0264；R3.md:F0269。

**第8位｜11. Bella Montagna** — 中後選；近期穩定入圍但贏力仍待證。

支持：Colin Stephen第三輸1.19、Newcastle Cup第三。

風險：好地十二戰未勝，最新2600米第五；十二檔跑法未定。

證據：R3.md:F0584；R3.md:F0589；R3.md:F0573；R3.md:F0579；R3.md:R0031。

**第9位｜9. Manzor Blue** — 耐力已證，但本地最近一仗未有競爭力，列後。

支持：Trentham3200米勝，Ellerslie3200米亞。

風險：MV Cup第13；若慢步速其後追耐力難用。

證據：R3.md:F0478；R3.md:F0473；R3.md:F0453。

**第10位｜10. Newlook** — 列末；需要明顯反彈兼證好地。

支持：4月2600米Chairmans勝，有相應長途能力。

風險：最近第七且好地五戰未入位；Bart Cummings落後Litzdeel。

證據：R3.md:F0561；R3.md:F0516；R3.md:F0510；R3.md:F0521。

### 可能改變排序的缺失資訊

- 缺當日風、跑線偏差、臨場狀態及完整分段。
- Stewards空白不能當作冇受阻；RaceL600唔係個體末段。
- 現行磅按Racecard；歷史行是來源記錄負磅，未明示減磅時不假定已扣，也不對不明現役claim自行扣重。

### 資料品質

- Litzdeel F0420試閘RaceL600 14.80明顯異常，不使用。
- Defiantly部分歷史主行與名次列負磅相差0.5公斤；不作精密磅值換算。

## R4

**完整固定排序：** 6 Inkaruna → 8 Grand Impact → 1 Arkansaw Kid → 5 Pallaton → 9 Immortal Star → 11 Photograph → 12 Cripps → 2 Grand Larceny → 17 Hankee Alpha → 4 Watchme Win → 15 Piastri → 7 De Bergerac → 10 La Fracas → 3 Sir Sway

**信心：low**。頭二：[6, 8]；前四：[6, 8, 1, 5]。

### 形勢及主要比較

- **Sir Sway與其他前置馬推快**：Inkaruna、Grand Impact可跟前群；Photograph後上位置機會增加。（R4.md:F0147；R4.md:F0331；R4.md:F0457；R4.md:F0647）
- **直路分組及跑線比步速更關鍵**：十七檔Inkaruna同十五檔Arkansaw Kid可能一組；未有跑線偏差資料，唔把外檔自動當蝕位。（R4.md:R0018；R4.md:R0003；R4.md:R0002）
- Grand Impact在Rising Fast明顯先Watchme Win、Hankee Alpha、Grand Larceny、De Bergerac；保持次選。
- Inkaruna直接先Grand Larceny與Watchme Win、今更輕；Arkansaw Kid本場成績好但需負59.5。

### 逐匹分析

**第1位｜6. Inkaruna** — 首選，近期對強手持續接近兼回54公斤。

支持：Schillaci第三先Grand Larceny、Watchme Win；How Now1200米第三。

風險：十七檔直路跑線未知；一星期再出，15戰只兩勝。

證據：R4.md:F0336；R4.md:F0341；R4.md:R0019；R4.md:R0018；R4.md:F0331；R4.md:F0322。

**第2位｜8. Grand Impact** — 次選；最新大場第四係本場最直接可靠新證據。

支持：Rising Fast十九駒第四僅輸1.35；此前BM94連亞。

風險：同樣七日再出，好地勝率不高，未勝本場。

證據：R4.md:F0457；R4.md:F0472；R4.md:F0477；R4.md:F0451；R4.md:F0450。

**第3位｜1. Arkansaw Kid** — 第三選，可靠直路班底但頂磅拉低勝出把握。

支持：本場1200米多次入位，Bobbie Lewis第四輸0.81。

風險：今59.5最高；最近第六、近一年未勝。

證據：R4.md:F0009；R4.md:F0026；R4.md:R0004；R4.md:F0016；R4.md:F0013。

**第4位｜5. Pallaton** — 第四選，近期BM100勝可抗衡。

支持：9月勝Ndola，歷史Zeditave1200米亦勝。

風險：最新1000米第六輸4.20；本場1200米未入位。

證據：R4.md:F0273；R4.md:F0274；R4.md:F0313；R4.md:F0268；R4.md:F0261。

**第5位｜9. Immortal Star** — 第五選；復出勝且輕磅，但要跨越班次。

支持：Geelong1200米負59.5勝，今54。

風險：僅BM84窄勝；五月同程Straight Six第十。

證據：R4.md:F0520；R4.md:R0028；R4.md:F0535。

**第6位｜11. Photograph** — 第六選，末段位置上升有加程可能。

支持：Begonia Belle由16位升第五輸2.16；Alinghi第三。

風險：1200米How Now曾明顯落後Inkaruna，好地九戰未勝。

證據：R4.md:F0647；R4.md:F0652；R4.md:F0662；R4.md:F0641。

**第7位｜12. Cripps** — 可改善冷門；未過度提升復出者。

支持：Gold Topaz1200米勝；十戰五勝且以往復出兩勝。

風險：154日未跑、最近跳閘末名，今實負54.5而非54。

證據：R4.md:F0716；R4.md:F0702；R4.md:F0707；R4.md:F0709；R4.md:F0711；R4.md:R0038。

**第8位｜2. Grand Larceny** — 舊G1入位證據強，近況轉差列第八。

支持：Goodwood第三輸0.57；三級上陣以往兩次都勝。

風險：最近同程第14輸6.48，今58.5比多匹輕磅馬蝕磅。

證據：R4.md:F0104；R4.md:F0075；R4.md:F0079；R4.md:R0007。

**第9位｜17. Hankee Alpha** — 中游冷門；泥濘大勝值得留意但不直接外推好地。

支持：10月本場1200米BM78勝六馬位。

風險：轉好地Rising Fast第十，評分78低於主力群。

證據：R4.md:F0850；R4.md:F0851；R4.md:F0840；R4.md:R0048。

**第10位｜4. Watchme Win** — 列第十；最新稍復甦，但贏力未返。

支持：Rising Fast第七輸2.41，明顯先Grand Larceny。

風險：本場三戰未入位、一年未勝。

證據：R4.md:F0205；R4.md:F0198；R4.md:F0202。

**第11位｜15. Piastri** — 中後選；濕地專長較明顯。

支持：本場1200米勝，9月BM84勝。

風險：好地五戰未入位；最新第五輸3.5。

證據：R4.md:F0796；R4.md:F0781；R4.md:F0770；R4.md:F0776。

**第12位｜7. De Bergerac** — 本場老手但近況弱，列後。

支持：本場1200米十戰兩勝三亞一季。

風險：最近第15輸7.48；近幾仗均落敗，需大幅復甦。

證據：R4.md:F0387；R4.md:F0394；R4.md:F0404。

**第13位｜10. La Fracas** — 列尾二；眼罩重戴未知能否反彈。

支持：1200米十二戰六勝，Hareeba曾亞。

風險：最近兩戰第九、第八且大敗；好地較弱，不自行假定Logan Bates額外減磅。

證據：R4.md:F0577；R4.md:F0609；R4.md:F0584；R4.md:F0589；R4.md:R0031；R4.md:F0573。

**第14位｜3. Sir Sway** — 舊高峰甚佳，但近期實戰風險最高。

支持：2025 Goodwood第二；最近1200米跳閘第一。

風險：復出第12輸10.79，近期幾場均落敗；不能靠跳閘勝消除此疑問。

證據：R4.md:F0177；R4.md:F0142；R4.md:F0147；R4.md:F0162。

### 可能改變排序的缺失資訊

- 缺當日風、跑線偏差、臨場狀態及完整分段。
- Stewards空白不能當作冇受阻；RaceL600唔係個體末段。
- 現行磅按Racecard；歷史行是來源記錄負磅，未明示減磅時不假定已扣，也不對不明現役claim自行扣重。

### 資料品質

- Pallaton 8月11日跳閘疑似重複，不當兩次準備。
- 不推定Logan Bates減磅；Cripps已明示0.5超磅。

## R5

**完整固定排序：** 5 Too Darn Discreet → 4 Soverato → 8 Vivy Air → 15 Ocean Bay → 1 Panova → 7 Zuleika → 6 Private Legacy → 10 Jenni's Meadow → 3 Machine Gun Gracie → 13 Perfect Ten → 9 You Wahng → 14 Pillow Fight → 2 Sunset Park → 11 Sun Worshipper → 12 Sun Gift → 17 Classic Gem

**信心：low**。頭二：[5, 4]；前四：[5, 4, 8, 15]。

### 形勢及主要比較

- **Sunset Park、Pillow Fight與Jenni's Meadow互爭前列**：持續步速利Too Darn Discreet、Soverato及有耐力的Ocean Bay；Pillow Fight初試2000米風險較高。（R5.md:F0079；R5.md:F0838；R5.md:F0585；R5.md:F0269）
- **單一領放馬放慢、內檔馬省程**：二檔Soverato與一檔Vivy Air更有利；Ocean Bay外檔若需搶位可能蝕力。（R5.md:R0012；R5.md:R0025；R5.md:R0047）
- Tesio共同基準下，Too Darn Discreet從負60轉56、Soverato由54轉57，7公斤相對轉移值得優先；沒有套固定每公斤馬位係數。
- Ocean Bay最新穩定優於Private Legacy/Jenni's Meadow，但外檔及增1公斤；Vivy Air級數強惟首次2000米。

### 逐匹分析

**第1位｜5. Too Darn Discreet** — 首選；主因今次相對磅位明顯改善及2000米能力已證。

支持：Tesio負60輸2.54，今56；2000米四戰三勝，本場BM100勝Land Legend。

風險：最近兩場第八，首次綁舌作用未知；磅位不等於保證翻盤。

證據：R5.md:F0269；R5.md:R0016；R5.md:F0262；R5.md:F0294；R5.md:F0295；R5.md:F0258。

**第2位｜4. Soverato** — 次選；最新本場同類距離勝最直接。

支持：Tesio十五駒勝，今二檔可慳腳程。

風險：由54增至57，對Too Darn Discreet相對磅差逆轉7公斤；不把上次勝視作必再勝。

證據：R5.md:F0205；R5.md:R0012；R5.md:R0013；R5.md:F0269。

**第3位｜8. Vivy Air** — 第三選；輕磅加級數可爭，但2000米係真正未知。

支持：Craven Plate第五先Panova；Coolmore第三輸0.62；今一檔55。

風險：35戰四勝；首次2000米，內檔後追或要等位。

證據：R5.md:F0458；R5.md:F0503；R5.md:R0025；R5.md:R0026；R5.md:F0451；R5.md:F0449。

**第4位｜15. Ocean Bay** — 第四選；近況持續上升、同程可靠。

支持：近六戰111213，Tesio第三僅輸0.61、2025米先Sun Gift。

風險：十七檔較上次二檔難跑；Soverato今增磅較多但仍有內檔優勢。

證據：R5.md:F0892；R5.md:F0901；R5.md:F0906；R5.md:R0047；R5.md:F0205。

**第5位｜1. Panova** — 第五選；舊2000米Oaks水平高，但近況、磅位及檔位壓低。

支持：Australasian Oaks勝及Queensland Oaks亞。

風險：本季三戰未入位，今59.5且十八檔；最新同場不及Vivy Air。

證據：R5.md:F0056；R5.md:F0046；R5.md:F0016；R5.md:R0003；R5.md:R0004；R5.md:F0458。

**第6位｜7. Zuleika** — 第六選，回2000米有進步可能。

支持：Filante第三；2000米三戰兩勝，2100米Gold Crown勝Sun Worshipper。

風險：今56比最近52多；Queensland Oaks曾遠後於Panova、Soverato。

證據：R5.md:F0395；R5.md:F0388；R5.md:F0410；R5.md:F0415；R5.md:R0023。

**第7位｜6. Private Legacy** — 第七選，近仗差距窄，但外檔及低勝率限制。

支持：Tesio第四僅輸0.67；有2033米勝。

風險：今56比上次54多，十六檔；34戰三勝。

證據：R5.md:F0332；R5.md:F0357；R5.md:R0019；R5.md:R0020；R5.md:F0323。

**第8位｜10. Jenni's Meadow** — 第八選；加程後改善，仍偏位置馬。

支持：Tesio搶前第五僅輸0.69，2000米十戰六次入位。

風險：該途程未勝；今55比上次54多，與多匹前速爭位。

證據：R5.md:F0585；R5.md:F0578；R5.md:R0033。

**第9位｜3. Machine Gun Gracie** — 舊級數有力但本季欠尖銳，列第九。

支持：1900米Epona勝；Naturalism第四僅輸1.36。

風險：最近長途第十、第六，縮程可助但未證，今57多於上仗54.5。

證據：R5.md:F0187；R5.md:F0152；R5.md:F0147；R5.md:F0142；R5.md:R0010。

**第10位｜13. Perfect Ten** — 中後選；內檔有利但2000米尚未證。

支持：Lady's Day Vase第三；全年八戰四勝兩亞一季。

風險：Tesio前置退第十，好地勝績少於軟地。

證據：R5.md:F0780；R5.md:F0772；R5.md:F0775；R5.md:F0769；R5.md:R0041。

**第11位｜9. You Wahng** — 後選；舊2000米入位支持加程，近況未足強。

支持：JRA Plate第二輸0.52；2200米MM Trophy亞。

風險：本季兩場輸逾五馬位，一年未勝；眼罩重戴效果未知。

證據：R5.md:F0552；R5.md:F0567；R5.md:F0522；R5.md:F0527；R5.md:F0519；R5.md:F0511。

**第12位｜14. Pillow Fight** — 後選；可能領放但加程存疑。

支持：Angst領放亞，曾先Vivy Air。

風險：最新1600米領放輸8.85；只勝1250米、未試2000米，今再短休。

證據：R5.md:F0843；R5.md:F0838；R5.md:F0831；R5.md:F0837。

**第13位｜2. Sunset Park** — 可影響步速，列後；磅位變差。

支持：Coongy第三輸0.75；2400米Harry White亞。

風險：Tesio領放第九，今58比上次55.5多；十三檔爭先耗力。

證據：R5.md:F0084；R5.md:F0089；R5.md:F0079；R5.md:R0006；R5.md:R0007。

**第14位｜11. Sun Worshipper** — 列後；同場差距近但長期近況不足。

支持：Tesio第六僅輸1.04；Gold Crown曾亞。

風險：最近六仗未入前三；37戰五勝。

證據：R5.md:F0649；R5.md:F0679；R5.md:F0640。

**第15位｜12. Sun Gift** — 列尾二；專長距離但剛跑重地再出有體力疑問。

支持：2000米十三戰四勝五亞；10月2025米亞。

風險：11月4日重地第六輸7.6，三日再出；Tesio只第七。

證據：R5.md:F0705；R5.md:F0722；R5.md:F0712；R5.md:F0717。

**第16位｜17. Classic Gem** — 末選；舊Oaks表現可提醒勿完全排除，但最新差距大。

支持：ATC Oaks第四僅輸1.64。

風險：Tesio第14、2000米四戰未入位；只一場勝。

證據：R5.md:F1000；R5.md:F0965；R5.md:F0958；R5.md:F0956。

### 可能改變排序的缺失資訊

- 當日風、場地跑線及臨場狀態未知。
- 無完整個體分段及可核實受阻報告；Stewards空白不代表冇受阻。
- 現行磅按Racecard；歷史行是來源記錄負磅，未明示減磅時不假定已扣，也不對不明現役claim自行扣重。

### 資料品質

- Tesio前十差距較近，不能僅依名次認定實力分層。
- Sun Gift11月4日至11月7日為三日；Days欄寫2，採日期。

## R6

**完整固定排序：** 6 Tempted → 7 Joliestar → 4 Caballus → 3 Headwall → 8 Charm Stone → 11 Point Barrow → 9 Skybird → 2 Mazu → 10 Geegees Mistruth → 12 Plaintiff

**信心：medium**。頭二：[6, 7]；前四：[6, 7, 4, 3]。

### 形勢及主要比較

- **Mazu、Caballus及Charm Stone令步速持續**：Tempted、Joliestar及Headwall可利用跟跑/後追；Caballus須避免與Mazu鬥快。（R6.md:F0017；R6.md:F0143；R6.md:F0338；R6.md:F0207）
- **前面節奏平和，Caballus獲順風跑線**：本場同程勝績可縮小與兩匹牝馬距離；仍維持Tempted首選，因近況直接比較較強。（R6.md:F0178；R6.md:F0207；R6.md:F0212）
- Tempted兩次近期直接勝Headwall且Everest先Joliestar，首選有同場證據。
- Headwall最新先Caballus0.4馬位但輕2公斤，今同磅，加上Caballus本場兩勝，鎖Caballus在前；此為判斷而非精確磅值換算。

### 逐匹分析

**第1位｜6. Tempted** — 首選；近期對主要對手直接勝出證據最完整。

支持：Concorde、Premiere、Everest三連勝，近十二月六戰全勝。

風險：未跑Flemington，Everest贏距只0.23，首次直路及跑線仍有風險。

證據：R6.md:F0222；R6.md:F0212；R6.md:F0207；R6.md:F0204；R6.md:F0200。

**第2位｜7. Joliestar** — 次選；高級1200米成績穩定且有本場經驗。

支持：Everest第三只輸Tempted0.58；TJ Smith勝，本場三戰全部入位。

風險：本季兩戰均未勝；未有證據可確定反先Tempted。

證據：R6.md:F0270；R6.md:F0310；R6.md:F0263；R6.md:F0280。

**第3位｜4. Caballus** — 第三選；直路同程勝績及最新復甦重要。

支持：Newmarket本場1200米勝；Russell Balding領放第三輸1.19。

風險：今58.5比Newmarket55多；Everest及Premiere均落後Tempted。

證據：R6.md:F0178；R6.md:F0143；R6.md:R0011；R6.md:F0148；R6.md:F0153。

**第4位｜3. Headwall** — 第四選；穩定頂級接近，但磅位與短休令我揀Caballus略先。

支持：Everest第四輸0.71，最新1300米第二先Caballus。

風險：最新比Caballus輕2公斤、今同磅；一星期再出，1200米未勝。

證據：R6.md:F0085；R6.md:F0080；R6.md:F0081；R6.md:R0008；R6.md:R0011；R6.md:F0073。

**第5位｜8. Charm Stone** — 第五選，近期G1入位兼可跟前。

支持：Manikato第三輸1；Sydney Stakes第四輸1.69。

風險：未參與Everest，跨組比較不確定；最近一年四戰未勝。

證據：R6.md:F0338；R6.md:F0333；R6.md:F0330。

**第6位｜11. Point Barrow** — 第六選，上升快、1200米勝率高。

支持：How Now與Northwood Plume連勝，1200米六戰四勝。

風險：主要牝馬賽轉頂級開放賽；Sangster曾落後Charm Stone及Geegees Mistruth。

證據：R6.md:F0532；R6.md:F0527；R6.md:F0515；R6.md:F0552。

**第7位｜9. Skybird** — 第七選，本場可靠可爭四席。

支持：Gilgai本場勝；本場四戰兩勝一亞一季。

風險：Sydney Stakes第五略後Charm Stone；Gilgai負55今56.5。

證據：R6.md:F0401；R6.md:F0389；R6.md:F0396；R6.md:R0024。

**第8位｜2. Mazu** — 第八選；可帶步速，但對今場最強者有近期落敗證據。

支持：McEwen本場領放亞僅輸0.02，The Shorts勝Joliestar。

風險：Premiere第十輸Tempted6.25，與Caballus同放可能耗力。

證據：R6.md:F0017；R6.md:F0027；R6.md:F0022；R6.md:F0143。

**第9位｜10. Geegees Mistruth** — 第九選，最新反彈仍需升級。

支持：Begonia Belle由後追亞輸0.5；Sangster曾勝Charm Stone。

風險：最新對手較弱，一星期再出；Manikato先前不及Charm Stone。

證據：R6.md:F0459；R6.md:F0484；R6.md:F0469。

**第10位｜12. Plaintiff** — 末選；有潛力但近況及對手級數未足。

支持：PJ Bell1200米勝，Sheraco僅輸0.86。

風險：Premiere第九輸Tempted4.48；首次本場，最新1300米第八。

證據：R6.md:F0616；R6.md:F0596；R6.md:F0591；R6.md:F0579；R6.md:F0586。

### 可能改變排序的缺失資訊

- 當日風、場地跑線及臨場狀態未知。
- 無完整個體分段及可核實受阻報告；Stewards空白不代表冇受阻。
- 現行磅按Racecard；歷史行是來源記錄負磅，未明示減磅時不假定已扣，也不對不明現役claim自行扣重。

### 資料品質

- Geegees Mistruth F0504 NON_STANDARD -9/13，不能視為正常負名次或普通第九。

## R7

**完整固定排序：** 8 Autumn Glow → 2 Lindermann → 1 Tom Kitten → 3 Buckaroo → 4 Sepals → 5 Pounding → 9 Within The Law → 7 El Soleado

**信心：medium**。頭二：[8, 2]；前四：[8, 2, 1, 3]。

### 形勢及主要比較

- **Lindermann領放，Autumn Glow跟前**：三檔Lindermann掌速有利，但二檔Autumn Glow可貼近；後追馬怕慢步速。（R7.md:F0080；R7.md:R0007；R7.md:R0023；R7.md:F0393）
- **Autumn Glow提早施壓**：Tom Kitten、Buckaroo追勢更有發揮；首選有領放及跟前兩種勝法。（R7.md:F0398；R7.md:F0393；R7.md:F0017；R7.md:F0143）
- Autumn Glow近期一哩勝Ceolwulf及Aeliana，較Lindermann有利；承認Lindermann曾2000米先到。
- Lindermann最新直接勝Tom Kitten，因此排先；Tom Kitten本場一哩勝保第三。

### 逐匹分析

**第1位｜8. Autumn Glow** — 首選；一哩高級持續勝績最完整。

支持：1600米四戰全勝；King Charles勝Ceolwulf2.24，十五戰十四勝。

風險：首次本場；本年2000米曾被Lindermann先到，不視為不可敗。

證據：R7.md:F0386；R7.md:F0393；R7.md:F0394；R7.md:F0384；R7.md:F0418。

**第2位｜2. Lindermann** — 次選；狀態佳且可掌步速。

支持：Craven Plate領放勝Tom Kitten；Chelmsford1600米勝Ceolwulf。

風險：Underwood曾大敗；近期1400米對Autumn Glow大敗。

證據：R7.md:F0080；R7.md:F0095；R7.md:F0090；R7.md:F0100；R7.md:F0101。

**第3位｜1. Tom Kitten** — 第三選；近況回勇，本場一哩有頂級勝績。

支持：Craven Plate亞、Epsom季；All-Star Mile同場同程勝。

風險：最近同磅被Lindermann擊敗0.97；眼罩重戴未證有助。

證據：R7.md:F0017；R7.md:F0022；R7.md:F0052；R7.md:F0006。

**第4位｜3. Buckaroo** — 第四選；最新本場一哩亞較次線馬可靠。

支持：Crystal Mile第二只輸0.5；Futurity曾亞。

風險：一年未勝；最新57今59，Turnbull大敗原因未知。

證據：R7.md:F0143；R7.md:F0188；R7.md:F0140；R7.md:R0011；R7.md:F0148。

**第5位｜4. Sepals** — 第五選；一流1400米表現，一哩仍待證。

支持：Rupert Clarke及Stradbroke均第二。

風險：最新第15輸12.83；一哩兩戰未入位，蹄鐵變化效果未知。

證據：R7.md:F0217；R7.md:F0232；R7.md:F0212；R7.md:F0200；R7.md:F0196。

**第6位｜5. Pounding** — 第六選；可爭位置但等磅較難。

支持：Coongy第四僅輸0.85；Feehan第三。

風險：一年十二戰未勝，Feehan只有六駒。

證據：R7.md:F0270；R7.md:F0275；R7.md:F0267。

**第7位｜9. Within The Law** — 尾二；一哩曾亞，近況不足撐升班。

支持：1600米五戰三亞，Silver Eagle第五僅輸0.93。

風險：Golden Eagle第14輸6.29，七日再出；勝績只至1200米。

證據：R7.md:F0449；R7.md:F0461；R7.md:F0456；R7.md:F0455。

**第8位｜7. El Soleado** — 末選；本場往績好，但現況及等磅級數不足。

支持：本場1600米五戰勝及兩季。

風險：最近BM84第八，之前亦大敗；評分85與115級同負59。

證據：R7.md:F0328；R7.md:F0335；R7.md:F0360；R7.md:F0365；R7.md:R0021；R7.md:R0004。

### 可能改變排序的缺失資訊

- 當日風、跑線及臨場狀態未知；缺個體分段及可核實受阻資料。
- 現行磅按Racecard；歷史行是來源記錄負磅，未明示減磅時不假定已扣，也不對不明現役claim自行扣重。

### 資料品質

- Pounding Grafton Cup -3/11屬NON_STANDARD，不按季軍計。
- El Soleado F0370標800米卻帶1600米時間與15位/10駒，疑串欄，不用作能力證據。

## R8

**完整固定排序：** 1 Cosmic Crusader → 5 Birdman → 10 Aeliana → 3 Sir Delius → 11 Treasurethe Moment → 2 Light Infantry Man → 6 Land Legend → 4 Attrition → 9 Omni Man → 7 Von Hauke

**信心：medium**。頭二：[1, 5]；前四：[1, 5, 10, 3]。

### 形勢及主要比較

- **Land Legend與Light Infantry Man爭放**：持續步速利Cosmic Crusader、Birdman、Aeliana；兩匹前仗同場大退。（R8.md:F0332；R8.md:F0079；R8.md:F0016；R8.md:F0269；R8.md:F0522）
- **前速互讓、Sir Delius眼罩後更主動**：前組保力；外檔後追Cosmic Crusader需早找位，內檔Birdman/Aeliana有利。（R8.md:F0143；R8.md:F0132；R8.md:R0003；R8.md:R0016；R8.md:R0029）
- 維持Cox Plate首三Cosmic Crusader、Birdman、Aeliana；Birdman在Underwood曾勝首選，差距可逆。
- Sir Delius舊高峰足挑戰，但首次眼罩未有實證，未因此升首三。

### 逐匹分析

**第1位｜1. Cosmic Crusader** — 首選；兩次近期本場2000米同組勝最強。

支持：Cox Plate勝Birdman與Aeliana；Turnbull勝，本場兩戰兩勝。

風險：十一檔後追怕慢步速，最近賽程密，恢復程度未知。

證據：R8.md:F0016；R8.md:F0017；R8.md:F0026；R8.md:F0009；R8.md:R0003；R8.md:F0021。

**第2位｜5. Birdman** — 次選；同組近況穩定，一檔可慳程。

支持：Cox Plate亞輸0.75；Underwood勝Cosmic Crusader；Doomben Cup勝。

風險：Caulfield Stakes被Land Legend先到；內檔或需等位。

證據：R8.md:F0269；R8.md:F0279；R8.md:F0304；R8.md:F0274；R8.md:R0016。

**第3位｜10. Aeliana** — 第三選；本場連季、內檔利慳程。

支持：Cox Plate第三輸0.95，Turnbull第三，Ranvet2000米勝。

風險：最近兩次都被Cosmic Crusader先到，今對其磅位無新優勢。

證據：R8.md:F0522；R8.md:F0527；R8.md:F0557；R8.md:R0030；R8.md:R0004。

**第4位｜3. Sir Delius** — 第四選；2000米高峰強，但近況遜首三。

支持：Queen Elizabeth勝Lindermann及Autumn Glow，2000米六戰三勝。

風險：本季第四、第四、第六，首次眼罩不保證提升。

證據：R8.md:F0173；R8.md:F0136；R8.md:F0143；R8.md:F0148；R8.md:F0153；R8.md:F0132。

**第5位｜11. Treasurethe Moment** — 第五選；縮2000米可改善，眼罩不作自動加分。

支持：本場五戰三勝；2000米五戰兩勝一亞一季；Caulfield Cup第七輸3.96。

風險：最新2000米第五輸4.5不及Birdman，首次眼罩反應未知。

證據：R8.md:F0579；R8.md:F0586；R8.md:F0591；R8.md:F0575。

**第6位｜2. Light Infantry Man** — 第六選；本場2000米級數有，最新大敗需解釋。

支持：Australian Cup同程勝、Turnbull第二先Aeliana。

風險：Cox Plate前置退第11輸13.8；與Land Legend同放或耗力。

證據：R8.md:F0119；R8.md:F0084；R8.md:F0079；R8.md:F0332。

**第7位｜6. Land Legend** — 第七選；高峰可勝但波動很大。

支持：Caulfield Stakes領放勝Birdman。

風險：Cox Plate領放退包尾輸18.8，本場七戰未勝。

證據：R8.md:F0337；R8.md:F0338；R8.md:F0332；R8.md:F0325。

**第8位｜4. Attrition** — 第八選；1900米勝有反證，但本場2000米較弱。

支持：Hill Stakes勝Lindermann；Underwood第三。

風險：Cox Plate第九輸10.3；2000米四戰未入位。

證據：R8.md:F0211；R8.md:F0216；R8.md:F0206；R8.md:F0199。

**第9位｜9. Omni Man** — 尾二；本地初跑有進步，今等磅跳升難度大。

支持：Geelong Cup第三輸2，歐洲長途有經驗。

風險：上次54今59、2400縮2000，缺本地WFA爭勝證據。

證據：R8.md:F0459；R8.md:R0027；R8.md:F0474。

**第10位｜7. Von Hauke** — 末選；加程及等磅級數雙重疑問。

支持：Stradbroke第三、Golden Mile勝。

風險：未試2000米，最近一哩第十、第十一，勝績只至1600米。

證據：R8.md:F0425；R8.md:F0440；R8.md:F0388；R8.md:F0395；R8.md:F0400；R8.md:F0394。

### 可能改變排序的缺失資訊

- 當日風、跑線、馬匹恢復及個體分段未知；Stewards空白不代表冇受阻。
- 現行磅按Racecard；歷史行是來源記錄負磅，未明示減磅時不假定已扣，也不對不明現役claim自行扣重。

### 資料品質

- Attrition試閘RaceL600 14.80異常，不使用。
- Omni Man F0479之1609米時間1:14.17異常，不作時間比較。
- Cox Plate標Flemington，忠於凍結輸入，不用外部常識改場地或推定彎位。

## R9

**完整固定排序：** 6 Educated → 10 Tres Magnifique → 2 Esmahli → 19 Lawborough → 16 Salaria → 8 Electric Elvis → 1 Verdoux → 5 Torsheen → 7 Rohesia → 14 Royal Rendezvous → 12 It's A Yes → 9 King Tut → 18 Brave Design → 17 Fission

**信心：low**。頭二：[6, 10]；前四：[6, 10, 2, 19]。

### 形勢及主要比較

- **Educated、Tres Magnifique及Esmahli推步速**：Royal Rendezvous、Verdoux、Electric Elvis可追；Educated需能跟跑避免硬鬥。（R9.md:F0208；R9.md:F0462；R9.md:F0079；R9.md:F0590；R9.md:F0016）
- **直路分組、外側掩護較佳**：Tres Magnifique、Esmahli、Lawborough或同組受惠，但未知偏差，不預先加分。（R9.md:R0028；R9.md:R0006；R9.md:R0051；R9.md:R0002）
- Educated與Electric Elvis最近只差0.2、今兩者各增1公斤；取Educated好地三勝及本場勝，承認實力可能接近。
- Tres Magnifique十月十四日先Lawborough、Verdoux、King Tut；今Lawborough增3、Tres增1，維持次選。
- Salaria53公斤有利，但低班窄勝不足直接升過首四。

### 逐匹分析

**第1位｜6. Educated** — 首選；好地不敗、同程持續接近、直接比較佳。

支持：Seymour勝Electric Elvis與Fission；好地三戰三勝，本場1100米勝。

風險：今59.5比上次58.5增1公斤，爭先或耗力；不額外推定Celine Gaudray減磅。

證據：R9.md:F0208；R9.md:F0209；R9.md:F0202；R9.md:F0243；R9.md:R0016。

**第2位｜10. Tres Magnifique** — 次選；較高班持續入位、同組比較好。

支持：BM88及BM84亞；1100米第三先Lawborough、Verdoux、King Tut。

風險：今58.5增1，十九檔；1100米未勝、首次口銜反應未知。

證據：R9.md:F0472；R9.md:F0467；R9.md:F0462；R9.md:R0029；R9.md:R0028；R9.md:F0455；R9.md:F0451。

**第3位｜2. Esmahli** — 第三選；穩定上升、減磅明確。

支持：BM70勝，本季221，BM78近亞；今減2實負59。

風險：最近勝係低班，本場重地亞輸六馬位，十四檔跑線未知。

證據：R9.md:F0079；R9.md:F0070；R9.md:F0089；R9.md:R0007；R9.md:F0084；R9.md:R0006。

**第4位｜19. Lawborough** — 第四選；最新好地同程勝，但今磅位上升。

支持：Bendigo BM78勝一馬位先Fission；好地五戰三勝。

風險：今58比上次55增3；前次同組後於Tres Magnifique。

證據：R9.md:F0845；R9.md:F0846；R9.md:F0839；R9.md:R0052；R9.md:F0850。

**第5位｜16. Salaria** — 第五選；53公斤與進步空間可爭四席。

支持：連勝1100米處女及復出1000米BM62，六戰五次前三。

風險：最新僅贏0.02、低班；初跑本場及首次單邊眼罩，升班未證。

證據：R9.md:F0670；R9.md:F0655；R9.md:F0656；R9.md:F0646；R9.md:R0042；R9.md:F0648；R9.md:F0644。

**第6位｜8. Electric Elvis** — 第六選；好狀態但好地贏力未證。

支持：近六場121221，最新1100米僅負Educated0.2。

風險：好地七戰未勝，初跑本場，十六檔跑線未知。

證據：R9.md:F0326；R9.md:F0340；R9.md:F0329；R9.md:F0328；R9.md:R0022。

**第7位｜1. Verdoux** — 第七選；本場追近有價值，但今高磅。

支持：Rising Fast十九駒第五輸1.7；1100米三勝。

風險：今減3實負61，仍比上次54多7公斤，短休及後追跑線有變數。

證據：R9.md:F0016；R9.md:F0009；R9.md:R0004。

**第8位｜5. Torsheen** — 第八選；舊級數足，但復出縮程變數大。

支持：Typhoon Tracy亞，Mornington1200米勝。

風險：195日未跑、首次1100米/本場；跳閘名次矛盾，多件裝備移除效果未知。

證據：R9.md:F0170；R9.md:F0160；R9.md:F0143；R9.md:F0138；R9.md:F0145；R9.md:F0146；R9.md:F0134。

**第9位｜7. Rohesia** — 第九選；跳閘準備好，但1100米待證。

支持：最新本場800米跳閘勝，Nitschke1400米勝。

風險：188日未賽、未試1100米，勝績由1212米起。

證據：R9.md:F0272；R9.md:F0292；R9.md:F0270；R9.md:F0265；R9.md:F0271。

**第10位｜14. Royal Rendezvous** — 第十選；輕磅上升但直路未試。

支持：好地1100米BM66勝，今減1.5實負53.5。

風險：二十檔、初跑本場；前次CL1亞輸3.25，班底薄。

證據：R9.md:F0590；R9.md:R0038；R9.md:R0037；R9.md:F0583；R9.md:F0595。

**第11位｜12. It's A Yes** — 第十一選；低班近勝配輕磅可偷位。

支持：Hamilton BM70及Geelong BM66之1100米勝，今56。

風險：本場兩戰未入位，對手比最近更強。

證據：R9.md:F0526；R9.md:F0541；R9.md:R0034；R9.md:F0519。

**第12位｜9. King Tut** — 第十二選；跳閘多勝未化成實戰。

支持：近期三次跳閘勝，舊BM70勝及BM84接近。

風險：復出BM78第九輸2.72，後於Tres Magnifique、Lawborough、Verdoux；初跑本場。

證據：R9.md:F0403；R9.md:F0408；R9.md:F0413；R9.md:F0428；R9.md:F0423；R9.md:F0398；R9.md:F0391。

**第13位｜18. Brave Design** — 尾二；閹後復出或變，但未夠可信排前。

支持：最近900米跳閘勝，本場曾亞季。

風險：153日未跑，前季三場未入位；只一勝、閹馬效果未知。

證據：R9.md:F0782；R9.md:F0775；R9.md:F0780；R9.md:F0779；R9.md:F0773；R9.md:F0771。

**第14位｜17. Fission** — 末選；舊本場勝有，但直接近況比較落後。

支持：Seymour1100米第三，一月本場1200米勝。

風險：最近被Lawborough擊敗2.55，1100米六戰未勝。

證據：R9.md:F0723；R9.md:F0763；R9.md:F0718；R9.md:F0711；R9.md:F0709。

### 可能改變排序的缺失資訊

- 當日風、跑線及臨場狀態未知；缺完整個體分段及受阻記錄。
- 歷史負磅未必標明已扣減磅，不能全作淨負磅精準比較。
- 現行磅按Racecard；歷史行是來源記錄負磅，未明示減磅時不假定已扣，也不對不明現役claim自行扣重。

### 資料品質

- Torsheen F0145寫6/6而F0146列第二，不據此判跳閘強弱。
- Torsheen及Royal Rendezvous一月廿一日往績各重複，不計兩場。
- 只採card明示現役減磅：Verdoux61、Esmahli59、Royal Rendezvous53.5。

## 鎖定聲明

已完成9/9場、105匹active runner；每匹都有支持、反證及精確來源行。所有排序一次鎖定，無結果後改選。若之後出現證據錯誤，只能另寫勘誤，不能修改這份初選。

局限：無法排除未察覺的預訓練知識；九場單日不足證明LLM或旺財優越，更不能據此調權重或加特徵。正式差異分類與賽後失手檢討待父agent hash鎖定後才進行。
