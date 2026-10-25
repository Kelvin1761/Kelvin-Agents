# Prop 專屬機會量及選中腿校準

基準 ee26e995fc5eb0ab230173330d79d3afda00a3a5。承接EXP-20261025-04：full情境模型沒有證明勝市場，selected子集高估近20pp。本輪先修資料與監測；**沒有fit新概率模型、沒有改C／EV／selector，沒有新盈利結論**。

## 每種prop自己的資料及公式分解

共用的是「預計分鐘→機會量→轉化→分布／milestone概率」流程，各prop消費不同來源，不能一套防守分數套用全部。

| Prop | 專屬來源／特徵 | 未經驗證的模型分解 |
|---|---|---|
| PTS | 2PA、3PA、FTA每分鐘、各自命中效率、USG%、對手容許得分／100回合 | 分鐘×(2×2PA率×2P轉化＋3×3PA率×3P轉化＋FTA率×FT轉化) |
| AST | potential assists每分鐘、同一passing來源的AST轉化、touches、持球時間、AST%、對手容許助攻 | 分鐘×potential-assist率×轉化率 |
| REB | 攻／防籃板機會與各自轉化、爭搶比例、對手自己投失球量／攻板、對手容許籃板 | 分鐘×(攻板機會率×轉化＋防板機會率×轉化) |
| 3PM | 3PA每分鐘、3P轉化、catch-and-shoot／pull-up出手、對手容許3PA／3PM | 分鐘×3PA率×3P轉化 |

這些首先是可稽核的分解。用同一批已實現數據做rate×conversion會約掉，不能因此聲稱產生新預測力。下一版需要只用更早資料預測分鐘、未來機會量及未來轉化，逐項學習及消融，再形成count分布與校準概率。季初GP1–3不支持直接相信原始效率；轉隊、角色、傷停、分鐘不確定性和基準收縮都需新協議。

對手自己FGA−FGM影響我方防板機會；OPP_FGA−OPP_FGM是該隊容許對方投失，不能當成同一件事。AST/POTENTIAL_AST只能用同一passing row；不拿GP1的touches配GP2的助攻做轉化。0機會時rate可為0、轉化率為null；失去來源／樣本不明也不是0。

## 工程接線

新增nba_opportunities.py：NBA整聯盟5個player tracking模式（Passing、Rebounding、Possessions、CatchShoot、PullUpShot），加player Base PerGame及team自身Base Per100，共7來源。保留全部返回欄位與GP／MIN、query、season、cutoff、capture、row及source hash。只用請求球季，不用上一季追補假裝當季。

正常extractor在預載後捕獲，按NBA player ID＋當前team exact join；NBA team ID查對手，不用ESPN team ID。未知／歧義／GP0／MIN0、錯季／錯cutoff、當場US日或之後history、捕獲已過開賽都標明原因。歷史box arrays亦須日期早於US事件日及長度對齊。當季Base有效時作得分／三分率來源，否則僅可用已驗證日期的L10 reference。USG／AST%繼承game package來源，需連meta.data_sources核對fallback，不能把裸數字當已完成獨立PIT驗證。

每名球員新增opportunity_features，包含每prop特徵／缺項、來源行及原始樣本、公式分解，model_input_enabled=false；沒有p或EV。game meta新增opportunity_health，逐來源status及逐欄非空數，避免optional feed死掉卻只見到key。C及report／selector原始碼逐位不變。

NBA_Opportunity_Sources.json以原子寫入、內容hash、同season／cutoff及30分鐘快取，供逐場子程序重用。無官方賽事不打新API；WC_NBA_OPPORTUNITIES=0停新capture。API失敗明列，不作成功值。scheduler的immutable snapshot包含這個optional原始來源檔，game package本身亦保留自身相關row，後續ML可驗原生賽前內容。沒有新增獨立背景排程；既有正常extractor下次運行即會記錄。

原opponent collector缺少OPP_FG3A／OPP_FG3M，本輪實際coverage捉到全空，已補入；補capture時間，舊快照沒有時間不能事後冒充當時已驗證。

## 真實未開賽來源驗證

只讀官方ESPN下一悉尼賽日2026-10-26，7場均未開賽，最早08:00+11。來源cutoff10/24/2026。7類全部available，配對到175個provider已觀察player-game；**不是完整官方roster覆蓋**，沒有盤口、分鐘預測或投注候選。

| 實際欄位 | 非空／175 |
|---|---:|
| 2PA／3PA／FTA每分鐘、USG% | 175 |
| potential assists每分鐘 | 157 |
| potential-assist轉化 | 129 |
| touches／持球時間 | 157 |
| AST% | 175 |
| 攻／防籃板機會 | 143 |
| 攻板轉化／防板轉化 | 123／135 |
| catch-and-shoot／pull-up 3PA率 | 120／120 |
| 對手自己投失、容許PTS／AST／REB／3PA／3PM | 175 |

部分轉化缺項源於零attempt denominator或provider null，不能亂補。歷史L10沒有在此新來源試驗另拉，所以沒有宣稱完成分鐘／角色穩定預測。第一輪缺3PM的原檔保留，v2補完整後另存，不覆蓋失敗紀錄。

## 選中腿校準監測

原nba_reliability雖列picked摘要，警報只看全體／高概率區。本輪增加current probability_model_id下、latest pretip selector-selected cohort自己的picked_status、按stat摘要、已結算事件數；**picked代表selector選中，不代表實際投注或注碼**。不將舊模型／未標版本／較舊snapshot拉返來湊樣本。

沿用現有100已結算腿及10pp差距作監測政策；選中腿額外至少10個有p_final及label的獨立事件才判狀態。這是操作警報，不是獲利／統計顯著性／promotion閘。全體校準正常但選中腿偏差過大也會alert，報告會印出該子集。多腿同場不當獨立100場，不fit或自動改概率。

只讀現役ledger本輪觀察：選中已結算腿3條／1事件，平均p .5147、hit 1.0，狀態insufficient_n。這不是C低估的結論。EXP-04的32條研究單腿與此現役cohort不同，不混算；其57.4%預測對37.5%命中仍只作舊開發診斷。

## 證據及驗證

外置根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-prop-opportunities-20261025`。
Protocol、官方future schedule、NBA_Opportunity_Sources、首次及v2 readiness／逐player-game features、opponent／advanced context、Replay_Readiness.py、C身分檢查、current ledger report。沒有用新賽果、沒有開舊terminal、沒有以本日結果調權重。

targeted覆蓋ID／team／US cutoff／GP／單位／0機會／缺來源／快取篡改／disable、normal extractor附欄與source-health、raw snapshot hash、global正常但picked偏差的反例、少事件及舊模型排除。完整測試、release SHA及啟用結果記在證據根Final_Verification.json。

後續驗證順序：先累積不可變新特徵與嚴格Final labels；固定train／calibration／未見forward，按prop獨立逐block測；比較市場／C／機會量模型的全體及固定選中子集校準。單腿過關後才驗SGM聯合概率與原生組合價。沒有資料支持前不把上述原始分解直接當下注公式。
