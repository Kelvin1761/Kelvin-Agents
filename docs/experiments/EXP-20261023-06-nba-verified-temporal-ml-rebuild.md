# EXP-20261023-06 NBA 訓練／推論／回測資料合約修正

**結論：資料及評估工具修正；RandomForest 候選不晉升。** 現役 C 層係數、v3 model artifact、評估合約均未改。呢個唔係模型表現改善聲稱。

承接原審核 F06 及 `EXP-20261021-01`：舊 v3 AUC 0.9391 來自隨機 player×stat×line 切分，唔可以引用為 OOS 成績。原記錄已要求正確對手、實價母體、時間／事件切分及配對評估。其他已有記錄（EXP-20261021-02～08、EXP-20261022-03）嘅限制及已見歷史窗照保留，唔改尺、唔救候選。

## 修正

- `nba_ml_features.py` 成為 v2 共用 27 個數值特徵建構器；對手係真正另一隊，L10 統計由對應歷史陣列重建，傷停紅利由該快照狀態計。缺值保持缺值；類別欄位冇訓練，就唔再聲稱已編碼入模型。市場價只作標籤母體／benchmark，冇偷放入 ML 特徵。
- 舊 builder 改按每場 US 比賽日處理，唔用 UTC 日期或 folder 第一個 JSON 嘅日期。只接納 exact event/date/team/full-name Final 標籤，缺欄位唔當 0，DNP 唔當 miss，0:30 上場唔當 DNP。重用現役 reflector finality 路徑，保留舊賽果檔，修正版另存；每次輸出用新目錄。
- v2 trainer 只接受有實價、賽前來源及 Final 標籤嘅列；重新核對來源 hash、日期、歷史場次與共用特徵，CSV 改數字唔會蒙混過關。重複事件必須先按最早合法來源處理。
- 完整 US 日期切分；dev 內五段 expanding time folds。每個 fold 自己 fit median imputer；全缺 train 特徵以 0 填補，唔讀驗證集補值。終端日期唔做 early stopping、唔 refit 入模型。
- 標準 sklearn Pipeline 一併保存 imputer／classifier；serving 核對 model hash、特徵 constructor hash／次序，唔再用另一套零填補。backtest 只評估模型最後訓練日之後嘅列，重現舊 terminal 會明標 historical reproduction，唔冒充新盲測。
- v3 留作未驗證 shadow。明確要求 live ML／hybrid 調整時，冇通過資格嘅 artifact 或預測失敗會阻止輸出，唔靜靜退回另一個模型。今次所有新候選 metadata 都係 `deployment_eligible=false`。

## 鎖定語料／協議

外置根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-remediation-20261023`。

80 份 raw game data → 55 份有獨立 Drive 修改時間及賽前擷取證據、歷史日期嚴格早於目標日 → 50 份可唯一配對實價。50 份係 **49 個獨立事件／24 個 US 日期**；MIN@SAS 同一場有兩個快照，按最早來源逐列去重，唔靠命中結果揀。

來源交叉核對：55 個 ESPN Final 事件；50 份 summary 成功，5 份 404 以官方 NBA 已完成季後賽 PlayerGameLogs、相同日期／球隊及唯一 NBA game ID 補標籤。966 個球員列兩個來源一致；308 個 DNP 獨立記錄。結果檔只入 label，唔入 features。原有一批 TBD／開賽前文字賽果檔唔再當 Final。

新 dataset 8,468 列，其中 8,286 有可靠標籤；dataset SHA-256：`16b378cd914d1d684609760eb0edbeb6d4648d52a7b5552faba10fd45c3a7e0d`。24 日期尾 20%（5 日期）固定作 terminal diagnostic，前 19 日期 dev。協議預先保存，SHA-256：`4ac407f80dc5e3f31f1cc7e57dc645f2712506da4c06b230a1998dd708b1378c`。RF 仍用 300 trees／depth 10／min leaf 5／balanced_subsample／seed 42，冇 search；兩條 CPU threads 只係執行限制。

**呢批歷史日期曾喺早前研究睇過，唔係新 confirmatory holdout。** 終端 5 日期：2026-05-17、06-03、06-05、06-08、06-10，偏向後段季後賽；唔換日期救候選。有效獨立樣本係 5 場，唔係 942 個獨立投注。

## 固定 terminal 診斷

訓練 7,344 列／44 場；terminal 942 列／5 場。當前環境 XGBoost 不可用，所以實際 classifier 係 RandomForest，metadata／輸出照實記錄。

| 模型／benchmark | Brier（低較好） | ROC-AUC | ML − benchmark Brier：按日配對 95% CI |
|---|---:|---:|---|
| 新 RF | 0.182219 | 0.795819 | — |
| 原始 L10 | 0.187590 | 0.788748 | −0.005371 [−0.011562, +0.000017] |
| 市場 1/price，含 vig | 0.171990 | 0.818129 | +0.010230 [−0.001124, +0.019775] |
| 現役 C（歷史已擬合 comparator） | 0.171071 | 0.817263 | +0.011148 [+0.001562, +0.019958] |

Bootstrap 固定 US 日期 cluster／2,000 次／seed 20261023。C 呢邊曾擬合／檢視歷史窗，唔獨立；不過候選連呢個診斷都輸，所以**唔晉升**。唔會拿相對原始 L10 嘅表面進步當成打贏現役或盈利證據。

CLI 封裝加 model／feature hash 綁定及統一 log-loss clipping 後，同資料／參數／日期重跑一次：所有 tree arrays 逐位一致；predict_proba 只有最多 `2.22e-16` 累加次序浮點差，低於 serving 四位小數。冇調參。第一次輸出保留；正式記錄用修正後一致指標。backtest 成功重現 942 列，排除 7,344 訓練列。

## 重現

```bash
python3 .agents/scripts/nba_ml/build_verified_nba_dataset.py --manifest <外置根>/strict_priced_manifest.json --labels <外置根>/verified_results/verified_labels.json --output-dir <新資料目錄>
PYTHONDONTWRITEBYTECODE=1 NBA_WC_PROB_LAYER=1 python3 .agents/scripts/nba_ml/train_nba_xgboost.py --dataset <新資料目錄>/dataset.csv --output-dir <新診斷模型目錄> --skip-shap
PYTHONDONTWRITEBYTECODE=1 NBA_WC_PROB_LAYER=1 python3 .agents/scripts/nba_ml/backtest_nba_ml.py --dataset <新資料目錄>/dataset.csv --model-dir <診斷模型目錄> --output-dir <新回測目錄>
```

精確數字／hash／切分／人口分佈及拒絕結果：`docs/experiments/evidence/EXP-20261023-06/`。模型權重、原始語料同大輸出只留外置碟，冇 commit／部署。之後如果研究校準或新特徵，要新協議及新 forward 證據，唔准再用呢段 terminal 調參。
