# HKJC shadow profile 登記表（2026-10-10）

Phase −1 第 4 步。目的：每個 shadow 要寫明來源、開始日、判決場數、處理建議。
唔准有「計咗但永遠唔判」嘅 shadow。

## 實測：shadow 由 10-07 先真正開始累積

逐個賽日讀 `racing_run_log.jsonl` 嘅 `horse_scored.shadow_profiles`，同埋賽前
immutable snapshot 嘅 `python_auto_shadow_verdicts`：

| 賽日 | run log 有 shadow | 賽前 snapshot 有 shadow verdict |
|---|---|---|
| 09-06 至 10-04（8 個賽日） | 冇 | 冇 |
| 10-07 跑馬地 | 7 個 profile | `Prediction_Snapshots/` 有（9 場）；`_prediction_snapshots/` 冇 |
| 10-11 沙田 | 8 個 profile | 有（未有賽果） |

即係各實驗記錄寫嘅「由 09-10／09-28 起 forward 觀察」，**實際 forward 證據只有
10-07 嗰 9 場**。`hkjc_shadow_monitor.py` 只讀 `Prediction_Snapshots/`，而 09 月嘅
賽日只有 `_prediction_snapshots/`（同 [[qa-frozen-dirs-were-name-exact]] 同一類命名分歧）。
10-07 兩個目錄並存，而且內容唔同 —— 邊個先係賽前真值要喺 Phase 6 釐清。

## 登記表

HKJC 每場約 10 場賽事、每週 2 個賽日 → 約 80 場／月。

| profile | 來源 | 用途 | 最少場數 | 已累積 | 建議 |
|---|---|---|---:|---:|---|
| `weight_refit_t02` | EXP-20260928-09 | 已 REJECT_DEV 嘅外層權重候選 | 120 | 9 | **剷**：同 e0c90bfa 嘅 `weight_rollback_0809`／`race_shape_w200`／`w170` 測同一件事 |
| `race_shape_v2_legacy_hv` | EXP-20260929-01 | 跑馬地 v3 實驗性上線嘅回退 | 20 | 9（HV） | 留，到 20 場判 |
| `race_shape_st_draw70` | EXP-20260929-02 | 沙田檔位 70% REJECT 後 forward | 80 | 0（ST 有賽果） | 留，但 9D 後要 rebase |
| `race_shape_legacy_unbounded` | EXP-20261008-03 | winsor10 上線嘅回退 | 80 | 9 | 留（回退保護） |
| `pre_race_draw_context_v1_generic` | EXP-20261007-01 | v2 檔位情境上線嘅回退 | 20 | 9 | 留，到 20 場判 |
| `trainer_recency_st_early90` | EXP-20261005-01 | 練馬師近況，季初限定 | 80 | 0（ST） | 留到季初窗口完；之後併入騎練走勢（Phase 4b） |
| `incident_reliability` | EXP-20260910-02 | 醫療事故仗唔重複扣段速 | — | 9 | **併入** Phase 4c 可原諒失利一齊判 |
| `distance_suitability_v2` | EXP-20261007-05 | 同程 residual | — | 9 | **併入** Phase 1／4 `distance_fit` 維度 |
| `weight_rollback_0809`（e0c90bfa） | EXP-20261009-14 | 0.2737 回退 | 120 | 0 | 留 |
| `race_shape_w200`／`w170`（e0c90bfa） | EXP-20261009-14 | race_shape 權重 arms | 120 | 0 | 留 |
| `early_draw_rollback`（e0c90bfa） | EXP-20261009-15 | E3 回退 | 120 | 0 | 留 |

## 規則（之後新增 shadow 一律跟）

1. 每個 profile 要喺 `PROFILE_MINIMUMS` 有最少場數，冇就唔准入 `DEFAULT_SHADOW_PROFILES`。
2. 開始日以「第一個有賽前 snapshot verdict 嘅賽日」計，唔係實驗記錄日期。
3. 到期（最少場數 × 2 仍未判）或者已判決 → 剷。
4. 9D 拆分（Phase 1）之後，所有權重類 shadow 要 rebase 到新權重，並重新計場數。
