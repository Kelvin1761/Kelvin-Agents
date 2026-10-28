# NBA 旺財：GitHub 借鑑與真價搜尋審計

範圍：以0fd9944d為基準，既有正式穩膽門檻／C機率不變。新增opt-in研究，唔代表採納新投注模型。

## GitHub 更新核對

2026-10-24重新經GitHub API核對三個repo預設分支HEAD，同先前審閱一致；未執行第三方程式或移植模型。

| 專案 | 固定SHA | 今次借鑑／適配 | 唔直接採用嘅原因 |
|---|---|---|---|
| kyleskom/NBA-Machine-Learning-Sports-Betting | 8e36b0b72ecc5082aa8976dff742cdf910b3aa36 | 日期排序、walk-forward log-loss及獨立校準；旺財沿用既有C機率，搜尋唔重新fit／上調機率 | 主做全場moneyline/totals，並非球員SGM盈利證據 |
| NBA-Betting/NBA_AI | 57445fbf8bf9ffae80ede46d073fe5c8cb9554de | as-of反事實測試；新增研究測試拒絕未來／錯event／過期quote，保存輸入SHA與模型身份 | 歷史特徵回放不等於模型checkpoint當時已存在，不能照搬收益宣稱 |
| zuyio/nba-model | 363a64e263b1c39b38d449f1a2bc15a7ee7a9939 | 盤線殘差、趨勢及按edge分層值得另立研究；使用每注真價而非固定-110估ROI | props回測全資料median補值、按球員排序切窗、代理盤線及push處理有疑點；本輪不移植 |

源碼：
- [kyleskom 訓練／驗證](https://github.com/kyleskom/NBA-Machine-Learning-Sports-Betting/blob/8e36b0b72ecc5082aa8976dff742cdf910b3aa36/src/Train-Models/XGBoost_Model_ML.py)
- [NBA_AI as-of tests](https://github.com/NBA-Betting/NBA_AI/blob/57445fbf8bf9ffae80ede46d073fe5c8cb9554de/tests/test_as_of.py)
- [zuyio props backtest](https://github.com/zuyio/nba-model/blob/363a64e263b1c39b38d449f1a2bc15a7ee7a9939/player_props.py#L1091)

## 實作

官方orchestrator `--banker-search-audit`，強制不部署；正常排程預設不啟用。Q0=報價前組合EV閘、Q1=真價後判EV、Q2=有限多組合真價搜尋。單腿edge移除只限呢個研究，其他資格沿用原嚴格／fallback；正式selector仍保留全部原門檻。

每個資格池最多18腿，列舉合法2–4腿；按固定代理EV排序並輪流涵蓋腿數，最多12個額外新quote／場，加最多2個基準quote，去重重用。單腿乘積只供排序，唔當真價。保存全部嘗試同未報價數，缺價係未知；正EV只指模型估計，永遠OBSERVE、不入正式ROI。

共享資格過濾係機械重構：8個凍結原版向量仍一致；76個既有頂層函數AST不變，包括機率及相關性計算。新增合成反例證明工具能檢出「乘積價負EV但真價正EV」與「貪心候選失敗但另一組合成功」；合成反例唔係實際市場機會或收益證據。

## 解讀限制

有限搜尋唔係證明全市場冇正EV，真價成功唔係盈利證據；搜尋更多會放大機率估計誤差。唔將今次八場工程預覽當前瞻確認集，唔用其結果擇參。B0/B1/B2既有協議不變。新搜尋需要另定確認窗／功效／多重比較及按日聚類收益／校準評估，先可以考慮正式採用。

如果有限搜尋仍冇機會，下一個優先係證明新訊號有超越市場價格嘅樣本外資訊，而唔係提高估計機率或要求每場必有BET。殘差／分鐘產出模型可另立候選，必須先檢查真實賽前盤線、訓練資料時間邊界及現有舊實驗。

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
