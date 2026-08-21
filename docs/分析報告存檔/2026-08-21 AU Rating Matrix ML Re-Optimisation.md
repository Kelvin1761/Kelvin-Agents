# AU Wong Choi Rating Matrix / ML 再優化報告

日期：2026-08-21  
分析範圍：截至 2026-08-20 嘅 AU 歷史資料  
目的：喺同期賽果覆蓋由約 60.8% 提升至 98.1% 後，重跑 Rating Matrix、ML 同投注策略驗證，判斷有冇足夠證據更新現役模型。

## 結論先行

今次增加資料後，**仍然唔應該更換現役 Rating Matrix，亦唔應該將 ML 升做正式模型**。

主要決定：

1. **Rating Matrix：保留現役權重。** 新候選權重喺 development 有少量改善，但 terminal holdout 同 canonical AUC gate 都退步，未達 promotion 標準。
2. **ML：繼續只做 shadow。** XGBoost 同 hybrid 均未能穩定打贏現役 Matrix；XGBoost 喺最終 holdout 明顯較差，hybrid 亦未通過 paired bootstrap gate。
3. **現行投注規則：建議暫停發出正式投注指示。** 2026-08-13 至 2026-08-20 用接近落飛前價格重算，161 注 ROI 為 **-27.84%**，daily-cluster bootstrap 95% CI 為 **[-45.12%, -11.02%]**，負回報已唔似單純隨機波動。
4. **「模型第一名、非市場大熱、位置賠率低於 2.0」候選規則只可繼續 shadow。** 佢將同期虧損收窄至 -5.28%，但信賴區間仍跨過 0，而且真正 post-selection OOS 只有 2026-08-20 一日、7 注，證據不足以正式啟用。

今次只完成離線重跑同決策審核，**冇更改 production 權重、冇提升 ML、冇部署新投注規則**。

## 1. 資料完整性與可用性

用現役 runtime parser 重新建立全套 dataset：

| 項目 | 結果 |
|---|---:|
| 掃描 Logic races | 1,530 |
| 成功對齊賽果 races | 1,411 |
| Runtime runners | 14,109 |
| ML 可用 races | 1,406 |
| ML 可用 runners | 14,063 |
| 日期範圍 | 2025-08-02 至 2026-08-20 |
| Future / target facts 混入 | 0 |
| Duplicate race IDs | 0 |
| Duplicate runners | 0 |
| 整場排除 | 5 場（dead-heat / tie） |

資料狀態為 **READY WITH LIMITATIONS**。同期賽果覆蓋大幅改善，令今次測試比舊版可信；但部分原始 feature 仍然稀疏：recent field percentile 約 23.9%、same-going 約 32.3%、sectionals 約 35.7%–56.8%、same-track 約 49%、current jockey 約 49.5%、rating 約 66.5%。因此，資料量增加唔等於 ML 一定會有突破。

另有 395 場 declared field size 同實際 starter 數量不同，主要係賽前分析名單包括其後退出馬匹，而賽果只包括 starters；檢查未發現因此引入 target leakage。

## 2. 現役 Matrix 基準

### 全歷史樣本（1,411 場）

| 指標 | 結果 |
|---|---:|
| Top-5 AUC | 0.6853 |
| Full-field AUC | 0.6698 |
| Gold | 17.86% |
| Good | 25.37% |
| Pass | 48.19% |
| Winner@3 | 57.26% |
| Winner@5 | 75.76% |
| Top-3 precision | 48.12% |

### 2026-08-13 至 2026-08-20 forward baseline（301 場）

| 指標 | 結果 |
|---|---:|
| Top-5 AUC | 0.6721 |
| Gold | 17.94% |
| Good | 24.92% |
| Pass | 50.17% |
| Champion | 26.25% |
| Winner@3 | 60.80% |
| Winner@5 | 77.74% |
| Top-3 precision | 48.39% |

呢個 forward period 顯示揀馬命中能力本身仍然存在；負 ROI 主要唔係「完全揀唔中」，而係價格、投注篩選同下注時點未能將命中率轉成正期望值。

## 3. Rating Matrix 再優化

先驗證 refit replica 同現役 `map_features_to_matrix_scores`：14,109 runners 最大分數差 0.0033，冇任何 runner 差異大過 0.01，足以用作公平比較。

