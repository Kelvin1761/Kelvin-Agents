# EXP-20261104-06 — NBA reflector 只讀 sidecar

- 日期：2026-11-04
- 平台：NBA（`nba_reflector`：`verify_props_hits.py`、`nba_reflector_orchestrator.py`；`nba_research_evidence` 經同一個 extractor）
- 基準 commit：`d500aa8b`（EXP-20261104-04，dashboard／防火牆／SGM 匯總已經只讀 sidecar）
- 類型：**工程重構，唔改模型、唔改結算規則**。

## 改咗咩

- `verify_props_hits.bound_sidecar()`：`report_sha256` 對得上先讀 `.market_legs.json`；`extract_legs_from_report()` 由 sidecar
  `combos[].legs` 攞腿（之前 regex 解析 `| 🧩 n |` 表格同 LLM 年代嘅 `Leg N:` 行）。
- `nba_reflector_orchestrator.sidecar_rows()` 取代 `parse_report_metadata`／`iter_leg_blocks`／`parse_leg_block`／
  `parse_player_cards`／`parse_combo_table_rows`／Markdown fallback（約 330 行）。冇綁定 sidecar 嘅報告唔記錄（印警告）。
- `implied_prob = round(100/odds, 2)`、`edge_pct = round(predicted − implied, 2)`：同舊報告印出嚟嘅數字逐條一樣（282/282；試過
  `round(100/odds, 1)` 有 246 條唔同）。`model_version` = sidecar `engine`，舊引擎冇呢欄就用 `legacy:<engine_mode>`。
- 冇 sidecar 嘅 `*_NBA_*_Analysis.md`／`.txt` 舊格式唔再掃。
- `report.py` 嘅 Markdown 而家純顯示，冇任何嘢 parse 佢。

## 結果（`docs/experiments/evidence/EXP-20261104-06-nba-reflector-sidecar-parity.py`）

`~/WongChoiData/Wong Choi NBA Analysis` 12 個有 Results_Brief 嘅賽日（2026-10-21 → 11-03），`d500aa8b` vs 今次：

- **Props_Verification JSON 12/12 日逐字一樣**（每條腿嘅 actual／margin／cleared／status，同 summary 嘅 hits／misses／voids／
  hit_rate、by_combo、by_stat）。合共 282 條腿，174 中。
- Reflector rows：282 條，key（場次、組合、球員、盤口、線）完全一樣；odds、implied、predicted、edge、L10 命中率、actual、
  cleared、status、final_score 全部一樣。
- **有分別（預期）**：只有舊 Markdown 球員卡先有嘅 `l10_hits`、`l10_total`、`l10_avg`、`l10_med`、`l10_sd`、`cov_label`
  變 None（舊 sidecar 從來冇存）；`model_version` 由報告標題字串（例如 `Hybrid V1 (ML shortlist …)`）變 `legacy:hybrid`。
  新引擎報告本身冇球員卡，之前已經係 None，所以 11-04 之後冇分別。
- 影響：呢幾欄只入 `reflector_legs` DB／training CSV，同 `evaluate_historical_model`（歷史 ML 評估報告，唔影響揀腿）嘅特徵。
  已經記錄咗嘅舊行唔會變，除非人手重跑舊日 reflector。

## 測試

NBA 472 全過。fixture `postgame_20261021` 嘅 sidecar 補返真實 10-21 嘅腿條目（L10 命中率）。新測試：報告改成冇表格、
sidecar 重新綁定 → 照樣 36 條；冇 sidecar／sidecar 對唔上 → 唔記錄；LLM 年代 `Leg N:` 報告 → 唔記錄。
