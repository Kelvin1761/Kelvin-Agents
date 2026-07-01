# Antigravity Setup Guide

呢份文件以目前 repo 內實際存在嘅腳本、依賴同資料夾為準，目標係令新用戶 clone 完之後，可以喺 macOS 或 Windows 完成基本安裝，並成功運行以下主流程或相關工具：

- `HKJC Wong Choi`
- `AU Wong Choi`
- `NBA Wong Choi`
- `tennis-wong-choi`
- `HKJC Reflector`
- `AU Reflector`

如果你只想畀新用戶一個入口，**直接叫佢由呢份 `SETUP.md` 開始就可以**。呢份文件會帶佢完成：

- 要讀邊幾份文檔
- 要安裝咩
- 要設咩環境
- 點驗證 setup
- 點跑 HKJC Wong Choi
- 點跑 AU Wong Choi
- 點跑 NBA Wong Choi
- 點跑 tennis-wong-choi
- 點跑 HKJC / AU Reflector
- 點配置 Cloudflare deployment
- 點 troubleshoot 常見問題

## ⚡ Quick Start（新機一鍵設定）

新電腦最快上手，照呢 3 步：

```bash
# 1. Clone 去一個【本地】資料夾（唔好放喺 Google Drive — 見下面警告）
git clone https://github.com/Kelvin1761/Kelvin-Agents.git ~/dev/Kelvin-Agents
cd ~/dev/Kelvin-Agents

# 2. 跑 bootstrap（建 venv + 裝依賴 + Playwright + 設定資料位置 + 驗證）
./bootstrap.sh                 # macOS / Linux
#  powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1   # Windows

# 3. 每次開新 shell 先 activate
source .venv/bin/activate      # macOS / Linux
#  .venv\Scripts\Activate.ps1  # Windows
```

bootstrap 會問你 **`DATA_ROOT`** —— 即係啲大型「Wong Choi … Analysis」資料夾放邊（通常喺 Google Drive）。你貼個路徑，佢寫入 `.wongchoi_data_root`（每部機各自設定，唔入 git）。`wongchoi_paths.py` 會據此解析所有資料路徑，所以 **Mac 同 Windows 都跑得**。想手動設亦得：設環境變數 `WONGCHOI_DATA_ROOT`。

> ⚠️ **唔好將 code repo 放喺 Google Drive 同步資料夾入面。** Drive 同步 `.git` 會令 `git commit` 卡死、多機之間 branch ref 跳動、檔案消失（實測過）。**Code 放本地、用 `git pull/push` 經 GitHub 同步;資料先放 Drive。** 詳見 `wongchoi_paths.py` 開頭註解。

## Language And Reply Style

如果你係用 Antigravity 入面嘅 agents / workflows 同新用戶或團隊成員協作，建議統一以下預設：

- 日常回覆：用香港繁體中文（廣東話口吻）
- implementation plan / next-step plan：都用香港繁體中文
- code、file path、CLI command、package name：維持英文原文

簡單講：

- **reply everything in Hong Kong Chinese**
- **plan everything in Hong Kong Chinese**
- **code stays in English**

咁可以減少新用戶誤會，同時保持 codebase 同 terminal commands 易讀。

## 0. Start Here

新用戶建議按以下次序完成：

1. 由上到下讀完整份 `SETUP.md`
2. 跟住做 clone、venv、dependency install、Playwright install
3. 跑本文件嘅 verification commands
4. 根據需要跑 HKJC 或 AU 主流程
5. 完成第一次 successful run 後，再讀 [AGENTS.md](AGENTS.md) 了解完整 agent / pipeline 架構

如果只需要高層 folder map，可再讀：

- [README.md](README.md)
- [AGENTS.md](AGENTS.md)
- [.agents/ARCHITECTURE.md](.agents/ARCHITECTURE.md)
- [CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md)

但如果目標係「clone repo 後成功跑到主流程」，**其實只跟住呢份 `SETUP.md` 已經足夠**。

## 0.1 Quick Onboarding Checklist