### 3,000 組候選權重搜尋

候選共識權重：

| Feature group | 候選權重 |
|---|---:|
| Stability | 0.31126 |
| Pace performance | 0.11302 |
| Race shape | 0.13556 |
| Jockey / trainer | 0.25928 |
| Class / weight | 0.13801 |
| Track | 0.04287 |

36/3,000 個候選喺 development 打贏 baseline，只有 5 個通過至少 4/5 development folds。最終候選喺 development 只得輕微改善，但 terminal holdout 出現退步：

| Holdout 指標變化 | 候選 - 現役 |
|---|---:|
| Gold | 0.00 pp |
| Good | +0.47 pp |
| Pass | -2.83 pp |
| Winner@3 | -1.42 pp |
| Top-3 precision | -1.26 pp |
| Top-5 AUC | -0.002925 |
| Full-field AUC | -0.002142 |

Top-5 AUC paired bootstrap 95% CI 為 **[-0.007335, +0.001836]**；full-field AUC 95% CI 為 **[-0.005184, +0.001052]**。兩者都冇證明候選較好，而且 development canonical AUC 已經輕微倒退（-0.000232）。

### Rolling walk-forward

11 個可評估窗口、每個約 92 場。候選 objective 贏 6/11 個窗口，但整體實用指標未改善：

| 指標變化 | 候選 - 現役 |
|---|---:|
| Gold | -0.99 pp |
| Good | -0.89 pp |
| Pass | -1.19 pp |
| Champion | +0.40 pp |
| Winner@3 | +0.49 pp |
| Top-3 precision | -0.30 pp |
| nDCG@5 | -0.09 pp |

結論：局部窗口有小幅增益，但冇跨時段一致優勢，**Matrix promotion gate：FAIL**。

## 4. ML 完整測試

ML dataset 有 1,406 場；最終 chronological holdout 有 510 場、4,630 runners，切割點為 2026-08-08。Development 選出 XGBoost，另測試 25% ML / 75% Matrix hybrid。

### 最終 holdout

| 指標 | 現役 Matrix | XGBoost | Hybrid |
|---|---:|---:|---:|
| Top-1 hit | 26.86% | 22.75% | 27.65% |
| Top-3 hit | 59.22% | 52.55% | 58.04% |
| Top-5 hit | 77.65% | 74.31% | 76.86% |
| Gold | 20.98% | 20.20% | 21.96% |
| Good | 27.65% | 24.90% | 28.43% |
| Pass | 53.14% | 47.45% | 52.35% |
| Win Brier（低較好） | 0.092560 | 0.094383 | 0.092763 |
| Place Brier（低較好） | 0.191906 | 0.195855 | 0.191976 |

XGBoost paired bootstrap：

- Win Brier improvement：-0.001846，95% CI [-0.002896, -0.000783]
- Top-3 hit difference：-6.75 pp，95% CI [-10.59 pp, -3.14 pp]

即係 XGBoost 唔單止未打贏，仲有統計證據顯示較差。Hybrid 雖然 Top-1、Gold、Good 略高，但 Top-3、Top-5、Pass 同 probability calibration 都冇穩定改善，paired bootstrap gate 亦失敗。

Promotion gates：

| Gate | XGBoost | Hybrid |
|---|---|---|
| Probability quality | FAIL | FAIL |
| Top-rank performance | FAIL | FAIL |
| Walk-forward consistency | 3/5 PASS | 4/5 PASS |
| Paired bootstrap | FAIL | FAIL |
| Betting loss tolerance | PASS | PASS |

結論：**KEEP CURRENT MATRIX；ML 繼續 shadow**。

## 5. Full-field 位置投注重算

今次用現役 Logic、最新 canonical results 同 odds history 重新對齊：562 場、5,675 model runners；5,248 result rows 中成功配對 5,242。投注損益分開用 first available price 同 last available pre-race price 計算。

### 2026-08-05 至 2026-08-20

