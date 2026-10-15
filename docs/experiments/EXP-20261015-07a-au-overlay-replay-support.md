# EXP-20261015-07a — 獨立評估重播 schema 支援

為用戶要求啟用嘅逐駒全程候選，先獨立發佈評估工具相容層。
`au_eval`同`au_matrix_refit`讀取明列嘅`full_time`／`full_time_speed_feature`，
作固定已輸入overlay加回score；欄位不存在時＝0，舊資料所有得分不變。

冇新增來源、冇建立候選特徵、冇改實際production engine／權重／排序，
亦冇改Gold／Good／Pass、bootstrap、時間窗、split或任何判決門檻。
呢個係避免新引擎輸出日後被舊重播工具靜靜丟掉嘅schema修正。
獨立發佈係Central按檔名分類evaluation所需，模型／dashboard另一次release。

基準`7a962be5`；新增4項正／負／中性overlay及缺欄位相容測試。
完整gate同發佈結果以Central immutable manifest為準。
