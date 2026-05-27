<!-- Cross-platform compatibility note: this file is the primary repo-facing guide. -->
<!-- `.agents/rules/GEMINI.md` is deprecated and kept only as a legacy compatibility note. -->

# Antigravity Agent Guide

> `GEMINI.md` 已 deprecated。新用戶同現役 workflow 請以 `SETUP.md` 同 `AGENTS.md` 為準。

## Current Status

Antigravity 目前最重要嘅兩條賽馬主線已經轉咗做 **full Python pipeline**：

- `HKJC Wong Choi`：100% Python-driven
- `AU Wong Choi`：100% Python-driven

即係話：

- 運行 HKJC / AU 主流程 **唔需要 Gemini**
- 運行 HKJC / AU 主流程 **唔需要任何 LLM**
- 主線分析、scoring、ranking、markdown / CSV 輸出都由 Python scripts 完成

其他目前有實際入口嘅 domain / review workflow：

- `NBA Wong Choi`
- `tennis-wong-choi`
- `HKJC Reflector`
- `AU Reflector`

補充：

- `HKJC Reflector` 同 `AU Reflector` 目前都以 Python unified orchestrator 做主入口
- reflectors 會產生 meeting-level report，同可選 archive review / backtest

如果你係新加入 repo，建議先讀：

1. [`SETUP.md`](SETUP.md)
2. 呢份 `AGENTS.md`
3. [`.agents/ARCHITECTURE.md`](.agents/ARCHITECTURE.md) 了解高層 folder map
4. [`CLOUDFLARE_DEPLOYMENT.md`](CLOUDFLARE_DEPLOYMENT.md) 了解另一部機 deploy 條件

## Repo Layout

### Core folders

- `.agents/agents/`
  角色型 agent 定義
- `.agents/skills/`
  各 domain workflow、scripts、resources
- `.agents/scripts/`
  共用 pipeline / utility scripts
- `.agents/archive/`
  舊版快照，只供比對
- `Horse_Racing_Dashboard/`
  dashboard、static snapshot、Cloudflare deploy

## HKJC Wong Choi

### Main entry

- `.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py`

### What it does

`HKJC Wong Choi` 係香港賽馬 pre-race analysis 主 orchestrator。現時主線流程係：

1. 接受 HKJC URL 或現成 meeting folder
2. 如有需要，先用 `hkjc_race_extractor` 抽取全日 race data
3. 跑 `.agents/scripts/run_prerace_pipeline.py` 生成 `Facts.md`
4. 逐場建立 / 更新 `Race_X_Logic.json`
5. 交畀 `hkjc_wong_choi_auto` 做 deterministic scoring、grade、verdict 同輸出
6. 成功後觸發共用 Cloudflare post-success hook

### Supported inputs

- HKJC racecard URL
- 已存在嘅 meeting folder

如果你只想重跑 deterministic auto engine，而唔想再抽資料 / 重建 facts，可直接用：

- `.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py`

呢個 auto orchestrator 支援：

- `Race_X_Logic.json`
- 或包含 `Race_*_Logic.json` 嘅 meeting folder

### Typical outputs

- `* Race * Facts.md`
- `Race_X_Logic.json`
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- `HKJC_Auto_Scoring.csv`

### Meeting folder naming

目前 helper 會以以下前綴建立 / 尋找 HKJC meeting folder：

- `YYYY-MM-DD_ShaTin`
- `YYYY-MM-DD_HappyValley`

## AU Wong Choi

### Main entry

- `.agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py`

### What it does

`AU Wong Choi` 係澳洲賽馬 pre-race analysis 主 orchestrator。現時主線流程係：

1. 接受 Racenet URL、meeting folder、或者現成 `Race_X_Logic.json`
2. 如有需要，先用 `au_race_extractor` 抽取 racecard / formguide
3. 由 racecard + formguide 生成 `Facts.md`
4. 用 `au_wong_choi_auto/scripts/build_au_logic.py` 建立 deterministic `Race_X_Logic.json`
5. 交畀 `au_wong_choi_auto/scripts/au_auto_orchestrator.py` 做 scoring、ranking、markdown / CSV render
6. 成功後觸發共用 Cloudflare post-success hook

### Supported inputs

- Racenet form-guide URL
- 已存在 meeting folder
- `Race_X_Logic.json`

如果用 meeting folder 直跑 full pipeline，至少要有：

- 每場對應 `*Racecard.md`
- 每場對應 `*Formguide.md`

### Typical outputs

- `*Racecard.md`
- `*Formguide.md`
- `*Race N Facts.md`
- `Race_X_Logic.json`
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- `Meeting_Auto_Scoring.csv`

### Meeting folder naming

AU orchestrator 會按資料夾名稱前綴反查 extractor 輸出，建議保留以下格式：

- `YYYY-MM-DD <Venue> ...`
- 或 `YYYY-MM-DD_<Venue>_Race_...`

## Shared Post-Success Deploy Hook

共用 hook：

- `.agents/skills/shared_racing/post_success_hooks/scripts/cloudflare_deploy_hook.py`

目前：

- `HKJC Wong Choi` 成功後會自動嘗試 deploy
- `AU Wong Choi` 成功後會自動嘗試 deploy

