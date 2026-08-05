# Windows Workstation Setup — Wong Choi

由零開始，喺一部新 Windows 機跑 AU / HKJC / NBA / Tennis Wong Choi 同 Cloudflare dashboard。
（macOS/Linux 睇 [SETUP.md](SETUP.md)。）

---

## 0. 先裝呢四樣

| 軟件 | 為咗乜 | 注意 |
|---|---|---|
| **Git for Windows** | clone repo + 跑 `deploy.sh` 用嘅 Git Bash | 裝嘅時候揀 **"Checkout as-is, commit Unix-style"**（見下面第 5 節） |
| **Python 3.9+** | 所有引擎 | 裝機時**一定要 tick「Add python.exe to PATH」** |
| **Node.js 20+** | Cloudflare wrangler deploy | LTS 版就夠 |
| **Google Drive Desktop** | AU 引擎嘅歷史資料 | 登入 `kelvin1761@gmail.com` |

---

## 1. Clone + bootstrap

```powershell
git clone https://github.com/Kelvin1761/Kelvin-Agents.git
cd Kelvin-Agents
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
```

`bootstrap.ps1` 會自動搞：venv、Python 依賴、Playwright Chromium、問你 `DATA_ROOT`、
最後行 data preflight。可以重複跑，唔會搞壞嘢。

之後每開一個新 shell：

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## 2. Google Drive —— AU 引擎嘅硬性要求

AU 評分要讀兩個 CSV（`AU_Historical_Raw_Race_Results.csv` 851 KB、
`AU_Backfill_Race_Results.csv` 78 KB）同 157 個 archive 賽事資料夾。呢啲**冇入 git**
（俾 `.gitignore` 嘅 `202*/` 擋咗），只喺 Google Drive。

1. 裝 Google Drive Desktop，登入 `kelvin1761@gmail.com`
2. 搵到 `我的雲端硬碟\Antigravity Shared\Antigravity`
3. **右 click → 「可離線使用」（Available offline）** ← 唔好跳過呢步。
   Streaming 模式下引擎讀檔會又慢又間歇性失敗。
4. bootstrap 問 `DATA_ROOT` 嗰陣，貼 `Antigravity` 呢個 folder 嘅完整路徑，例如：
   ```
   G:\My Drive\Antigravity Shared\Antigravity
   ```
   （寫入 `.wongchoi_data_root`，唔會入 git，所以兩部機各自設。）
5. **唔好**設 `WONGCHOI_AU_DATA_ROOT` / `.wongchoi_au_data_root`。呢個 AU-only
   覆寫係 Mac 專用（Mac 嘅 launchd 冇 CloudStorage 權限，所以 AU 樹搬落本機硬碟）。
   Windows 唔設就自動跌返 Drive 路徑，行為同以前一樣。

⚠️ 由 2026-08-05 起，Mac 嘅 AU source of truth 係本機硬碟，Drive 邊靠 Mac 每次跑完之後
鏡像返（launchd 底下都做得，實測寫 CloudStorage 係容許嘅）。但個 step 係 best-effort，
而且只鏡像「今次動過嘅場次」，所以 Windows 睇到嘅 `AU_Racing` 仍然**有機會落後**。做 AU
分析／backtest 之前，睇一睇最新場次夾嘅日期夠唔夠新；Mac 嗰邊嘅 run log 有 `[mirror]`
一行講咗抄咗幾多檔。

隨時可以自己驗：

```powershell
python wongchoi_paths.py
```

見到 `Data preflight     : OK` 就得。如果報 problem，佢會直接講你缺乜同點解決。

> **HKJC 唔受影響** —— 佢 14 個 `comprehensive_stats` prior CSV 已經入咗 repo，
> 唔靠 Google Drive。即係話 Drive 未搞好之前，你都已經可以跑 HKJC。

---

## 3. 每部機獨立嘅 MCP config

`.agents/mcp_config.json` hardcode 咗本機路徑，所以佢**已經唔入 git**（避免每次 sync 撞 conflict）。

```powershell
copy .agents\mcp_config.json.template .agents\mcp_config.json
```

然後開個 editor 改，將 `<DATA_ROOT>` 同 `<SQLITE_DB>` 換成你部機嘅路徑。
JSON 裡面 backslash 要 double escape：`"G:\\My Drive\\Antigravity Shared\\Antigravity"`。

---

## 4. 驗證安裝

```powershell
powershell -ExecutionPolicy Bypass -File .\run_tests.ps1
```

應該全部 9 個 suite PASS。

> 唔好試住用一句 `pytest` 跑齊 AU 同 HKJC —— AU 同 HKJC 各有一個叫 `scoring`
> 嘅 module，同一個 Python process 裡面會互相蓋過，一定 ImportError。
> `run_tests.ps1` 已經幫你每個 suite 開獨立 process。

---

## 5. 行 Cloudflare deploy（要 Git Bash）

`deploy.sh` 係 bash-only，冇 PowerShell 版。

### 5a. 換行符 —— 已經幫你搞好

Repo 有 [.gitattributes](.gitattributes) 強制 `*.sh` 用 LF。冇呢個嘅話，
Git for Windows 會將 `deploy.sh` 改成 CRLF，跟住 Git Bash 就出：

```
bash: ./deploy.sh: /bin/bash^M: bad interpreter
```

如果你係喺加 `.gitattributes` 之前 clone 咗，行一次呢句重新 normalize：

```bash
git rm --cached -r . && git reset --hard
```

### 5b. Cloudflare 認證（逐部機，要做一次）

兩個選擇。**Option A**（推薦）：

```bash
npx wrangler@4.86.0 login
```

**Option B** —— 用 API token：

```powershell
$env:CLOUDFLARE_API_TOKEN="<your-token>"
```

KV namespace（`WC_STATE`）嘅 id 已經入咗 [wrangler.toml](Horse_Racing_Dashboard/wrangler.toml)，
唔需要重新開。

### 5c. Deploy

喺 **Git Bash** 裡面：

```bash
cd Horse_Racing_Dashboard
./deploy.sh --build-only   # 先試 build，唔會 push 上 Cloudflare
./deploy.sh                # 真正 deploy
```

wrangler 版本已經 pin 咗 `4.86.0`（`deploy.sh` 同 `package.json` 兩邊）。
想試新版就設 `WC_WRANGLER_VERSION`。

---

## 6. 本機 dashboard（唔需要 Cloudflare）

直接 double-click：

```
Horse_Racing_Dashboard\start-dashboard.bat
```

跟住開 <http://localhost:8000>。

---

## 7. 已知限制

| 項目 | 狀況 |
|---|---|
| **Tennis DB** | `tennis_wc.db` 冇入 git → 新機由空 DB 開始。跑 `tennis-wc init-db` 再由 API 重建。 |
| **Tennis 排程** | 只有 macOS launchd 版。Windows 要用 Task Scheduler 自己叫 `scripts\tennis_daily_schedule.py`。 |
| ~~`Race compliance QA` 測試~~ | ✅ 已修（`parse_result_json` 而家識讀 archive results mapping）。全部 suite 應該綠。 |
| **`launch-wrapper.sh`** | macOS 專用，Windows 用 `start-dashboard.bat` 代替。 |

---

## 8. 中文亂碼

`bootstrap.ps1` 同 `run_tests.ps1` 已經自己設好 UTF-8。手動開 shell 想穩陣就：

```powershell
$env:PYTHONUTF8="1"
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
```
