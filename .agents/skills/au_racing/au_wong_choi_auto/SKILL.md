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
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_auto_orchestrator.py <meeting_dir_or_logic_file>
```

## Outputs
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- meeting summary CSV
- `Meeting_Structural_Shadow.csv` (frozen forward-research ranks; report-only)
- `Meeting_Dual_Objective_Shadow.csv` (Place Rating + two Top4 Coverage ratings; report-only)

## Rules
- Do not inject LLM placeholders
- Do not depend on `[FILL]` fields for live ranking
- Ranking uses deterministic `ability_score` + AU micro tie-break rules
- Structural shadow scores must never mutate `ability_score`, `final_rank_score`, official Top2/Top4, or Logic JSON.
- Structural shadow inputs are market-free; odds, SP, favourite rank and market movement are prohibited.
- Dual-objective shadow uses the checksum-verified `AU_DUAL_OBJECTIVE_SHADOW_V1` pack trained through 2026-07-08. It must remain frozen during forward tracking.
- A shadow gate pass creates a promotion-ready alert only. It never silently changes the official model; explicit approval is required before canary/main activation.
