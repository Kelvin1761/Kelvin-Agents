# EXP-20261025-03 跨場 Multi 結構可行性

基準0ac88e6374db43692d851b0a4d665ddb4ba192f1。工程／描述研究，NEEDS MORE TESTING；不採用正式策略。

先搜尋既有 EXP-20261025-01／02、20261024-02／03 及 ML 實驗。固定規則與 input SHA 在研究目錄 Frozen_Protocol.md／Prerun.json；程式 Replay_Daily_Multi.py 不讀 results／settlements。執行前已見當日部分結果，故不是 blind 或 holdout。完整方案見 docs/audits/2026-10-25-nba-selection-flow-and-daily-multi.md。

資料為2026-10-24-banker-search-audit/engineering-preview 的8場原生報價及 market legs。共同知識截止2026-10-24T12:28:07.717951+00:00，早於最早開賽2026-10-25T09:10:00+11:00；只保留一致 C identity／probability、exact player/team/stat/line。每場依概率及固定identity取6腿，枚舉2–4腿，場次／球員不重複，參考乘積價2–3.5。按 joint product、最弱概率、少腿、固定hash排序，第二張排除第一張所有場次，最多2張。

M0保留每腿EV>=0及組合EV>0：0張。M1移除EV閘僅作研究：2張，參考價2.03／2.05556、參考joint .465716／.451451472、參考EV −.05459652／−.072014412。無真實跨場報價或相容性確認，不是可交易建議，不計命中或ROI，不據此改閘／fit模型。toy checks 包括同場、重複球員、低價、NaN、順序不變、兩張場次隔離、場數不足及EV閘。

附帶資料bug檢查：8快照防守top-three47列，off-roster24、known-unavailable4；修正後37列、兩類均0。原始欄位保留，1,471 C概率不變。不是預測改善證據。

下一步：正常抽取時收 opponent per-game／per100+GP（本輪collector不進模型），核實角色／opportunity來源、原生跨場quote，先固定前瞻／消融與判決方案再量表現。證據根 `/Users/imac/WongChoiData/NBA_Research/2026-10-25-selection-flow-and-daily-multi/`；測試及發佈結果由該目錄 Final_Verification.json 記錄。
