---
name: AU Wong Choi Auto
description: Deterministic full-Python scoring and narrative renderer for AU Wong Choi. Use when AU races need Python-only logic, scoring, ranking, markdown output, and validation without LLM-filled analysis fields.
version: 1.0.0
---

# AU Wong Choi Auto — Full Python Deterministic Engine

## Purpose
- Consume existing AU `Race_X_Logic.json` + `Facts.md`
- Build deterministic `python_auto` analysis namespace
- Render AU narrative-style `Race_X_Auto_Analysis.md`
- Export `Race_X_Auto_Scoring.csv`
- Produce meeting-level summary output for reflector and dashboard

## Entry Point
```bash
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_auto_orchestrator.py <meeting_dir_or_logic_file> [--going "Good 4"]
```

For live meetings, ALWAYS pass `--going` with the official current track condition
(from the extractor / racenet meeting page) so scoring never runs on stale Logic
going (Warwick Farm 2026-07-15 raced Good 4 but was scored on stale Soft 5 data).
The refresh overwrites every going field the engine reads and records an audit
trail in `race_analysis.going_refresh`.

## Outputs
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- meeting summary CSV

## Rules
- Do not inject LLM placeholders
- Do not depend on `[FILL]` fields for live ranking
- Ranking uses deterministic `ability_score` + AU micro tie-break rules
