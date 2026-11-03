# EXP-20261104-02 `engine_core.py` 拆出 `narrative.py`（純搬遷，零差）＋引擎指紋包晒成個 package

- **日期**：2026-11-04；**平台**：AU；**baseline**：`22d9dd0b`。
- **用戶**：「先拆 narrative」（`engine_core` 三步拆分嘅第二步；第一步係 EXP-20261103-14 `data_prep.py`）。

## 改動

1. **`narrative.py`**：`RacingEngine` 嘅 64 個報告文字 method（判讀、證據行、優劣勢、評分透明度、標籤）搬去
   `NarrativeMixin`，`RacingEngine(NarrativeMixin)`。揀法用 AST 呼叫圖：由報告入口（`_matrix_reasoning`、`_advantages`、
   `_disadvantages`、`_core_logic`、`_data_readout`、`_au_grade_computation_transparency`…）去到、而**任何評分入口**
   （`_score_features` 同全部 leaf、`_merged_form_quality`、`_proven_class_feature`…）都去唔到嘅先搬 —— 所以改報告字眼唔會郁分數。
   報告同評分共用嘅 61 個 method 留喺 `engine_core`。`engine_core.py` 4,734 → 3,557 行；`narrative.py` 1,206 行。
   `RE_OPP_FOLLOWUP`（兩邊都用）喺 narrative 定義、engine_core re-export。
2. **引擎指紋包晒成個 AU package**：`data_contract.engine_fingerprint` 同 `explain_model.fingerprint` 以前寫死
   `scoring.py`／`matrix_mapper.py`／`engine_core.py`（＋`dimensions.py`），之前拆出嚟嘅 `stability.py`、`track_going.py`、
   `jockey_trainer.py`、`class_rating.py`、`draw.py`、`data_prep.py` 改咗都**唔會**令 baseline／模型說明過期。改為 AU 一律
   `au_racing_engine/*.py`。指紋變咗，所以照 AGENTS.md 重新 `--calibrate --since 2026-08-05 --limit 2000`。
3. **測試跟住搬**：dashboard `test_parser_au_structured`（掃引擎句子檢查每句都有 chip 縮寫）改為讀 engine_core + narrative；
   `test_registry_reasoning_dispatch` 改 patch `narrative.DIMENSION_SPECS`。

## 核對

- 全語料 dump（以 (場次, 場) 對齊）：4,210 場、41,283 匹，分數 0 匹有差。
- 報告文字（10-20..10-26，2,607 匹）：**完全一樣**。
- Dashboard：新舊引擎各自重評 2026-11-03 Flemington 副本，`generate_static._collect_meeting` 成個 payload 除咗
  `prediction_at` 時間戳之外 **0 處不同**（10 場、139 匹）。
- 入口鏈 `--help`：orchestrator、auto orchestrator、reflector、排程、dump、walk-forward、build_au_logic、explain_model、data_contract 全 OK。
- 測試：AU／daily／shared／scripts 2,082 過、dashboard backend 137 過；唯一失敗 `test_drift_monitor` 喺 main 本身已紅。

## `engine_core` 而家淨低咩

`analyze_horse`、全部 leaf、評分同報告共用嘅 helper（3,557 行）。三步拆分完成：data_prep（數據）／engine_core（評分）／narrative（文字）。

## 發佈

Release policy 唔准評估尺（`data_contract.py`）同模型（`explain_model.py` 中「model.py」marker）同一個 release，所以分兩次：
A = narrative 拆檔＋`explain_model` 指紋＋測試＋模型說明；B = `data_contract` 指紋＋重新 calibrate 嘅 baseline（A merge 咗之後先發）。
A 同 B 之間 data_contract 會出 `stale-baseline` 警告（只警告，唔攔 deploy）。
