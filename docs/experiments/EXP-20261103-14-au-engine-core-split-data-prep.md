# EXP-20261103-14 `engine_core.py` 拆出 `data_prep.py`（純搬遷，零差）

- **日期**：2026-11-03；**平台**：AU；**baseline**：`710b4297`。
- **用戶**：「do we need new structure for au wong choi?」→「好，開始拆」（第一步：數據準備）。

## 改動

- `engine_core.py` 7,161 → 4,734 行；新 `data_prep.py` 2,942 行。
- 搬咗：class 之後全部模組層 function（讀 Facts／Formguide／Racecard、`refresh_*`、`backfill_*`、`enrich_logic_from_facts`、
  場地幾何／profile、meeting intelligence），加埋佢哋用嘅常數同 cache（`TRACK_*`、`PF_BACKFILL_*`、`VENUE_TRACK_MAP`、
  `HORSE_BLOCK_RE`、`_FG_*` regex）—— 共 145 個名。
- `engine_core` 用一個明確 import list re-export 晒 145 個舊名，所以 `from au_racing_engine.engine_core import refresh_form_quality`
  之類嘅舊 import（研究腳本、排程、dashboard `generate_static.py`）照用。`data_prep` 唔 import `engine_core`，冇 circular。
- 測試：兩個 monkeypatch 舊位置嘅測試改 patch `data_prep`（`_pf_backfill_for_race`、`_PF_BACKFILL_CACHE`）——
  rebinding 一個 re-export 名唔會影響 `data_prep` 入面嗰個。

## 零差證明

- 全語料 dump：4,105 場、40,216 匹，feature 同 ability 0 匹有差。
- 報告文字（10-20..10-26，2,607 匹，feature notes／明細／判讀／優劣勢）：**完全一樣**。
- 入口鏈真 import（`--help`）：AU orchestrator、auto orchestrator、reflector、排程、dump、walk-forward、build_au_logic 全 OK；
  5 個本身唔支援 `--help` 嘅腳本同 main 結果一樣。
- Dashboard：用新引擎重評 2026-11-03 Flemington（scratch 副本），`generate_static._collect_meeting` 讀到 8 個維度，
  直路賽 R4 顯示「直路賽（冇彎），檔位唔計分」、檔位 overlay 0。

## 下一步

拆 `narrative.py`（報告文字 ~1,050 行）。另外 dashboard 見到兩個舊有顯示問題（同今次無關）：試閘備戰證據欄空白兼印英文 key；
直路賽戰術劇本寫「首彎前」—— 另一個 commit 修。
