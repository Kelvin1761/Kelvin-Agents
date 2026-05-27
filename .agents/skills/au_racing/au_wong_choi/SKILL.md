---
name: AU Wong Choi
description: This skill should be used when the user wants to "analyse AU races", "run AU pipeline", "澳洲賽馬分析", "AU Wong Choi", or needs to orchestrate the full Australian horse racing analysis pipeline from data extraction through to final deterministic output generation.
version: 6.0.0
---

# AU Wong Choi — Current Mainline

## Current Reality

`AU Wong Choi` 目前主線係 **full Python pipeline**。

而家嘅 live path：

1. Racenet extraction
2. `Facts.md` generation
3. deterministic `Race_X_Logic.json` build
4. deterministic auto scoring / ranking
5. `Race_X_Auto_Analysis.md` / `Race_X_Auto_Scoring.csv` / `Meeting_Auto_Scoring.csv`

> 現時主線 **唔需要 LLM 手動填 core logic、verdict 或 `[FILL]` 欄位**。

## 唯一入口

收到 Racenet URL、meeting folder、或現成 `Race_X_Logic.json` 後，唯一正確入口係：

```bash
python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<URL或資料夾>"
```

如果環境冇 `python3`，可改用：

```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<URL或資料夾>"
```

## Supported Inputs

- Racenet form-guide URL
- 已存在 meeting folder
- 現成 `Race_X_Logic.json`

## Expected Outputs

- `*Racecard.md`
- `*Formguide.md`
- `*Race N Facts.md`
- `Race_X_Logic.json`
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- `Meeting_Auto_Scoring.csv`

## Guard Rails

- **嚴禁**跳過 orchestrator 手動拼裝 extraction / facts / logic / output
- **嚴禁**假設要跟 `NEXT_CMD` 做 LLM-driven workflow
- **嚴禁**再用舊 active-path legacy orchestrator
- **嚴禁**手動補 deterministic analysis 欄位

## Related Components

- `au_race_extractor`
- `.agents/scripts/inject_fact_anchors.py`
- `au_wong_choi_auto/scripts/build_au_logic.py`
- `au_wong_choi_auto/scripts/au_auto_orchestrator.py`
- shared post-success Cloudflare deploy hook

## Archived Legacy Snapshot

如用戶明確要求 legacy comparison，封存版本喺：

- `.agents/archive/wong_choi_legacy_snapshot_20260526/au/au_orchestrator_legacy_snapshot_20260526.py`

用途只限：

- 舊 output 對照
- 手動考古比對