新用戶可以直接照住 tick：

- clone repo
- 安裝 `Python 3.10+`
- 建立 `.venv`
- 安裝 Python dependencies
- 執行 `python -m playwright install chromium`
- 跑 help / verification commands
- 跑一次 `HKJC Wong Choi`、`AU Wong Choi`、`NBA Wong Choi`、`tennis-wong-choi` 或 reflector
- 如需 dashboard，再處理 `Node.js` / `npx` / `deploy.sh`
- 如需 Cloudflare deploy，再讀 [CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md)

## 1. What You Need

- `Git`
- `Python 3.10+`
- 可連網環境
- 如果要用 dashboard / Cloudflare deploy：
  `Node.js` 同 `npx`

說明：

- `HKJC Wong Choi` 同 `AU Wong Choi` 現已係 **100% Python-driven**。
- 運行 HKJC / AU 主流程 **唔需要 Gemini 或其他 LLM**。
- `NBA Wong Choi` 同 `tennis-wong-choi` 亦有實際可跑入口，但佢哋嘅架構同 HKJC / AU 並唔完全相同。
- repo 而家已提供 root `requirements.txt`，方便 clone 後直接安裝主線依賴。
- `.agents/rules/GEMINI.md` 已 deprecated，唔係新用戶 onboarding 入口。

## 2. Clone The Repository

```bash
git clone https://github.com/Kelvin1761/Kelvin-Agents.git ~/dev/Kelvin-Agents
cd ~/dev/Kelvin-Agents
```

> ⚠️ Clone 去一個**本地**路徑（如 `~/dev/Kelvin-Agents`），**唔好**放喺 Google Drive 同步資料夾。多機經 Drive 同步同一個 `.git` 會令 commit 卡死、ref 跳動、檔案消失。各機之間用 `git pull/push`（GitHub）同步就夠。

clone 完之後，跑 `./bootstrap.sh`（或 Windows 嘅 `bootstrap.ps1`）就會自動做埋下面 3–5 節（venv / 依賴 / Playwright / 資料路徑）。想手動逐步做就繼續睇落去。

### 2.1 設定資料位置（DATA_ROOT）

啲大型資料夾（`Wong Choi Horse Race Analysis`、`Wong Choi NBA Analysis`、`Wong Choi Tennis Analysis`、`NBA_ML_Dataset` 等）唔入 git，通常留喺 Google Drive。`wongchoi_paths.py` 會用以下次序搵佢哋：

1. 環境變數 `WONGCHOI_DATA_ROOT`
2. repo root 嘅 `.wongchoi_data_root` 檔（一行路徑，唔入 git）
3. 都冇就用 repo 本身

設定方法（揀一個）：

```bash
# macOS 例子：指向 Google Drive 嘅 Antigravity 資料夾
echo "/Users/<you>/Library/CloudStorage/GoogleDrive-<acct>/我的雲端硬碟/Antigravity Shared/Antigravity" > .wongchoi_data_root
```

```powershell
# Windows 例子
Set-Content .wongchoi_data_root "G:\我的雲端硬碟\Antigravity Shared\Antigravity"
```

驗證：`python3 wongchoi_paths.py` —— 應該見到每個資料夾 `(exists)`。

## 3. Create A Virtual Environment

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

### Windows PowerShell

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

如果你部機預設唔係 UTF-8，建議喺 Windows 先設：

```powershell
$env:PYTHONUTF8="1"
```

## 4. Install Python Dependencies

主流程目前實際會用到以下 Python 套件。建議直接用 root requirements file：

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

套件來源依據目前 repo 內 active scripts，例如：

- HKJC / AU extractor：`playwright`、`beautifulsoup4`、`requests`、`curl-cffi`
- Facts / scoring / archive tooling：`pandas`、`openpyxl`
- HKJC PDF / starter data：`pdfplumber`
- Dashboard backend：`fastapi`、`uvicorn`、`watchdog`
- HKJC `.numbers` parsing：`numbers-parser`
- NBA extractor / NBA reflector：`nba_api`

