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


## Gold / Good 定義（2026-08-04 改）

Kelvin 定嘅追逐目標係 **Gold + Good**，而 Gold 嘅意思改咗：

    Gold        實際前三**全部**落喺模型頭四揀之內   ← 捕捉率，新
    gold_strict 模型頭三揀全部上名                    ← 舊定義，保留做歷史對照
    Good 位置   模型第一同第二揀都上名                （冇改）
    Pass        模型頭三揀任兩匹上名                   （累積指標）

新 Gold 係舊 Gold 嘅**超集**，所以任何一場舊 Gold 一定仍然係 Gold。
604 場 Sportsbet 語料：Gold 5.0% → 14.7%。

點解改：舊定義答嘅係「頭三格排得幾整齊」，而 Kelvin 要問嘅係
「三隻上名馬有冇一隻走漏」。一隻上名馬排喺第 4 位係捉到咗，
唔應該同一隻排喺第 9 位嘅同分。

⚠️ 任何引用歷史 Gold 數字嘅地方要講清楚用邊個定義 —— 兩者差近三倍。

`Good Any-2` 名稱已退休；原本同一條「任兩匹」規則正式統一叫 `Pass`。

統一評估（同時列新 Gold、`gold_strict`、Good、Pass、Champion、Winner@3/5）：

```bash
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_eval.py \
  --data <leaves_or_current_runtime_dataset.json>
```

切分以完整賽日為單位；唔可以將同一日 meeting 一半放 dev、一半放 holdout。
`eval_metrics.race_metrics` 兩個都出，`summarize_races` 兩個都數。
