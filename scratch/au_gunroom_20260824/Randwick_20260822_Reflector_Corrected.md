# Unified AU Race Reflector Report

## Workflow Summary
- Domain: `AU`
- Meeting: `2026-08-22 Randwick Race 1-10`
- Reflected races: `1, 2, 3, 4, 5, 6, 7, 8, 9, 10`
- Results file: `Race_Results_Reflector.md`
- Approval gate: **任何 improvement suggestion 只供審批，不會自動改 code / matrix。**

## Meeting Performance Summary
- Gold: 0
- Good: 0
- Pass: 4
- 1 Hit: 5
- Miss: 1
- Top 5 包齊實際前三: 3/10 (30.0%)
- Top 5 包至少兩匹實際前三: 6/10 (60.0%)
- 冠軍在模型 Top 5: 9/10 (90.0%)
- 平均每場 Top 5 包實際前三匹數: 1.9

## What The Model Did Well
- 至少 2/3 Top picks 入實際前三的場次有 4 場。
- Top 5 shortlist 有 6/10 場包到至少兩匹實際前三，平均每場包 1.9 匹。

## What The Model Missed
- 完全 Miss 場次有 1 場，代表綜合戰力分前列排序仍有結構性落差。
- 只有 1 Hit 的場次有 5 場，通常屬排序未夠準而唔係完全冇訊號。

## Race 1
- Performance label: **Pass**
- Model Top 3: #3 Gunroom, #1 Clear Proof, #16 Isawyou
- Model Top 5 shortlist: #3 Gunroom, #1 Clear Proof, #16 Isawyou, #12 Let's Go Again, #15 Twinkling Star
- Actual Top 3: 1. #1 Clear Proof, 2. #16 Isawyou, 3. #18 Call Me Sassy
- Top 5 shortlist coverage: 2/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Actual Top 3 outside model Top 5: #18 Call Me Sassy
- Missed Top 3 horses:
  - #18 Call Me Sassy: 模型失誤。 原模型排第 7， 隱藏訊號 `賽績線 / 段速`， 短板 `rating_score / 騎師`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
- Race verdict: 帶有可寬恕元素或非純模型錯誤

## Race 2
- Performance label: **1 Hit**
- Model Top 3: #5 Mrs Goldberg, #9 Dee Dee Express, #4 Zubba Storm
- Model Top 5 shortlist: #5 Mrs Goldberg, #9 Dee Dee Express, #4 Zubba Storm, #14 Kakoda, #19 Parthenope
- Actual Top 3: 1. #5 Mrs Goldberg, 2. #15 Empress Tsarina, 3. #18 Lovecats
- Top 5 shortlist coverage: 1/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Actual Top 3 outside model Top 5: #15 Empress Tsarina, #18 Lovecats
- Missed Top 3 horses:
  - #15 Empress Tsarina: 模型失誤。 原模型排第 13， 隱藏訊號 `段速 / 信心`， 短板 `練馬師 / 騎師`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強段速 / 試閘 / 速度訊號
  - #18 Lovecats: 模型失誤。 原模型排第 8， 隱藏訊號 `賽績線 / 信心`， 短板 `pace_figure_score / rating_score`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
- Race verdict: 偏向 clean model failure

## Race 3
- Performance label: **1 Hit**
- Model Top 3: #3 Le Troisir, #1 Captain Fenkel, #2 I Park
- Model Top 5 shortlist: #3 Le Troisir, #1 Captain Fenkel, #2 I Park, #7 Skycatcher, #10 Trapalanda
- Actual Top 3: 1. #6 Foire De Trone, 2. #3 Le Troisir, 3. #4 Golden Century
- Top 5 shortlist coverage: 1/3 actual Top 3; winner in Top 5: No
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Actual Top 3 outside model Top 5: #6 Foire De Trone, #4 Golden Century
- Missed Top 3 horses:
  - #6 Foire De Trone: 模型失誤。 原模型排第 6， 隱藏訊號 `近況 / 段速`， 短板 `pace_figure_score / 人馬配搭`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 細化檔位 / 步速 / 場地偏差 context
  - #4 Golden Century: 模型失誤。 原模型排第 7， 隱藏訊號 `信心 / 騎師`， 短板 `pace_figure_score / 步速形勢`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
- Race verdict: 偏向 clean model failure

## Race 4
- Performance label: **1 Hit**
- Model Top 3: #1 King Of The Sea, #10 Cosmeena, #2 The Creator
- Model Top 5 shortlist: #1 King Of The Sea, #10 Cosmeena, #2 The Creator, #14 Barking Mad, #9 Puntin
- Actual Top 3: 1. #1 King Of The Sea, 2. #9 Puntin, 3. #16 Anthracite
- Top 5 shortlist coverage: 2/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Actual Top 3 outside model Top 5: #16 Anthracite
- Missed Top 3 horses:
  - #9 Puntin: 模型失誤。 原模型排第 5， 隱藏訊號 `信心 / 場地`， 短板 `performance_quality_score / pace_figure_score`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 細化檔位 / 步速 / 場地偏差 context
  - #16 Anthracite: 模型失誤。 原模型排第 11， 隱藏訊號 `信心 / 場地`， 短板 `performance_quality_score / rating_score`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 細化檔位 / 步速 / 場地偏差 context
- Race verdict: 偏向 clean model failure