如果你只係想先跑 HKJC / AU 主流程，以上 command 已經係目前最接近「完整主線 runtime 依賴」嘅安裝方式。

### tennis-wong-choi 額外說明

`tennis-wong-choi` 係 repo 入面一個獨立 Python package。根據目前 codebase，同 mock provider 跑基本流程時唔需要額外第三方依賴；如需額外工具：

- 跑測試：`pytest`
- 跑 tennis dashboard：`streamlit`

如果你想補裝 optional workstation extras：

```bash
pip install -r requirements-optional.txt
```

## 5. Optional Environment Variables

### `PYTHONUTF8=1`

Windows 建議開啟，避免中文 meeting / 檔名 / markdown 輸出亂碼。

### `ANTIGRAVITY_ROOT`

如果你唔係將 repo 放喺原本 Google Drive 路徑，而又要用 dashboard backend，可手動指定：

### macOS

```bash
export ANTIGRAVITY_ROOT="/absolute/path/to/Antigravity"
```

### Windows PowerShell

```powershell
$env:ANTIGRAVITY_ROOT="C:\path\to\Antigravity"
```

### `WC_DISABLE_POST_SUCCESS_DEPLOY=1`

如果你只想跑分析、唔想成功後自動嘗試 deploy 去 Cloudflare：

### macOS

```bash
export WC_DISABLE_POST_SUCCESS_DEPLOY=1
```

### Windows PowerShell

```powershell
$env:WC_DISABLE_POST_SUCCESS_DEPLOY="1"
```

## 6. Verify The Setup

完成安裝後，建議至少跑以下幾個檢查：

```bash
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py --help
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py --help
python .agents/skills/nba/nba_orchestrator.py --help
cd tennis-wong-choi && PYTHONPATH=src python -m tennis_wc.cli --help
python .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py --help
python .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py --help
python Horse_Racing_Dashboard/generate_static.py --help
python .agents/scripts/safe_file_writer.py --help
```

如果以上都正常出 help text，而 `python -m playwright install chromium` 亦完成，基本環境就算 ready。

如果你想做一個最短 smoke test，可以用以下判斷：

- `hkjc_orchestrator.py --help` 成功
- `au_orchestrator.py --help` 成功
- `nba_orchestrator.py --help` 成功
- `tennis_wc.cli --help` 成功
- HKJC / AU reflector orchestrator `--help` 成功
- `generate_static.py --help` 成功

咁代表主入口、dashboard snapshot generator 同共用 Python 環境都基本可用。

## 7. Run HKJC Wong Choi

主入口：

`.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py`

### 用 HKJC URL 直接跑

```bash
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/05/31&Racecourse=ST&RaceNo=1"
```

### 用已存在 meeting folder 重跑

```bash
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py "/absolute/path/to/2026-05-31_ShaTin"
```

### HKJC 會做乜

- 如有 URL：先跑 HKJC extractor，提取全日 race data
- 之後跑 `.agents/scripts/run_prerace_pipeline.py` 生成 `* Race * Facts.md`
- 再建立 / 更新 `Race_X_Logic.json`
- 最後交畀 `hkjc_wong_choi_auto` 做 deterministic scoring 同 analysis render

如果你只需要同新用戶講一句，可以直接講：

```bash
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py "<HKJC racecard URL or meeting folder>"
```

### HKJC 常見輸出

- `* Race * Facts.md`
- `Race_X_Logic.json`
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- `HKJC_Auto_Scoring.csv`

### HKJC Meeting Folder 命名

目前 orchestrator helper 會用以下前綴建立 / 尋找 meeting folder：

- `YYYY-MM-DD_ShaTin`
- `YYYY-MM-DD_HappyValley`

## 8. Run AU Wong Choi

主入口：

`.agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py`

### 用 Racenet URL 直接跑

```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "https://www.racenet.com.au/form-guide/horse-racing/flemington-20260530/example-race-1/overview"
```

### 用已存在 meeting folder 重跑

