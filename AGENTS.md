<!-- Cross-platform compatibility note: this file is the primary repo-facing guide. -->
<!-- `.agents/rules/GEMINI.md` is deprecated and kept only as a legacy compatibility note. -->

# Antigravity Agent Guide

> `GEMINI.md` 已 deprecated。新用戶同現役 workflow 請以 `SETUP.md` 同 `AGENTS.md` 為準。

## 工作守則（Claude Code 同 Codex 一律適用）

呢個 repo 同時俾 Claude Code 同 Codex 用。`CLAUDE.md` 只係 `@AGENTS.md` 嘅
import，所以**呢份文件係唯一真源** —— 新規則加喺呢度，唔好喺 `CLAUDE.md` 另寫。

### 交嘢之前一定要跑

```bash
./檢查.sh --quick     # 改完 code 即刻跑
./檢查.sh             # 交嘢之前跑齊（連單元測試）
```

紅燈就唔好 commit。每一項都會印咗係咩問題、點解、點修。

另外三條：`./健康.sh`（營運有冇斷）、`./備份.sh`（備份去外置碟）、
`./整理.sh`（清已合併嘅分支）。**`檢查.sh` 查 code，`健康.sh` 查資料同排程 ——
兩者唔互相覆蓋。**

### commit 同 push

用 `./保存.sh --path <今次scope> "commit message"`。佢會交畀 Central release
manager 自動做 policy gate、exact-scope commit／push、immutable manifest 同 Telegram；
code／model／automation／deployment 要 `/approve SHA` 先 merge／activate。禁止再用舊式
「掃晒成個 worktree」保存。

**多個 agent session 同時開工**：commit 之前先睇 `git status`。只 stage 你自己
今次改嘅嘢，唔好 `git add -A` 連人哋未 commit 嘅工作一齊掃入去。

### 五件唔可以做嘅事

1. **唔好手寫模型說明。** `Wong Choi 模型說明/` 入面啲檔由
   `.agents/skills/shared_racing/scripts/explain_model.py` 生成。上一份人手寫嘅
   過期咗兩個月冇人發現（寫住 7 維，live 係 6 維；叫人對照一個唔存在嘅檔案）。
   要改內容就改生成器。

2. **改完評分 code，一定要清 bytecode cache 先做 A/B。** macOS 系統 Python 將
   `.pyc` 放喺 `~/Library/Caches/com.apple.python`（**唔係** `__pycache__`），
   而且只靠 `(mtime, 檔案大細)` 判斷要唔要重新編譯。權重由 `0.08037` 改做
   `0.09037` **位元組數一樣**，同一秒內改完再跑 = 靜靜行返舊 bytecode。
   `./檢查.sh` 第 0 步已經做咗；自己手動跑就要
   `export PYTHONDONTWRITEBYTECODE=1`。
   **「A/B 結果同 baseline 一模一樣」唔等於「呢個改動冇效果」。**

3. **唔好將引擎目錄本身放上 `sys.path`。** 引擎而家係 package：
   `au_racing_engine` / `hkjc_racing_engine`。要 import 就
   `sys.path.insert(0, str(<...>/scripts))` 然後
   `from au_racing_engine.scoring import ...`。插住 package 目錄本身會令入面啲
   module 又變返 top-level，兩邊 `scoring` 就再次撞名。

4. **唔好合併 AU 同 HKJC 嘅模型。** 睇落好似抄嘅，實測 589 個 function 得 5 個
   逐字一樣。維度數目、合成公式、feature 數量、初出馬處理全部唔同。
   跨平台工具嘅正確做法係「一個腳本 + `--platform` flag」。

5. **改咗評分邏輯，要順手更新兩樣嘢**：
   ```bash
   python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform au --record
   python3 .agents/skills/shared_racing/scripts/data_contract.py  --platform au --calibrate
   ./Wong\ Choi\ 模型說明/更新模型說明.sh
   ```
   前提係你已經確認過個變化係你想要嘅 —— golden 會逐匹馬印出邊度變咗。

### 發佈閘：死欄位會攔住 deploy

`step_dashboard` 喺 snapshot 驗證**之前**跑 `data_contract --meeting --gate`，
逐個場次檢查欄位級健康。只有**死欄位**會攔（幾乎每匹馬中性，而基準話呢個欄位
平時有值）；細場次資料稀疏只出警告。

呢個閘存在嘅原因：2026-08-22 十個場次全部 `pace_figure_score` 中性 60、場內
SD 0.00 —— 排名 **12.2% 權重完全死**，而抽取報「成功」、九個 suite 全綠、
snapshot 結構正常、日誌零錯。真兇係 claw 一句被吞嘅 ImportError
（`_l600_delta` 條 sys.path 插咗 package 目錄本身）。實測 71% 場次 top-4 會唔同。

**改咗評分邏輯之後要重新 calibrate**，唔然閘會出 `stale-baseline` 警告：

```bash
python3 .agents/skills/shared_racing/scripts/data_contract.py --platform au \
  --calibrate --since 2026-08-05 --limit 2000
```

### 已知失敗

**而家冇。** `run_tests.sh` 九個 suite 全綠。

之前 `Agent scripts` 由 2026-08-03 起一直紅：`test_hkjc_high_quality_features.py`
assert 緊兩個冇 merge 過嘅嘢 —— `rating_series` 只存在於
`scratch/hkjc_high_quality_dimension_gate.py`，而 `parse_normalized_sectionals`
**成個 repo 都唔存在**。2026-08-21 改為 `unittest.expectedFailure` 並寫明原因：
一個永遠紅嘅 suite 會訓練到人忽略佢，然後真嘅 regression 就冇人睇到。
如果將來真係 merge 咗，pytest 會報 XPASS 提醒你拆走 decorator。

