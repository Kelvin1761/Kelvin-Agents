# NBA ML 工具（v2）

現役最終機率係 NBA C 層；舊 v3 ML 只作未驗證 shadow。舊 AUC 0.9391 來自錯誤嘅隨機逐盤切分，唔可用作 OOS／晉升證據。修正實測及拒絕候選見 `docs/experiments/EXP-20261023-06-nba-verified-temporal-ml-rebuild.md`。

v2 共用 27 個數值特徵，只用賽前可驗證資料及有報價嘅整數 milestone。US 日期／事件切分，缺值處理 fit 喺每個訓練窗，Pipeline 一併保存。冇分類欄位 encoder、冇全池 median、冇 row shuffle、冇 terminal early stopping、冇自動晉升。

## 建資料

正常本地 archive（有 hash-matched `_prediction_snapshots/*/manifest.json`）可用：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/nba_ml/build_nba_ml_dataset.py --output-dir <新資料目錄>
```

每個事件用自己 US 日期配賽果。`--skip-fetch` 唔打網絡，但可用新輸出目錄已有嘅 Final cache；來源／Final 驗證永遠唔跳過。缺 immutable 證據或冇實價嘅列會保留 unverified／template 標示，trainer 會拒絕，唔冒充訓練資料。輸出目錄必須全新，唔覆蓋原 dataset。

外部 archive 有獨立來源 receipts 時用：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/nba_ml/build_verified_nba_dataset.py --manifest <賽前來源 manifest.json> --labels <已核對 Final labels.json> --output-dir <新資料目錄>
```

實際 schema 及範例見本次 audit 外置根嘅 `strict_priced_manifest.json`／`verified_results/verified_labels.json`。工具會重新驗來源 hash、事件主客身份、Final 及原始 boxscore 數字，唔只信一個「verified」旗標。DNP／缺 label 唔當 miss。

## 訓練及重現

```bash
PYTHONDONTWRITEBYTECODE=1 NBA_WC_PROB_LAYER=1 python3 .agents/scripts/nba_ml/train_nba_xgboost.py --dataset <新資料目錄>/dataset.csv --output-dir <新候選目錄> --skip-shap
PYTHONDONTWRITEBYTECODE=1 NBA_WC_PROB_LAYER=1 python3 .agents/scripts/nba_ml/backtest_nba_ml.py --dataset <新資料目錄>/dataset.csv --model-dir <候選目錄> --output-dir <新回測目錄>
```

檔名保留舊 CLI compatibility；classifier 係 XGBoost 可用就用佢，否則 RandomForest，metadata 會寫實際類型。固定尾 20% **日期**只作 terminal diagnostic，前段五折 expanding time validation；已看過嘅歷史窗唔會變成新盲測。每個新輸出目錄都唔覆蓋舊結果。

`model.pkl` 係 fitted imputer＋classifier；`feature_names.json` 綁定 model hash、特徵 constructor hash、訓練截止日。`metrics.json` 記錄日期／場數／人口／配對 benchmark。backtest 排除模型訓練日及之前嘅事件，亦會標示 historical terminal reproduction。

新 artifact 一律 `deployment_eligible=false`。明確要求 live ML 或開 hybrid ML 調整時，未具資格／載入或預測失敗會停止報告；唔會靜靜改做另一個模型。歷史 v3 可以繼續 shadow，唔會變成已批准模型。今次新 RF 輸畀現役 C，權重只留外置診斷目錄，冇部署。

C 層啟用時會覆蓋 upstream legacy／hybrid 機率；報告另列實際最終來源。`--legacy` 唔代表自動關閉 C。重現純 legacy 研究要明確設定 `NBA_WC_PROB_LAYER=0`，亦唔代表該研究已獲模型晉升。