## Race 5
- Performance label: **Pass**
- Model Top 3: #2 Thebudgiesmugla, #9 So You Are, #5 Boniface
- Model Top 5 shortlist: #2 Thebudgiesmugla, #9 So You Are, #5 Boniface, #1 Changingoftheguard, #7 Matusalem
- Actual Top 3: 1. #5 Boniface, 2. #9 So You Are, 3. #7 Matusalem
- Top 5 shortlist coverage: 3/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Missed Top 3 horses:
  - #7 Matusalem: 模型有訊號但低估。 原模型排第 5， 隱藏訊號 `段速 / pace_figure_score`， 短板 `路程 / 騎師`。
  - 原因: 其實模型已經將呢匹馬放喺前列邊緣，只係未能推入 Top 3，較似權重排序問題多過完全 miss。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強段速 / 試閘 / 速度訊號
- Race verdict: 帶有可寬恕元素或非純模型錯誤

## Race 6
- Performance label: **1 Hit**
- Model Top 3: #2 Apocalyptic, #1 Savvy Hallie, #9 Gatwick
- Model Top 5 shortlist: #2 Apocalyptic, #1 Savvy Hallie, #9 Gatwick, #6 Prima Bella, #5 Catch The Glory
- Actual Top 3: 1. #6 Prima Bella, 2. #8 Stardom, 3. #2 Apocalyptic
- Top 5 shortlist coverage: 2/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Actual Top 3 outside model Top 5: #8 Stardom
- Missed Top 3 horses:
  - #6 Prima Bella: 模型失誤。 原模型排第 4， 隱藏訊號 `近況 / 場地`， 短板 `pace_figure_score / 騎師`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
  - #8 Stardom: 模型失誤。 原模型排第 6， 隱藏訊號 `賽績線 / 試閘`， 短板 `performance_quality_score / rating_score`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
- Race verdict: 偏向 clean model failure

## Race 7
- Performance label: **1 Hit**
- Model Top 3: #1 Cherry Bomshell, #2 Pembrey, #3 Agrarian Girl
- Model Top 5 shortlist: #1 Cherry Bomshell, #2 Pembrey, #3 Agrarian Girl, #11 Screen Icon, #4 By Choice
- Actual Top 3: 1. #2 Pembrey, 2. #5 Bangkok Hottie, 3. #7 Global Goal
- Top 5 shortlist coverage: 1/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Actual Top 3 outside model Top 5: #5 Bangkok Hottie, #7 Global Goal
- Missed Top 3 horses:
  - #5 Bangkok Hottie: 模型失誤。 原模型排第 8， 隱藏訊號 `賽績線 / 近況`， 短板 `騎師 / 練馬師`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
  - #7 Global Goal: 模型失誤。 原模型排第 6， 隱藏訊號 `近況 / 賽績線`， 短板 `pace_figure_score / rating_score`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
- Race verdict: 偏向 clean model failure

## Race 8
- Performance label: **Pass**
- Model Top 3: #8 Campione D'italia, #1 Midnight In Tokyo, #7 Matcha Latte
- Model Top 5 shortlist: #8 Campione D'italia, #1 Midnight In Tokyo, #7 Matcha Latte, #3 Enriched, #9 Soothsayer
- Actual Top 3: 1. #1 Midnight In Tokyo, 2. #9 Soothsayer, 3. #7 Matcha Latte
- Top 5 shortlist coverage: 3/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Missed Top 3 horses:
  - #9 Soothsayer: 模型失誤。 原模型排第 5， 隱藏訊號 `段速 / 賽績線`， 短板 `rating_score / 人馬配搭`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
- Race verdict: 帶有可寬恕元素或非純模型錯誤

## Race 9
- Performance label: **Pass**
- Model Top 3: #8 Autumn Glow, #9 Aeliana, #14 Sheza Alibi
- Model Top 5 shortlist: #8 Autumn Glow, #9 Aeliana, #14 Sheza Alibi, #10 Fangirl, #2 Gringotts
- Actual Top 3: 1. #8 Autumn Glow, 2. #14 Sheza Alibi, 3. #2 Gringotts
- Top 5 shortlist coverage: 3/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Missed Top 3 horses:
  - #2 Gringotts: 模型失誤。 原模型排第 5， 隱藏訊號 `試閘 / 段速`， 短板 `pace_figure_score / performance_quality_score`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 細化檔位 / 步速 / 場地偏差 context
- Race verdict: 帶有可寬恕元素或非純模型錯誤

## Race 10
- Performance label: **Miss**
- Model Top 3: #1 Columbia Blue, #7 Call Me Gorgeous, #2 Sovereign Hill
- Model Top 5 shortlist: #1 Columbia Blue, #7 Call Me Gorgeous, #2 Sovereign Hill, #11 Hidrix, #8 Exit Fee
- Actual Top 3: 1. #2 Sovereign Hill, 2. #13 Ernaux, 3. #12 Love Shuck
- Top 5 shortlist coverage: 1/3 actual Top 3; winner in Top 5: Yes
- Incident / forgiveness: **資料不足** — AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。
- Actual Top 3 outside model Top 5: #13 Ernaux, #12 Love Shuck
- Missed Top 3 horses:
  - #13 Ernaux: 模型失誤。 原模型排第 8， 隱藏訊號 `近況 / 場地`， 短板 `pace_figure_score / rating_score`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 細化檔位 / 步速 / 場地偏差 context
  - #12 Love Shuck: 模型失誤。 原模型排第 12， 隱藏訊號 `pace_figure_score / 賽績線`， 短板 `騎師 / rating_score`。
  - 原因: 現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。
  - 是否有足夠歷史證據: 有
  - 建議測試方向: 加強班次 / 路程 / form line interpretation
- Race verdict: 偏向 clean model failure

## Backtested Improvement Suggestions
- 今次未有可用 backtest candidate。

## Recommended Next Step
- 先審核今份反射報告與 backtest evidence。
- 如你批准某個 suggestion，我哋先會再做 code / matrix 更新。
- 無批准之前，最終排名仍以現行 `綜合戰力分` 排序結果為準，唔會有任何 override。