```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "/absolute/path/to/2026-05-30 Flemington Race 1-9"
```

### 只用現成 Logic 重跑 auto scorer

```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "/absolute/path/to/Race_1_Logic.json"
```

### AU Folder 最少要有乜

如果唔係用 URL extraction，而係直接用 meeting folder，至少要有：

- 每場對應 `*Racecard.md`
- 每場對應 `*Formguide.md`

之後 orchestrator 會：

- 生成 `*Race N Facts.md`
- 建立 / 更新 `Race_X_Logic.json`
- 跑 `au_wong_choi_auto` 寫出 deterministic analysis / scoring

如果你只需要同新用戶講一句，可以直接講：

```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<Racenet URL, meeting folder, or Race_X_Logic.json>"
```

### AU 常見輸出

- `*Racecard.md`
- `*Formguide.md`
- `*Race N Facts.md`
- `Race_X_Logic.json`
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- `Meeting_Auto_Scoring.csv`

### AU Meeting Folder 命名

目前 AU orchestrator 會用 meeting folder 名稱前綴去反查 extraction 輸出，所以建議保留以下格式：

- `YYYY-MM-DD <Venue> ...`
- 或 `YYYY-MM-DD_<Venue>_Race_...`

## 9. Run NBA Wong Choi

主入口：

`.agents/skills/nba/nba_orchestrator.py`

### 基本跑法

```bash
python .agents/skills/nba/nba_orchestrator.py --date 2026-05-27
```

### 常用模式

列出當日賽事：

```bash
python .agents/skills/nba/nba_orchestrator.py --date 2026-05-27 --list
```

只跑單場：

```bash
python .agents/skills/nba/nba_orchestrator.py --date 2026-05-27 --game ATL_NYK
```

查看 pipeline 狀態：

```bash
python .agents/skills/nba/nba_orchestrator.py --date 2026-05-27 --status
```

### NBA 額外現況說明

目前 `NBA Wong Choi` 有實際 orchestrator 同自動腳本鏈，但 repo 內仍然保留咗一啲舊描述，例如檔頭提及 pre-filled skeleton / analyst phase。對新用戶嚟講，最重要係：

- 主入口已存在並可直接運行
- `nba_api` 係必要依賴之一
- 分析輸出會寫入 `{YYYY-MM-DD} NBA Analysis/`

## 10. Run HKJC / AU Reflector

### HKJC Reflector

主入口：

`.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py`

基本跑法：

```bash
python .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py "<meeting_dir>"
```

常用選項：

```bash
python .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py "<meeting_dir>" --json
python .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py "<meeting_dir>" --skip-review
```

### AU Reflector

主入口：

`.agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py`

基本跑法：

```bash
python .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py "<meeting_dir>"
```

如已有 results file：

```bash
python .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py "<meeting_dir>" "<results_file>"
```

常用選項：

```bash
python .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py "<meeting_dir>" --json
python .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py "<meeting_dir>" --skip-backtest
```

### Reflector 現況

HKJC 同 AU reflectors 而家都有 unified orchestrator wrapper，可以直接由單一入口跑。呢兩條 reflector 主線都係 Python-first workflow。

## 11. Run tennis-wong-choi

`tennis-wong-choi` 係獨立 package，建議由佢自己個資料夾運行。

### 已驗證可跑方式

```bash
cd tennis-wong-choi
PYTHONPATH=src python -m tennis_wc.cli --help
```

### 基本初始化

```bash
cd tennis-wong-choi
cp .env.example .env
PYTHONPATH=src python -m tennis_wc.cli init-db
PYTHONPATH=src python -m tennis_wc.cli config-check
PYTHONPATH=src python -m tennis_wc.cli provider-smoke --provider tennis --date 2026-05-08 --tour ATP
PYTHONPATH=src python -m tennis_wc.cli provider-smoke --provider odds --date 2026-05-08
```

### Daily flow

