# Wong Choi 自動覆盤及模型改良規範

本規範同時適用於 AU Wong Choi 同 HKJC Wong Choi。目標係將每日資料健康、賽後覆盤、Matrix 診斷、ML 研究、候選版本過閘及人手批准部署串成同一條可追溯流程。

## 1. 不可變原則

1. 每場開跑前保存 prediction snapshot、Logic、Scoring CSV、程式版本及資料時間戳；賽後不得覆寫。
2. 賽果只可進入 reflector、evaluation 同 research dataset，不能倒流入該場 pre-race scoring。
3. AU/HKJC 正式排名繼續由既有 Matrix 結構產生。ML 先作 matrix 判讀、交互作用及候選權重研究，不可靜默取代 production score。
4. 缺數據要保持中性並記錄 provenance；不得用零分當作「冇資料」。
5. 候選版本只可自動建立 non-draft PR；任何 production merge 必須由人批准。

## 2. 每日分析健康檢查

每次分析完成、dashboard deploy 之前，必須執行 `racing_data_health.py`：

- Racecard → Facts → Logic runner number 一致
- 馬名及馬號唯一
- 每匹馬都有 `python_auto`、完整 matrix feature、合法 ability score 及連續 rank
- Scoring CSV 行數與 Logic runner 數一致
- AU 每匹馬 data coverage 已記錄；低 coverage 要警告
- 任何 alignment、missing auto、rank 或 output error 都要阻止 deploy
- 結果寫入 meeting folder 嘅 `Data_Health.json` 同 `Data_Health.md`
- Telegram status 必須列出場數、馬數、error、warning 同 coverage；冇錯亦要明示

## 3. 賽後處理

1. 抽取正式賽果並驗證 race、馬號、馬名同 pre-race snapshot 對齊。
2. 先完成 meeting-level reflector，逐場分開：結果、判讀過程、protocol 遵守、可泛化性、改良建議。
3. 分類失誤：熱門漏捉、冷門高排但包尾、scratch／場地變更、資料缺失、matrix 判讀錯、隨機結果。
4. 更新 forward corpus；同時保留歷史 reference corpus，唔可以將 reused historical holdout 當作新 forward proof。

## 4. 每週 review

- 匯總 Gold／Good／Pass、Champion、Winner@3、Winner@5、Top-5 AUC，同上一個 production version 作 paired comparison。
- 按場地、途程、班次、going、field size、新馬／舊馬、熱門／冷門 cohort 檢查 drift。
- 每個 matrix 做 standalone、leave-one-matrix-out、coverage、monotonicity、cohort stability。
- 檢查 matrix crossover：相關性、重複證據、互補 uplift、交互作用是否跨 time split 穩定。
- 樣本不足只可以列為 observation，不可改 production。

## 5. ML 研究與防洩漏

- 全部 feature 必須係 point-in-time；以完整賽日／meeting 切 train、validation、test，禁止同一場拆到兩邊。
- 舊資料可作 training/reference；新季資料作乾淨 forward stream。兩者可以同表展示，但 headline 必須分開。
- ML 優先回答「每個 matrix 點判讀、何時有效、交互作用係乜」，而唔係直接堆一個黑箱 reranker。
- 所有 search、feature selection、calibration 必須只在 train/validation 做；forward set 不可反覆調參。

## 6. 候選過閘

候選需同現行 production 做相同賽事 paired comparison，至少包括：

- Top-5 AUC、Gold／Good／Pass、Champion、Winner@3／5
- bootstrap confidence interval 或等價不確定性
- 無重大 cohort regression
- 對 coverage/missingness 不敏感
- code validation、data health、determinism、no-leakage tests 全過

AU：100 races／5 dates 可開始診斷；300 races／10 dates 先具候選資格。HKJC：舊三個月可作 training/reference；新季至少 8 meetings／約 80–120 races先做正式 forward 診斷，最好 12 meetings／約 180–200 races先考慮 production promotion。若效果大但未夠樣本，只發「繼續觀察」通知。

## 7. Telegram 同批准流程

Telegram 通知分四類：

1. 每日分析完成／失敗及 data-health 摘要
2. 賽果可用、覆盤完成／待處理
3. 每週 performance/drift 摘要及是否需要人手 review
4. 候選過閘：舊版 vs 新版指標、樣本、風險、PR link、rollback 方法

候選通過後系統自動準備 non-draft PR；訊息用「建議批准／繼續觀察／拒絕」表達。只有用戶批准後先 merge 及 deploy。
