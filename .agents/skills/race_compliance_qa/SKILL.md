---
name: Race Compliance QA
description: Use this shared skill when checking HKJC or AU racing pipeline quality, race compliance, batch QA, raw extraction validity, Logic vs Analysis Top4 drift, reflector result parsing, or when replacing retired HKJC/AU batch QA and compliance agents with one cross-racing guardrail.
version: 1.0.0
---

# Race Compliance QA

## Role
你係 HKJC + AU racing pipeline 嘅 shared QA/compliance 守門員。你負責喺 Wong Choi、Race Extractor、Reflector、completion gate 之間做獨立檢查，確保 raw data、Logic JSON、Analysis Markdown、result stats 四層冇 drift。

## Scope
- 覆蓋 HKJC 同 AU racing。
- 優先檢查 deterministic failure modes：raw extraction bad file、Top4 drift、result JSON parse failure、placeholder 殘留、batch incomplete。
- 呢個 skill 係 shared guardrail，不取代 `hkjc_orchestrator.py` / `au_orchestrator.py` / `completion_gate_v2.py`。
- 預設只讀；除非用戶明確要求 fix，否則只報告問題。

## Quick Workflow
1. 判斷目標係 `hkjc`、`au`，或跨兩者。
2. 若有本地 meeting/report directory，先跑 deterministic scanner：
   ```bash
   python .agents/skills/race_compliance_qa/scripts/race_compliance_scan.py --root <target_dir> --platform hkjc --json
   ```
   AU 用 `--platform au`；唔肯定就用 `--platform auto`。
3. 讀 scanner output，先處理 `CRITICAL`。任何 `CRITICAL` 都代表唔可以進入下一步分析/覆盤。
4. 需要人工判斷時，讀 `resources/01_guardrails.md`，按平台做補充審查。
5. 最終用香港繁體中文輸出：
   - `✅ RACE QA PASSED`
   - `⚠️ RACE QA CONDITIONAL PASS`
   - `❌ RACE QA FAILED`

## Mandatory Gates
- Raw racecard/formguide/results 檔案不可細過最低大小、不可包含 extractor error/Traceback。
- Logic verdict Top4 必須同 compiled Analysis Markdown Top4 一致。
- Result JSON 必須可 parse 到 race number、position、horse number。
- Analysis/Logic 不可有 `[AUTO]`、`PLACEHOLDER`、`{{LLM_FILL}}`、`[FILL]`。
- 若 batch extractor 有任何 requested race fail，pipeline 必須 non-zero exit 或移除 invalid partial file。
- `✅✅` / `❌❌` 只可作 conviction/tiebreak display marker；canonical grading pass/fail 只當一個維度。

## Failure Protocol
- `CRITICAL`: 停止 pipeline，列出檔案、race、修復方向。
- `MINOR`: 可 conditional pass，但必須記錄並喺下一輪修正。
- 連續兩次同一 gate fail：標記為 `UNRESOLVED`，請用戶介入，不可自行猜測 raw facts。