```bash
cd tennis-wong-choi
PYTHONPATH=src python -m tennis_wc.cli run-daily --date 2026-05-08
PYTHONPATH=src python -m tennis_wc.cli predict-daily --date 2026-05-08
PYTHONPATH=src python -m tennis_wc.cli run-agents --date 2026-05-08
PYTHONPATH=src python -m tennis_wc.cli generate-report --date 2026-05-08
```

### tennis 現況

- mock provider 係預設，所以新用戶可以唔靠付費 API 先測通 CLI
- 真實 provider 設定請參考 `tennis-wong-choi/.env.example`
- `tennis-wong-choi/README.md` 有更完整 tennis domain 說明

## 12. Dashboard And Cloudflare Deploy

### 一句講晒：任何機、任何位置，都係 run 一個指令

```bash
./deploy.sh
```

**唔使理你而家喺 Google Drive 個 copy 定係本地 clone 度 run —— 兩邊都會正確發最新版。**
唔使記路徑、唔使自己設環境變數。冇 memory 嘅 agent（例如 Codex）照跟呢句就得。

只想 build snapshot、唔真係推上線：

```bash
./deploy.sh --build-only
```

### 背後點運作（點解唔會再發舊版）

呢個 repo 曾經因為 **code + `.git` 放喺 Google Drive、多機同步** 而反覆出事：
Drive 個 checkout 會 stranded 喺舊 commit，直接由嗰度 build 就會發**舊版 dashboard**
（唔見咗 `評級矩陣` / `數據判讀`，投注掣變返「匯出」）。依家有 **三重防線**：

1. **Drive checkout 已退役 → 自動轉駁 proxy。**
   Drive 上嘅 `Horse_Racing_Dashboard/deploy.sh`（同 root `./deploy.sh`）唔再自己 build，而係自動：
   - 搵本機 off-Drive clone（預設 `~/dev/Kelvin-Agents`）；**冇就自動 `git clone`**（首次免手動）
   - `git checkout main` + `git pull --ff-only origin main`（同步到最新）
   - 用**本機自己嘅 Drive 資料路徑**做 data root（由 script 位置自動推算，用 `WONGCHOI_DATA_ROOT` 注入 —— 所以新機 clone 完即用，唔使預先設 `.wongchoi_data_root`）
   - 交俾 off-Drive clone 果個有 guard 嘅 `deploy.sh`

2. **Build guard（喺 off-Drive clone 個 deploy.sh 入面）。**
   推上 Cloudflare 之前會驗證 build 有齊 `評級矩陣` / `數據判讀` / `匯入投注記錄`；
   **冇齊就直接 abort，唔會誤發舊版**，並提示去 off-Drive clone 部署。`--build-only` 都會行呢個檢查。

3. **Off-Drive clone 係唯一真正 build + 推送嘅地方**（`~/dev/Kelvin-Agents`），
   果度 git 即時、唔會 hang，永遠對住 GitHub `main`。

> 直接由 off-Drive clone deploy 亦得（其實 proxy 最後都係行呢句）：
> ```bash
> cd ~/dev/Kelvin-Agents && git checkout main && git pull && ./deploy.sh
> ```

### 喺一部新機首次 deploy —— 環境要求（proxy 冇能力自動裝，要人手備妥一次）

proxy 可以自動 clone + pull + 揀正確資料根，但以下係作業系統／帳戶層面嘅嘢，**每部機做一次**：

1. **GitHub 憑證** —— 私 repo，自動 `git clone` 要你已登入（如 `gh auth login`、SSH key、或 credential manager）。
   自動 clone 失敗嘅話，proxy 會 `exit 1` 兼印手動 `git clone` 指令，跟住做一次就得。
2. **Node.js + npx** —— 行 `wrangler` 用。
3. **Cloudflare 認證**（推送嗰步先需要）：
   - `wrangler login`（本機 session），或
   - 設 `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`
   - 詳見 [CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md)
4. **Windows**：一定要用 **Git Bash 或 WSL** 行 `deploy.sh`（Bash script，cmd/PowerShell 行唔到）。
   （只想本機生成 snapshot 唔推送，可直接 `python Horse_Racing_Dashboard/generate_static.py`。）

