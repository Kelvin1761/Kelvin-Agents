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

## 覆盤都由呢個 skill 入（唔使再叫 AU Reflector）

用戶講「**au wong choi review 08-01 rosehill gardens**」或者「**覆盤 08-01 flemington**」
嗰陣，唔好叫佢貼路徑或者 URL，亦唔使另外叫 `AU Reflector` skill。先用 resolver 把
一句話變成 meeting 目錄，再交畀 reflector orchestrator：

```bash
DIR=$(python3 .agents/skills/au_racing/au_meeting_resolver.py "08-01 rosehill gardens") \
  && python3 .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py "$DIR"
```

分析（唔係覆盤）就同一個 resolver 接落主入口：

```bash
DIR=$(python3 .agents/skills/au_racing/au_meeting_resolver.py "08-01 rosehill gardens") \
  && python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "$DIR"
```

Resolver 認得 `08-01` / `8-1` / `2026-08-01` / `20260801`，馬場名做大小寫無關嘅
子字串（`rosehill` 對得住 `Rosehill Gardens`），live 根目錄同 `Archive/` 一齊搵。

⚠️ **多過一個 match 佢會 exit 1 並列晒出嚟，唔會亂猜** —— 撞錯馬場好過靜靜咁分析錯。
遇到就把個 list 畀用戶揀，唔好自己挑一個。

⚠️ 覆盤要賽果。`--results-url` 已經冇用（Racenet 三條 transport 全封），賽果由
Sportsbet 攞 —— 見 `claw_sportsbet_form.py`。

## Supported Inputs

- 一句話（例：`08-01 rosehill gardens`）— 經 `au_meeting_resolver.py`
- 已存在 meeting folder
- 現成 `Race_X_Logic.json`
- ~~Racenet form-guide URL~~ — Racenet 已全面封鎖，改用 Sportsbet

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
