# EXP-20261101-02 NBA：ESPN 做唯一數據來源 —— 一把尺重建訓練語料 + regression gate

- **日期**：2026-11-01
- **平台**：NBA
- **假設**：用 ESPN 重新計晒訓練語料嘅全部特徵（一把尺），現役 C 層嘅輸出唔會變差（non-inferior）；防守者表（`defender_pm`）同 DvP 可以由特徵表移除。
- **搜索過嘅舊記錄**：EXP-20261023-06（v2 驗證語料、RF 協議、C 嘅 terminal 診斷）、EXP-20261030-01（ESPN 賽績 94.7% 逐場一樣）、EXP-20261031-01（ESPN 聯盟數據表；冇追蹤數據對機率零影響）、EXP-20261101-01（PBP 陣容 parity）。
- **改到嘅檔案**：
  - 數據合約：`nba_data_contract.py`（contract v3：唔再要求防守者表；每個 package 寫 `stat_source`；`primary_source()`）
  - 主來源：`nba_wong_choi/resources/nba_stat_source.json`（`primary: espn`）、`nba_api_breaker.py`（ESPN 主來源時 stats.nba.com 一個請求都唔發、cache 都唔讀）、`nba_league_snapshot.py`（ESPN 模式唔讀 nba.com 快照）、`nba_daily_schedule.py`（狀態 `not_used` 唔再發封鎖／恢復通知）
  - 抽取：`nba_extractor.py`（`meta.stat_source`）
  - 特徵／訓練：`nba_ml_features.py`（contract `nba-ml-features/v3`：剷 `defender_pm`，26 個特徵；`check_single_source`）、`build_nba_ml_dataset.py`（每行 `stat_source`）、`train_nba_xgboost.py`（混合來源拒絕，`--allow-mixed-sources` 先放行並印比例）、`nba_ml_predictor.py`
  - 位置：`nba_espn_lineups.espn_position`（ESPN G/F/C 一個尺度）

## 預先登記（跑閘之前寫，commit 先於結果）

**語料**：EXP-20261023-06 嘅 strict priced manifest —— 49 個賽事、24 個美東日期（2026-04-15..06-10，2025-26 季後賽／附加賽），已驗證標籤。baseline 同 candidate **同一批行**（兩邊都有、都有標籤先入；只喺一邊出現嘅行照數報，唔補）。

**兩把尺**：
- baseline（`stat_source=nbacom`）：原本 nba.com package，經今日嘅特徵建構器（v3，冇 `defender_pm`）。
- candidate（`stat_source=espn`）：同一個 package（陣容、傷停狀態、賠率、擷取時間不變），所有數據換成 live ESPN 路徑：extractor 自己嘅 `fetch_player_gamelog`／`fetch_player_splits`／`compute_fatigue_adjustment`（stats.nba.com stand down），球隊／球員表由 ESPN 2025-26 常規賽 box score 計（nba.com 喺季後賽用嘅都係常規賽終值，已核對），球員 OFF/DEF 由 PBP 陣容計，位置用 ESPN G/F/C。
- point-in-time：所有 ESPN 輸入都係賽事美東日之前已完場嘅日子（`history_date_to`），同原本 nba.com 窗口一樣；`validate_capture` 會再查 L10 日期。

**主要判決（現役 C 層，live）**：`p_final = calibrated_prob(stat, 價, hit_rate_l10)`，全部配對行；ESPN − nba.com 嘅 Brier，美東日期 cluster bootstrap 2,000 次、seed 20261101。
- **KEEP**：95% CI 上限 ≤ **+0.002**（non-inferior；約 C Brier 嘅 1.2%）
- **REJECT**：CI 下限 > 0（顯著變差）
- 其餘 **NEEDS MORE TESTING**
- 同時報：log-loss 差、`hit_rate_l10` 一樣嘅比例、有變嘅腿數、平均／最大移動、跨 50/60/70/80% 嘅數目。

**次要（只係 shadow，唔影響判決）**：v2 固定 RF 協議（`train_model`，前 19 日 dev 五折、尾 5 日 terminal），三個 arm：
- A：v2 dataset 27 特徵（含 `defender_pm`，2026-10-23 重現）
- B：nba.com 尺 26 特徵（剷 `defender_pm`）
- C：ESPN 尺 26 特徵
- 報 terminal Brier、B−A（剷防守者）、C−B（換尺），配對 CI。呢段 terminal 已經睇過（EXP-20261023-06），唔係新盲測，**唔准用嚟調參或者揀特徵**。

**唔做**：唔 refit C、唔改 C 係數、唔換窗口、唔換指標救候選。

## 結果
（跑閘後填）