### 可調環境變數（通常唔使郁）

| 變數 | 用途 | 預設 |
|------|------|------|
| `WONGCHOI_OFFDRIVE_CLONE` | off-Drive clone 路徑 | `~/dev/Kelvin-Agents` |
| `WONGCHOI_REPO_URL` | 自動 clone 用嘅 repo 網址 | `https://github.com/Kelvin1761/Kelvin-Agents.git` |
| `WONGCHOI_DATA_ROOT` | 資料根（proxy 會自動注入本機 Drive 路徑；手動 deploy 先要自己設） | 由 proxy 推算 |
| `WC_CLOUDFLARE_PAGES_PROJECT` | Cloudflare Pages project 名 | `wongchoi-dashboard` |

### 自動 deploy（orchestrator 跑完之後）

HKJC / AU 主 orchestrator 成功完成後，預設會自動嘗試 Cloudflare deploy（一樣經上面條 proxy）。想停用：

- command flag：`--skip-cloudflare-deploy`
- env var：`WC_DISABLE_POST_SUCCESS_DEPLOY=1`

> ⚠️ **切記：唔好喺 Google Drive 個 copy 度自己改 `deploy.sh` 或者繞過 proxy 直接 build。**
> 一律 run `./deploy.sh`，等 proxy + guard 保護你。真正發佈只可以由 off-Drive clone 出。

## 13. Troubleshooting

### `ModuleNotFoundError`

通常係：

- 未 activate `.venv`
- 套件裝咗去另一個 Python
- 遺漏咗 `playwright` / `numbers-parser` / `pdfplumber`

先確認：

```bash
python -V
python -m pip list
```

### `nba_api` not installed

```bash
pip install nba_api
```

### Playwright browser not installed

```bash
python -m playwright install chromium
```

### tennis-wong-choi import error

如果見到 `ModuleNotFoundError: No module named 'tennis_wc'`，代表你未用 package context 啟動。請改用：

```bash
cd tennis-wong-choi
PYTHONPATH=src python -m tennis_wc.cli --help
```

### Windows 中文亂碼 / UnicodeEncodeError

```powershell
$env:PYTHONUTF8="1"
```

### Dashboard backend 搵唔到 repo root

設返 `ANTIGRAVITY_ROOT` 去你 clone repo 嘅實際位置。

### Cloudflare deploy 失敗

檢查：

- `npx` 係咪可用
- Cloudflare / Wrangler auth session 係咪已就緒

如果你只想保留本地分析輸出，可以暫時加：

```bash
--skip-cloudflare-deploy
```

## 14. Current Reality Check

截至目前 repo 狀態：

- `HKJC Wong Choi` 主線：full Python
- `AU Wong Choi` 主線：full Python
- `HKJC Reflector` 主線：unified Python orchestrator
- `AU Reflector` 主線：unified Python orchestrator
- `NBA Wong Choi`：有實際 orchestrator，但 repo 內仍存在部分舊式 analyst / skeleton 描述
- `tennis-wong-choi`：獨立 package + CLI，mock provider 可直接測通
- LLM-era scripts、legacy snapshots、compile templates 仍然存在，但已唔係主運行入口
- `.agents/archive/wong_choi_legacy_snapshot_20260526/` 只供手動比對，唔應視為主線

## 15. What To Read After Setup

如果新用戶已經完成 setup，同成功跑到一次主流程，下一步建議睇：

1. [AGENTS.md](AGENTS.md)
   了解目前 HKJC / AU / NBA / tennis / reflector 架構、輸入輸出、命名規則
2. [README.md](README.md)
   作 repo 首頁總覽
3. [.agents/ARCHITECTURE.md](.agents/ARCHITECTURE.md)
   只用嚟理解高層 folder map

簡單講：

- **要成功安裝同跑起主流程**：睇 `SETUP.md`
- **要理解現役架構**：睇 `AGENTS.md`
- **要高層總覽**：睇 `README.md` 同 `ARCHITECTURE.md`
