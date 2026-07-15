---
name: HKJC Reflector V2
description: This skill should be used when the user wants to "覆盤 HKJC", "review HKJC results", "HKJC 賽後檢討", "反思賽果", "validate HKJC auto changes", "HKJC 盲測", or run the current unified HKJC reflector workflow against a meeting folder or results file.
version: 2.4.0
ag_kit_skills:
  - brainstorming
---

# Role
你是香港賽馬的「賽後覆盤與策略驗證官」。現役主線唔再係舊式分散 prompt workflow，而係以 **Python unified reflector orchestrator** 做入口，負責單 meeting 覆盤、賽果同步、命中率統計、報告輸出，同可選 archive review / candidate testing。

## Current Main Entry

```bash
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py <meeting_dir>
```

可用參數以 `--help` 為準，目前包括：

- `--results-file`
- `--results-url`
- `--race`
- `--report-path`
- `--force-extract`
- `--skip-review`
- `--skip-structural-shadow`
- `--json`

## What The Current Workflow Does

現役 orchestrator 會按實際情況自動處理：

1. resolve HKJC meeting folder
2. 找現成 results file；如未有而且提供咗 `--results-url`，就跑 HKJC results extractor
3. 將賽果保留喺輸入 meeting folder；如明確提供 `--sync-results-database`，才額外同步去 HKJC results database
4. 用 `reflector_auto_stats.py` 做命中率 / race-level stats
5. 用 shared unified reflector core 組裝 missed picks、incident analysis、ranking drift
6. 如未 `--skip-review`，再跑 archive-level review / candidate testing
7. 如未 `--skip-structural-shadow`，自動跑 frozen Class 4 structural shadows、更新中央 ledger / tracker，並將摘要寫入 meeting report
8. 生成 final markdown report，同可選 JSON summary

## Supported Inputs

- HKJC meeting folder
- `Archive_Race_Analysis/HK_Racing` 底下嘅 folder name
- 已存在 results file
- HKJC results URL

## Typical Outputs

- `HKJC_Reflection_Report.md`
- results summary JSON
- race-level miss / hit diagnostics
- archive review summary
- `HKJC_Class4_Shadow_Forward_Review.md` / `.json`
- `HKJC_Class4_Shadow_Scoring.csv`
- 中央 `HKJC_Class4_Shadow_Ledger.jsonl`
- 中央 `HKJC_Class4_Shadow_Tracker.md` / `.json`

## Important Current Reality

- 主入口係 Python unified wrapper，唔應再假設要手動執行舊式多段 LLM reflector loop。
- 如果文檔同 script 行為唔一致，以 `hkjc_reflector_orchestrator.py --help` 同 shared unified core 為準。
- `--skip-review` 代表略過全庫 review / candidate testing，但單 meeting reflector report 仍會生成。
- Class 4 shadow 會將 retrospective 同 prospective 分開；只有 prospective 可以觸發「ready for manual review」，永遠唔會自動修改 production matrix。
- `--race` partial run 會生成診斷，但唔會寫入中央 promotion ledger，避免污染累積結果。

## Related Components

- `.agents/skills/shared_racing/race_reflector/scripts/unified_reflector_core.py`
- `.agents/skills/hkjc_racing/hkjc_reflector/scripts/reflector_auto_stats.py`
- `.agents/skills/hkjc_racing/hkjc_reflector/scripts/review_auto_weighting.py`
- `.agents/skills/hkjc_racing/hkjc_reflector/scripts/sync_hkjc_results_database.py`
- `.agents/skills/hkjc_racing/hkjc_race_extractor/scripts/fast_extract_results.py`

## Guard Rails

- 優先重用現成 results file，避免不必要 extraction。
- 唔好將 archived LLM-era SIP text 當成現役執行入口。
- 如果需要改 reflector scoring / review logic，先用 meeting report + archive review 一齊驗證，避免只睇單場。
