# EXP-20261101-30 上線：L600 環境分近期加權（R）—— 用戶決定，唔係改善聲稱

- **用戶決定（2026-11-01）**：「近期加權的確令速度分準咗 i think we should use this, also Good 升、Gold 跌 i can accept for au」
- **判決記錄**：[results](EXP-20261101-30-au-l600-recency-distance-results.md) —— 研究判決係 REJECT
  （v3 `primary_regression`、§8 `both_arms_reject`）。今次上線係用戶按可解釋性同取捨作嘅決定，
  同 EXP-20261016-77 上線一樣，**唔係閘門通過**。
- **只上 R**。P（路程相近度）同 RP 照舊 REJECT，冇上。

## 改咗咩

`engine_core._pf_aggregates`：`l600_delta_avg` 同 `own_l600_delta_avg` 由每仗一樣重改為近期加權，
最近一仗權重 1，之後每仗 ×0.8（`L600_RECENCY_DECAY`，EXP-20261016-01 D3c 原值）。k 按 `run_date` 由新到舊。
場均／場內 SD 經 field summary 讀同一個值，所以分子分母同一個量。其他 `_avg`／`_best`、試閘 L600 分
（`trial_speed_raw`，獨立路徑）不變。報告字眼改為「近期加權平均」。

## 預期影響（全部係歷史量度，CI 跨零）

| | 數值 |
|---|---|
| L600 環境分 leaf AUC | +0.0053 [+0.0022, +0.0084]（3,246 場） |
| Gold（v3，3,246 場） | 21.32% → 21.13%（−0.18pp [−0.72, +0.33]） |
| Good 位置 | 25.85% → 26.12%（+0.28pp [−0.23, +0.77]） |
| Pass | 49.57% → 49.32% |
| 首選頭三次序有變嘅場次 | 628／3,246（19.3%） |

## 核對

- 引擎上線版重新 dump（同一語料），同 replica R arm 逐匹對比：乾淨窗 31,246 匹 `pace_figure_score`
  差 > 1e-3 = **0**、綜合分差 > 0.005 = **0**（最大差 0.0）。即係上線嘅就係量度過嗰個 arm。
- 單元測試：`test_pace_figure_individualised.py` 期望值按新權重更新（0.67→0.689、0.7→0.678），
  另加「權重跟 run_date 唔跟傳入次序」測試；`test_l600_recency_forward.py` 釘住監察重算 == 引擎。
- golden_scoring 120 匹一致 —— 預期之內：golden 係「特徵入、分數出」，唔經 PF 解析
  （佢自己 docstring 已寫明呢個盲點）。live 路徑 `enrich_logic_from_facts` 每次都重新 parse
  Formguide → `_pf_aggregates`，已確認接通。

## Forward 監察（預先登記）

- `au_wong_choi_auto/scripts/au_l600_recency_forward.py`，AU 排程每次 run 喺速度盲測之後跑
  （`step_l600_recency_forward`），狀態寫 `au_daily_auto/work/au-l600-recency-forward-status.json`。
- 用已儲存 live Logic 重算：上線版（必須同儲存 `pace_figure_score` 一致，否則當舊引擎場次唔計）vs
  每仗一樣重嘅反事實，其餘特徵同 overlay 原封不動。上線前 518 場 smoke test：decay=1 時 518／518 場同儲存分一致。
- 由 **2026-11-02** 起，夠 **600 場**完整賽果判一次並凍結（v3 fixed_rule）：Gold、Good 點估計都唔負 = 保留；
  否則 Telegram 提請 Kelvin 決定係咪還原。之前只記場數，唔出結果指標。永遠唔會自動改模型。

## 還原

`L600_RECENCY_DECAY = 1.0` 即係返回每仗一樣重（權重全部 1；加總次序按日期，捨入到 3dp 後同舊平均數一樣，
smoke test 518／518 場對得上）。