### 改模型嘅規矩

呢節係**證據紀律**，同上面「五件唔可以做嘅事」一樣硬。詳細做法喺
`.claude/skills/` 嘅四個 skill 度（`model-regression-gate`、`leakage-audit`、
`feature-ablation`、`data-quality-audit`、`experiment-review`）—— 呢度只寫規矩本身。

**把尺喺邊**：[`docs/model-evaluation-contract.md`](docs/model-evaluation-contract.md)
—— AU 判決規則、bootstrap 設定、dev/holdout 切法、兩邊 baseline、同五個已知缺陷。
**改動嗰份文件 = 改動判決規則**，要當一個獨立改動先論證，唔可以同候選一齊改。

- **冇跑過評估，唔准講「改善」。** 「code 睇落合理啲」「理論上應該好啲」唔係證據。
- **改之前先量 baseline。** baseline 同 candidate 要行同一份語料、同一個時間窗。
  跨 harness 攞數字互相比 = 錯結論。
- **holdout 唔准用嚟調參，亦唔准改切法。** 換指標／換窗／換 top-K 去救個候選，
  一律當 REJECT。
- **防目標洩漏同未來資訊洩漏。** 對每個欄位問：「呢個確切資訊，喺落注嗰刻真係
  拎得到？」答唔到就 flag，唔准當安全。**統計閘門捉唔到洩漏** —— 一個洩漏特徵
  試過 5/5 fold 全過、holdout +17.58pp。
- **賠率／市場價唔准做隱藏 proxy。** 除非個 methodology 明文寫住佢係模型一部分。
  回測取賠率一定要最早快照（tennis：`MIN(id)`，後面嘅係走地價）。
- **唔准只針對最近一日／一個場次去調。** 單日結果冇功效。
- **優先睇 out-of-sample。** dev + 時間 fold 揀，holdout 只做最後確認。
- **保住可重現性。** 記低命令、dataset 路徑、commit hash。改評分 code 之前
  先清 bytecode（`./檢查.sh` 第 0 步；手動跑要 `PYTHONDONTWRITEBYTECODE=1`）。
- **簡單而穩健 > 複雜而邊際。** 一齊改幾樣就要做 ablation，逐樣量邊際貢獻；
  分唔開嘅就唔留。
- **多過一個特徵／權重一齊郁，一定要 ablation。** 「合併實驗升咗」講唔出邊樣有用。
- **有意義嘅實驗要記落 `docs/experiments/`。** 開始新假設之前先 grep 舊記錄。
- **失敗實驗係有用資訊，要照記，唔准掩飾。** 記「點失敗」，唔係只寫「冇用」。
- **失敗實驗嘅 model code 唔准自動 commit。** 記錄可以 commit，改動唔可以。
- **唔准無條件背景 push。** 只有用戶明確要求保存／交付／release，先可由
  `./保存.sh --path …` exact-scope 自動 push；高風險 release 仍要 immutable SHA 批准。
  失敗實驗嘅 model code 永遠唔可以靠呢個授權自動 push。
- **唔准喺冇可退回 baseline 嘅情況下覆蓋一個 known-good 模型。**
  `golden_scoring` 舊 snapshot 唔准同 code 一次過覆蓋。
- **模型表現跌，先查數據管線，唔好即刻怪模型。** 呢個 repo 每個貴嘅 bug 都係
  「欄位仍在、code 仍行、test 全綠，但值靜靜變空／變常數／變過期」。
- **證據弱就報唔確定，唔准砌一個結論。**

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

- `.claude/skills/`
  Claude Code project skills —— 證據紀律（`model-regression-gate`、
  `leakage-audit`、`feature-ablation`、`data-quality-audit`、
  `experiment-review`）同幾個 vendor 返嚟嘅 upstream skill。
  vendor 嗰批唔好手改，改咗就同上游脫節。
- `docs/model-evaluation-contract.md`
  **判決規則同 baseline 嘅唯一真源。** 改佢 = 改把尺。
- `docs/experiments/`
  實驗記錄。開始新假設之前先 grep 呢度。
- `docs/audits/`、`docs/handoff/`
  唯讀審計報告，同俾另一個 agent 獨立覆核用嘅交接。
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
- `Data_Health.json`
- `Data_Health.md`

### Daily automation

HKJC unattended scheduler：

- `.agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py`

佢負責休季 racecard watch、賽前 full pipeline、immutable prediction snapshot、
賽後 unified reflector、每週 Telegram review 同 candidate PR approval gate。
候選只會建立 non-draft PR，唔會自動 merge。

macOS launchd 用 `.wongchoi_hk_data_root` 指向 local primary，再用
`.wongchoi_hk_mirror_root` best-effort mirror 去 Google Drive，避免背景程序被
CloudStorage TCC 阻擋。

macOS 安裝入口：

- `.agents/skills/hkjc_racing/hkjc_daily_auto/install_macos_launchd.sh`

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

### Daily automation

NBA unattended scheduler：

- `.agents/skills/nba/nba_daily_auto/nba_daily_schedule.py`

佢負責 Sydney-time pregame、off-season dormant、immutable prediction snapshot、
post-game reflector、results-backed archive、health／Telegram 同 dashboard deploy。安裝入口：

- `.agents/skills/nba/nba_daily_auto/install_macos_launchd.sh`

Settlement 會先輸出本機 proposal；未獲明確批准前唔會自動 POST／apply 去外部 ledger。

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
