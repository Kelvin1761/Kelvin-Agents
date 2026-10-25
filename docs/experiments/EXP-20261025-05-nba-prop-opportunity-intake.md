# EXP-20261025-05 Prop 專屬機會量接線及選中腿監測

**DATA CONTRACT／MONITORING；無模型fit或採用判決。** 基準ee26e995；C config、report／selector不變。先搜尋EXP25-04及C／RF舊記錄：既有無價模型未贏市場，不能再把更多手工context當增益。

本輪只做normal pipeline來源與監測。Protocol固定在外置證據根，最初列5 tracking＋team Base，實作資料核對增加player Base作同period得分／三分來源；屬工程來源合約擴充，沒有新arm／看結果調參。資料驗證不使用賽果或fit、不重開舊terminal。

PTS分2PA／3PA／FTA與各自效率、AST分potential-assist與轉化、REB分攻防機會與轉化及對手自身投失、3PM分3PA與投射類型。原始rate×conversion是分解identity，**不是預測改善**。所有新feature model_input_enabled=false。完整來源、公式、缺失及限制見docs/audits/2026-10-25-nba-prop-opportunities-and-selected-calibration.md。

未開賽2026-10-26官方7場、175個provider已觀察player-game：來源7/7 available，potential assists157、reb chances143、shooting styles120；對手3PA／3PM首次全空→發現原collector缺欄，補後175。保留首次缺漏及v2證據。不聲稱完整roster或所有特徵已驗證可訓練；季初GP低，USG／AST%需讀fallback來源。

監測新增picked_status／事件數及按stat，沿用100腿／10pp並加10有label及p_final事件守則。全體好而picked壞會報警，不改模型；picked不是實際投注。只讀現役3腿／1場，insufficient_n，不下結論。既有32場研究selected subset不混入現役。

重現：外置根Replay_Readiness.py、Source_Readiness_v2.json、Forward_Opportunity_Features_v2.json、Current_C_Reliability.json、Model_Identity_Check.json。外置根 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-prop-opportunities-20261025`。沒有候選準確率／ROI改善聲稱，後續需新prop-specific時間OOS／消融與選中子集校準。