| 規則 | 價格 | 注數 | 命中率 | ROI | Daily-cluster 95% CI | 最大回撤 |
|---|---|---:|---:|---:|---:|---:|
| 現行規則 | First | 376 | 31.12% | -8.57% | [-21.30%, +8.00%] | -41.21u |
| 現行規則 | Last | 342 | 29.24% | -17.16% | [-30.75%, +0.40%] | -60.17u |
| 候選規則 | First | 139 | 59.71% | -3.88% | [-12.62%, +6.29%] | -9.73u |
| 候選規則 | Last | 162 | 58.64% | -6.26% | [-15.77%, +3.38%] | -13.85u |
| 同價位非模型第一名 control | Last | 703 | 47.51% | -21.38% | [-27.10%, -15.70%] | -155.45u |

候選規則係：**模型排名第 1、唔係市場大熱、位置賠率低於 2.0**。

模型第一名喺同一低賠率 band 明顯優於非模型第一名 control，證明模型排序確實有信息量；但市場價格仍然食走大部分優勢，所以「命中率高」仍未等於「正 ROI」。

### 2026-08-13 至 2026-08-20

| 規則（Last price） | 注數 | ROI | Daily-cluster 95% CI |
|---|---:|---:|---:|
| 現行規則 | 161 | -27.84% | [-45.12%, -11.02%] |
| 候選規則 | 99 | -5.28% | [-16.32%, +7.48%] |

現行規則喺呢段時間嘅信賴區間完全低過 0，應視為明確風險訊號。候選規則雖然大幅減少虧損，但未證明有正 edge。

重要限制：候選規則喺之前檢討已經參考過 2026-08-13 至 2026-08-19，所以呢段唔可以當成完全乾淨嘅 post-selection OOS。真正新嘅 OOS 只有 2026-08-20：現行規則 16 注、+6.75%；候選規則 7 注、-35.29%。一日樣本太細，兩邊都唔能夠作結論。

## 6. 點解揀中但仍然輸錢

今次結果再次確認以下模式：

- Rating Matrix 對「邊匹較大機會入位」有真實排序能力；模型第一名喺相同低賠率區間明顯勝過 control。
- 現行投注規則揀得太闊，將大量只有排名訊號、但冇價格優勢嘅馬一併下注。
- Last price 表現普遍差過 first price，反映臨場市場修正、價格壓縮或資料時點問題會侵蝕原有 edge。
- 低位置賠率帶來高命中率，但每次落空要用多次小勝先補回；只要真實命中率稍低過 breakeven，ROI 就會快速轉負。
- 所以核心問題係 **calibration + price discipline + bet selection**，唔係單純增加模型命中率。

## 7. 建議操作

即時：

1. 保留現役 Matrix 權重。
2. ML 維持 shadow，唔進 production。
3. 暫停現行 AU 正式投注指示，或者至少標記為 `NO BET / SHADOW`，直至重新通過 ROI gate。
4. 候選規則只記錄 shadow ledger，唔當作已證實可投注策略。
5. 每注同時保存 first price、decision-time price、last price、實際可成交價及資料 timestamp，分辨係選馬問題定 execution slippage。

下一次 promotion gate：

- 至少再累積 4–6 星期；
- 候選規則至少 500–700 注乾淨 post-selection bets；
- whole-date walk-forward，唔可以 random split；
- daily-cluster bootstrap ROI 下限要高過 0，或者至少達到預先鎖定嘅容忍線；
- 同時要求回撤、賠率時點穩定性、track/venue 分層唔出現單一場地支撐全部盈利。

## 8. 可重現性

核心輸入 / 輸出 SHA-256：

- Historical results CSV：`6886a92a50c34f57a7e642575502ad88f8444f1f6823ed17abe85cb2ce285fd0`
- Runtime dataset：`21b9811a44a3c72c49e8299520d9f408b9d8122e7988917d3266de004cb01539`
- ML dataset：`b63889b49948aea2a824e9ee6993544f85a023c8aa44b05b62e36b61d5450951`
- ML experiment result：`4fa6b1c03f93daaf3284780d11e275dddadbaab3acf10ebe2e2f3ab971c824e7`
- Full-field place betting review：`705b31203cc9b8f2c4f2acff2a68a80398ea81eb85de4a2504560d301634fa93`

ML 執行時系統缺少可供 LightGBM / XGBoost 載入嘅 `libomp`。今次只喺 `/private/tmp` 建立隔離 runtime，並驗證官方 Homebrew bottle SHA；**冇修改原本 Python environment 或系統 library**。
