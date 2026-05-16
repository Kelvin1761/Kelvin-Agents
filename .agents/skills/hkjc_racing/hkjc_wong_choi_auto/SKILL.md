---
name: HKJC Wong Choi Auto
description: This skill should be used when the user wants to "run HKJC Wong Choi Auto", "HKJC Auto Python scoring", "全 Python 化香港賽馬分析", "deterministic HKJC scoring", or score existing `Race_X_Logic.json` files without LLM involvement.
version: 1.0.0
---

# HKJC Wong Choi Auto — Python-Only Scoring Wrapper

## Role

HKJC Wong Choi Auto 係獨立於 classic HKJC Wong Choi 嘅 deterministic scoring pipeline。佢沿用 existing extraction / Logic JSON output，但分數、排名、Grade、Top Pick、risk flags、reason codes、core logic、Markdown/CSV wording 全部由 Python 產生。

## Objective

對現有 `Race_*_Logic.json` 或 meeting folder 進行 deterministic Auto scoring，寫入：

- 每匹馬 `python_auto`
- race-level `python_auto_verdict`
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- folder-level `HKJC_Auto_Scoring.csv`

## Resource Read-Once Protocol

開始前讀一次：

- `resources/01_scoring_contract.md`
- `resources/02_output_mapping.md`
- `resources/03_validation_rules.md`

## Scope

Auto V1 支援：

- existing `Race_X_Logic.json`
- folder containing `Race_*_Logic.json`
- local `hkjc_draw_stats.json`
- existing extracted fields such as `_data`, `trackwork`, `last_6_finishes`, `season_stats`, `jockey_combo_block`

Auto V1 不負責：

- HKJC website extraction
- PDF parsing
- classic Analysis.md rewrite
- odds/value/Kelly/bet sizing
- LLM commentary

## Strict Constraints

- Python owns all Auto output.
- LLM must not fill, edit, rewrite, approve, or rank Auto output.
- Do not import or call OpenAI, Claude, Gemini, browser AI, or local model providers.
- Do not use odds, market, fair odds, edge, value, pace prediction, leader count, race collapse, on-pace score, or backmarker score in scoring.
- Do not write `[FILL]` into Auto fields.
- Missing structured data = neutral 60 + reason/risk code + provenance.
- User-facing report uses 香港中文 labels: `模型首選`, `觀望`, `綜合戰力分`, `信心分`, `風險分`; `NO_PICK` 狀態在報告內不展示。
- Internal JSON/CSV headers may keep English keys for machines.

## Interaction Logic

1. Run:
   ```bash
   python3 .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py <target>
   ```
2. If `python3` is unavailable, use:
   ```bash
   python .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py <target>
   ```
3. Read stdout. If validation fails, report exact error codes.
4. Do not manually edit scoring output.

## Verification

After code changes to Auto, run:

```bash
python3 -m py_compile .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py
python3 -m unittest discover .agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests
```
