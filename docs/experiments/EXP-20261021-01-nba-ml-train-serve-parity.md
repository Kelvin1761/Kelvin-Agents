# EXP-20261021-01 NBA ML：live 特徵同訓練特徵唔一致（修正 + 實測，唔係模型改善）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：live `build_features` 同訓練 `build_nba_ml_dataset.extract_game_data` 構造出嚟嘅特徵唔一致，令 hybrid 對大部分 leg 套 −5pp。
- **搜索過嘅舊記錄**：`grep -ril nba docs/experiments/` —— 冇相關 NBA ML 記錄。
- **改到嘅檔案／組件**：`.agents/scripts/nba_ml/nba_ml_predictor.py`、`.agents/skills/nba/nba_wong_choi/scripts/generate_nba_reports.py`、新測試 `test_nba_ml_train_serve_parity.py`、`test_nba_ml_failure_and_cache.py`、`nba_orchestrator.extractor_cache_current`
- **唔係**：冇重訓、冇改 model.pkl／權重。**唔聲稱 ML 更好。**

## 發現（逐項，已用 parity test 釘死）
1. `hit_rate_l10/l5/l3`、`amc`：extractor 寫 x.5 盤口（`>`），report 問整數 milestone（`>=`）。live 入咗 `sportsbet_lines` 分支搵唔到 → 全部 0（`l3` 喺冇 pa 分支亦漏）。訓練用整數線 + 由 game log 手算。**修正**：永遠由 game log 按請求線用訓練公式計（`training_hit_features`）。
2. `pace_projected`：訓練基準 98，live 用 extractor 嘅 100 基準。**修正**：live 用訓練公式 `(opp_pace−98)/98`。
3. `usg_bonus_pct`：訓練永遠 0（查 `player` key，extractor 由來唔寫），live 非零。**修正**：live 固定 0（參數保留但忽略）。
4. `defender_pm`：訓練用對手 *第一個* defender，live 傳 top-3 平均。**修正**：call site 傳第一個。
5. 吞錯：`except: pass`（預測）、ML 載入失敗靜靜退 legacy。**修正**：`ML_STATUS` 計數 + 報告 header 警告。
6. **（未修，訓練側缺陷）** `build_nba_ml_dataset` 嘅 `opp_abbr = home_abbr if is_home else away_abbr` 其實係球員**自己隊**，所以訓練集入面 `opp_def_rating/opp_def_rank/opp_pace/defender_pm` 全部係己隊數值。Live 傳真正對手。呢個要重訓先修得；`test_training_builder_resolves_opponent_to_own_team` 釘住現狀，builder 一修就會響。

## 實測（修正前 vs 後，同一 v3 模型，11 場 2026-10-11/12 真實存檔，401 個 leg）
命令：`/private/tmp/.../scratchpad/run_ab.py {old,new}`（old = origin/main 嘅 predictor），逐場跑 `generate_nba_reports --engine hybrid`，比對 `.market_legs.json`。

| | 修正前 | 修正後 |
|---|---|---|
| 平均 ML 機率 | 0.278 | 0.688 |
| 平均 10-Factor 機率 | 0.521 | 0.521 |
| 平均 (ML − 10F) | −24.4pp | **+16.7pp** |
| hybrid 調整 ≤ −4.5pp 嘅 leg 比例 | **58.1%** | 6.5% |
| hybrid 調整 ≥ +1.5pp 嘅 leg 比例 | 11.2% | **46.4%** |
| 平均 L10 base rate（參考） | — | 0.56 |

結論：**−5pp 懲罰唔再廣泛觸發（58%→6.5%），但換成廣泛加分（46% 拎 +2/+3pp）。** 修正後 ML 平均 0.688 高過 L10 base 0.56 同 10F 0.521，即模型喺有報價嘅線上偏樂觀。成因（推測，未驗證）：訓練集 13.7% 係正樣本（所有整數線，包括冇人開盤嘅離譜線），而有報價嘅線正樣本率約 55%，機率冇校準到呢個 population。呢個**唔係**「修咗就更準」，只係 live 同訓練輸入一致；hybrid 而家會更常加分，EV／Kelly 用嘅係 10F + hybrid_adj，所以影響限於 ±2/3pp。

## 檢查
- **leakage-audit**：PASS（冇加新特徵；只係令 live 輸入跟返訓練構造）。
- **golden_scoring／data_contract**：冇郁（NBA ML 唔喺賽馬引擎）。
- **退步**：冇測到（NBA suite 207 passed）；但冇 out-of-sample 證據顯示 hybrid 結果更好或更差。

## 公佈指標無效（記錄，唔好引用）
`models/v3/metrics.json` 嘅 AUC 0.9391 無效：`train_test_split` 隨機、`KFold` shuffle，行係 player×stat×line，同一場同一球員嘅多條線跨 train/test；Brier 0.0814 **差過** baseline 0.0748。

## 建議下一個實驗（獨立，未做）
用**時間排序、按場（game）分組**切 train/val/holdout，只用**有報價**嘅線訓練同評分，先量 baseline（10F、市場隱含機率）再量 candidate；修正 builder 嘅 opp_abbr；校準（isotonic／Platt）到有報價 population；用 Brier／log-loss + 配對 bootstrap 判決，唔用 AUC。完成前 hybrid 嘅 ML 訊號只可視為未驗證。

## 同場 drafted：extractor 快取
`extractor_cache_current` 只作廢 PRESEASON 快取，令開幕夜空 team_stats／advanced 嘅快取喺 06:30 被重用。新規則：非 preseason 而 team_stats 全空或全部球員 advanced 空 → 視為過期重抽。
