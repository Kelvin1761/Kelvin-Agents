---
name: HKJC Wong Choi
description: This skill should be used when the user wants to "analyse HKJC races", "run HKJC pipeline", "香港賽馬分析", "HKJC Wong Choi", or needs to orchestrate the full Python Hong Kong horse racing pipeline from data extraction through to final Auto analysis generation.
version: 5.0.0
---

# HKJC Wong Choi — Current Mainline

## Current Reality

`HKJC Wong Choi` 目前主線係 **full Python pipeline**。

而家嘅 live path：

1. HKJC extraction
2. `Facts.md` generation
3. `Race_X_Logic.json` generation / refresh
4. deterministic auto scoring
5. runner/name/source alignment + data coverage gate
6. `Race_X_Auto_Analysis.md` / `Race_X_Auto_Scoring.csv` / `HKJC_Auto_Scoring.csv`
7. health-gated dashboard deploy

> 現時主線 **唔需要 LLM 手動填 verdict、matrix、core logic 或 `[FILL]` 欄位**。

## 唯一入口

收到 HKJC URL 或 meeting folder 後，唯一正確入口係：

```bash
python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <URL或資料夾>
```

如果環境冇 `python3`，可改用：

```bash
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <URL或資料夾>
```

## Supported Inputs

- HKJC racecard URL
- 已存在 meeting folder

## Expected Outputs

- `* Race * Facts.md`
- `Race_X_Logic.json`
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- `HKJC_Auto_Scoring.csv`
- `Data_Health.json` / `Data_Health.md`

## Guard Rails

- **嚴禁**跳過 orchestrator 手動拼裝流程
- **嚴禁**再用舊 active-path legacy orchestrator
- **嚴禁**假設仍要靠 LLM 補分析欄位
- **嚴禁**手動改 deterministic scoring，除非用戶明確要求 debug / calibration

## Related Components

- `hkjc_race_extractor`
- `.agents/scripts/run_prerace_pipeline.py`
- `hkjc_wong_choi_auto`
- shared post-success Cloudflare deploy hook
- `hkjc_daily_auto`（off-season watch、pre-race、post-race reflector、weekly Telegram／PR approval gate）

## Unattended Schedule

安裝 macOS launchd：

```bash
bash .agents/skills/hkjc_racing/hkjc_daily_auto/install_macos_launchd.sh
```

候選模型只可自動開 non-draft PR；任何 merge / production promotion 必須等
用戶明確批准。

## Archived Legacy Snapshot

如用戶明確要求 legacy comparison，封存版本喺：

- `.agents/archive/wong_choi_legacy_snapshot_20260526/hkjc/hkjc_orchestrator_legacy_snapshot_20260526.py`

用途只限：

- 舊 output 對照
- 手動考古比對
