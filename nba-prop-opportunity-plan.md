# Prop 專屬機會量與選中腿校準

- [x] 先核對現有 raw tracking／GP／單位，凍結工程驗證範圍，不重開舊terminal。
- [x] 新增按 player ID＋team 精確配對的來源、時間／cutoff、樣本及缺失合約；共用有時效快取。
- [x] PTS拆2PA／3PA／FTA與效率；AST用potential assists與轉化；REB拆攻／防籃板機會與對手投失；3PM拆出手、catch-and-shoot／pull-up。
- [x] 接入正常抽取及immutable snapshot，只記錄專屬特徵，無新增概率／EV或選腿修改。
- [x] 修正校準監測只看全體的缺口：selector選中腿獨立報樣本／事件數／差距及警報；不可冒充實際投注。
- [x] 研究資料重播並驗證新欄位覆蓋、真實來源、以及已選子集與整體校準差距；不fit選中腿結果。
- [x] targeted／quick／full通過後exact-scope保存與啟用，保留C baseline與回退。

- 驗證及啟用SHA以外置Final_Verification.json為準；新feature不進正式概率、原始分解不當已驗證模型。