控制方式：

- per run：`--skip-cloudflare-deploy`
- env：`WC_DISABLE_POST_SUCCESS_DEPLOY=1`

Deploy wrapper：

- repo root：`deploy.sh`
- actual script：`Horse_Racing_Dashboard/deploy.sh`

## NBA Wong Choi

### Main entry

- `.agents/skills/nba/nba_orchestrator.py`

### What it does

`NBA Wong Choi` 目前有自己嘅 orchestrator，會串連 Sportsbet odds extraction、NBA data extraction、report generation、validation 同 SGM compile。

### Supported inputs

- `--date YYYY-MM-DD`
- `--game TEAM_TEAM`
- `--list`
- `--status`
- `--compile-only`

### Typical outputs

- `{YYYY-MM-DD} NBA Analysis/`
- `Sportsbet_Odds_*.json`
- `nba_game_data_{TAG}.json`
- `Game_{TAG}_Full_Analysis.md`
- SGM / banker 匯總報告

### Current reality

`NBA Wong Choi` 有實際可跑入口，但 repo 內仍保留一啲較舊嘅 skeleton / analyst wording。對新用戶嚟講，以 orchestrator 同實際輸出為準。

## tennis-wong-choi

### Main entry

- `tennis-wong-choi/src/tennis_wc/cli.py`

### What it does

`tennis-wong-choi` 係獨立 tennis pricing / betting engine，提供 CLI workflow，包括：

- DB 初始化
- provider health / smoke checks
- upcoming matches / odds / rankings ingestion
- daily pricing / prediction / report generation
- agent review
- performance / backtest / settlement

### Supported run style

目前最穩陣嘅本地跑法係進入 package 目錄後用 package context：

- `cd tennis-wong-choi`
- `PYTHONPATH=src python -m tennis_wc.cli --help`

### Typical outputs

- `tennis-wong-choi/data/exports/`
- `tennis-wong-choi/tennis_wc.db`
- daily report markdown
- prediction / ledger / backtest artifacts

### Current reality

- mock provider 係預設
- 真實 provider 設定睇 `tennis-wong-choi/.env.example`
- tennis 自己有獨立 [README](tennis-wong-choi/README.md)

## HKJC / AU Reflectors

### HKJC Reflector main entry

- `.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py`

### AU Reflector main entry

- `.agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py`

### What they do

兩條 race reflector 主線而家都有 unified orchestrator wrapper，負責：

- 賽果 extraction / results file resolve
- 單 meeting review
- report generation
- archive backtest / review phase

### Typical outputs

- meeting-level reflector report
- results summary JSON / markdown
- review / backtest summary

## Related Components

### Extractors

- `hkjc_race_extractor`
  HKJC racecard / formguide / result / starter data extraction
- `au_race_extractor`
  AU Racenet extraction

### Auto engines

- `hkjc_wong_choi_auto`
  HKJC deterministic engine、renderer、tests、weight review tools
- `au_wong_choi_auto`
  AU deterministic engine、logic builder、archive calibrator、ML diagnostics

### Reflectors

- `hkjc_reflector`
  HKJC post-race review、walk-forward backtests、results database sync
- `au_reflector`
  AU shadow tests、matrix diagnostics、archive analysis

### Dashboard

- `Horse_Racing_Dashboard/`
  收集 HKJC + AU meeting snapshot，生成 static dashboard，同 Cloudflare Pages deploy

## Important File Conventions

以下命名規則係主流程會直接依賴：

- `Race_X_Logic.json`
  逐場 deterministic intermediate
- `Race_X_Auto_Analysis.md`
  逐場最終文字分析
- `Race_X_Auto_Scoring.csv`
  逐場 feature / matrix / rank 輸出
- `HKJC_Auto_Scoring.csv`
  HKJC 全 meeting scoring summary
- `Meeting_Auto_Scoring.csv`
  AU 全 meeting scoring summary
- `* Race * Facts.md` / `*Race N Facts.md`
  facts layer，後續 logic build / enrich 會直接食

如果手動整理檔案：

- 唔好亂改 race number
- 唔好混用 `Race 1` 同 `Race_1` 去代表唔同場次
- 盡量保留 meeting folder 日期 / 場地前綴

## Legacy And Deprecated Paths

以下內容仲保留喺 repo，但唔係主線：

- `.agents/archive/wong_choi_legacy_snapshot_20260526/`
- 某啲早期 LLM skeleton / compile scripts
- 舊版 workflow 文檔內提到 Gemini / LLM 必須參與嘅描述

用途主要係：

- 做舊版比對
- 檢查歷史決策
- 支援 archive / calibration / migration

唔應再將佢哋視為 HKJC / AU 目前嘅運行方式。

## Practical Rule Of Thumb

如果你只想安全咁理解 repo：

1. `SETUP.md` 負責安裝
2. `AGENTS.md` 負責講清楚現役架構同主入口
3. `HKJC Wong Choi` / `AU Wong Choi` 以 Python orchestrator 為準
4. `.agents/rules/GEMINI.md` 只係 legacy compatibility note，唔係主線運行依據
