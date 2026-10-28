# EXP-20261024-03 穩膽真價搜尋審計（獨立研究）

- 基準：0fd9944d5ef198b1bbbbc9779c7265647fe869f7。
- 已搜索：EXP-20261022-01/02/03、EXP-20261024-01/02，以及 GitHub Review 20261024；未見同一真價有限搜尋實驗。
- 假設：報價前組合EV篩選或貪心搜尋會漏掉模型估計正EV真價組合。只有真價工程機會數可以本輪驗證；盈利另需前瞻證據。
- B0/B1/B2 既有協議不變；Q0/Q1/Q2另立 family banker-search-v1，永遠 OBSERVE／無注碼／不入正式ROI。

## 凍結設計（新搜尋結果產生前）

Q0：現役 selector，移除單腿edge，保留報價前組合EV，之後真價EV檢查（既有B1規則）。
Q1：同selector及排序，亦移除報價前組合EV，之後真價EV檢查（既有B2候選再以正EV作診斷）。Q1−Q0只檢查提前拒絕。
Q2：同一套嚴格／fallback單腿資格，移除單腿edge，改用有限多組合搜尋；Q2−Q1檢查搜尋變更。未經確認，不影響正式輸出。

每套資格固定取最多18腿，按 estimated_prob 降序、edge降序、odds升序、desc穩定排序；列舉2–4腿合法組合，套用現有唯一球員、同隊總數≤3、同隊PTS≤2及結構限制。每個腿數按「現役聯合機率×單腿乘積價−1」降序，描述排序破和局；按2/3/4腿輪流挑選，嚴格池先於fallback，同一組腿去重。最多12個新增候選報價／場，不按結果追加預算。Q0/Q1另各最多1個，可重用同次生成快取；Q2保留Q0/Q1報價作incumbent，並加最多12個未報價候選。單腿乘積只排序，不當真價、不作硬EV／最低組合價篩選。

所有診斷通過條件：有效賽前精確event／legs／request身份及未過期真實SGM價≥2，現役機率計算EV>0。未取得有效價一律未知，唔假算負EV或零ROI。保存全部報價、勝出組合、資格來源、搜索與截斷數，正結果亦不升為BET。只取最高真價EV候選作每場診斷；搜尋更多會放大估計誤差，必須另驗校準及收益。

## 驗證與判決

工程：凍結baseline向量、預設輸出不變、合成真價反例、時間邊界、真價身份、預算及輸入不變測試；八場官方orchestrator opt-in。唔用已見11日holdout擇參。

前瞻採用：先另定未見確認窗、功效及多重比較規則，按日聚類，真價ROI／全中率校準／回撤／報價覆蓋一起檢查；無交易ROI=null。本輪只能 NEEDS MORE TESTING，無自動採用。

## GitHub 借鑑

- kyleskom 8e36b0b：時間排序及walk-forward log-loss／校準；主要全場市場，不能直接作SGM模型。
- NBA_AI 57445fb：as-of反事實測試、獨立baseline及回放邊界；不將回放視為當時checkpoint預測。
- zuyio 363a64e：盤線殘差概念值得下一個獨立候選；不採用代理盤線、全資料補值及固定-110收益做SGM證據。

## 結果

待工程試跑；尚未改機率、權重或正式門檻。無盈利結論。

## 八場工程實跑結果

| 賽事 | 列舉合法組合 | 已問真價 | 有效價≥2 | 當時最好模型估計EV |
|---|---:|---:|---:|---:|
| BKN_CLE | 473 | 13 | 12 | -4.5% |
| GSW_PHX | 11 | 11 | 8 | -5.2% |
| HOU_ATL | 153 | 13 | 9 | -3.3% |
| MIA_CHA | 7 | 7 | 5 | -11.6% |
| MIL_PHI | 29 | 13 | 11 | -10.8% |
| NOP_DEN | 18 | 13 | 6 | -9.9% |
| SAS_DAL | 25 | 13 | 10 | -5.7% |
| WAS_CHI | 10 | 10 | 5 | -4.1% |

總共列舉726個不重複合法組合（固定短名單內），查詢93個不重複真價，其中93個有效、66個有效真價≥2；Q0／Q1／Q2均0場估計正EV。未問價633個，唔假定負EV。

八場全部通過官方orchestrator、firewall及compile，無部署研究結果。全部賽果未知；無結算收益、唔宣稱改善。更廣搜尋在本次固定預算下未產生正EV機會；工具只保留為隔離審計能力，未替換正式selector。

重跑：`PYTHONDONTWRITEBYTECODE=1 NBA_WC_MODEL_DIR=/Users/imac/WongChoiData/NBA_ML_Dataset/models/v3 python3 .agents/skills/nba/nba_orchestrator.py --date 2026-10-25 --auto --banker-search-audit`。來源與quote會隨時間改變；重現當時結果需使用另存原生輸入／quote審計JSON。資料包：`/Users/imac/WongChoiData/NBA_Research/2026-10-24-banker-search-audit/`。

判決：NEEDS MORE TESTING；正式模型／門檻不變。
