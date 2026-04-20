# 🚀 Antigravity Agent Setup Guide

> 本指南覆蓋所有 Agent Pipeline（HKJC 賽馬、AU 賽馬、NBA 籃球、LoL 電競）。
> 跟住步驟做，確保你嘅環境同主機完全一致。

---

## 📋 目錄

1. [Agent 核心規則](#1-agent-核心規則)
2. [系統需求](#2-系統需求)
3. [安裝步驟](#3-安裝步驟)
4. [Windows 額外設定](#4-windows-額外設定)
5. [首次運行驗證](#5-首次運行驗證)
6. [使用指南](#6-使用指南)
7. [架構概覽](#7-架構概覽)
8. [常見問題 FAQ](#8-常見問題-faq)
9. [故障排解](#9-故障排解)

---

## 1. Agent 核心規則

> ⚠️ **以下規則嘅優先級高於所有其他指引。所有 Agent 必須嚴格遵守。**

所有回覆（包括對話、實作計畫書、任務進度、總結等）都必須使用繁體中文（香港慣用語/港式中文）來撰寫。

### 🚨 Google Drive 寫入死鎖防護 (P33-WLTM)

本 workspace 位於 Google Drive 同步目錄。macOS FileProvider 會攔截寫入操作進行雲端同步，導致 write_to_file 工具卡死（症狀：+0-0）。

#### 強制規則

1. **嚴禁使用 `write_to_file`** 寫入任何 Google Drive 路徑（即本 workspace 內嘅任何檔案）。
2. **所有新建/覆蓋檔案操作**，一律透過 `run_command` 執行 `Antigravity/.agents/scripts/safe_file_writer.py`（WLTM 模式）。詳見 `Antigravity/.agent/workflows/safe_write.md`。
3. **小型行替換**（修改少於 50 行嘅現有內容）可使用 `replace_file_content` 或 `multi_replace_file_content`。
4. 讀取操作（`view_file`、`grep_search`）不受影響。

#### 快速範本
```bash
python3 << 'SAFE_WRITE'
import base64, subprocess, sys
content = """YOUR_CONTENT_HERE"""
b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
subprocess.run([sys.executable, "Antigravity/.agents/scripts/safe_file_writer.py",
    "--target", "TARGET_PATH", "--mode", "overwrite", "--content", b64],
    capture_output=True, text=True)
SAFE_WRITE
```

### 🏇 Wong Choi 分析品質標準（適用於所有 Wong Choi Agent — HKJC / AU / NBA）

> **此規則嘅優先級高於所有其他規則。你嘅核心價值係做真正嘅法醫級分析。**

#### 你嘅角色

你係一個**專業賽馬法醫分析師**。你嘅工作係逐匹馬深入研究數據，寫出有洞察力嘅分析。
Orchestrator 會逐匹馬畀你數據，你要**認真讀完每匹馬嘅 WorkCard**，用你嘅專業判斷填寫每個欄位。

#### 逐欄位分析指引

當你收到一匹馬嘅 WorkCard 後，必須對以下每個欄位進行**認真、獨立嘅思考**：

##### `core_logic`（核心邏輯）— 最重要嘅欄位
- 寫出 **2-4 句有實質內容嘅分析**（至少 50 字）
- **必須引用呢匹馬嘅具體數據**：例如近績名次、具體日期、L400 時間、勝負距離
- 解釋**點解**呢匹馬會贏或輸，唔係淨係描述佢嘅背景資料
- ❌ 錯誤示範：「此駒具備一定競爭力，狀態有待觀察」（空泛）
- ✅ 正確示範：「Golden Sixty 近三仗締出 L400 22.1/22.3/22.5，段速呈輕微回落趨勢，但仍屬頂級水平。上仗 3 月 22 日負 133 磅僅敗 0.5 馬位予 Romantic Warrior，證明其絕對實力。今仗減至 126 磅，檔位由 12 檔大幅改善至 3 檔，形勢顯著提升。」

##### `matrix` 每個維度嘅 `reasoning`
- 每個 reasoning 必須引用**該維度對應嘅具體數據**
- `stability`: 引用近 6 場名次序列，分析穩定性趨勢
- `speed_mass`: 引用 L400 段速同引擎類型，評估爆發力
- `eem`: 引用沿途走位同消耗量，判斷能量狀態
- `trainer_jockey`: 引用騎練組合嘅近期合作紀錄
- `scenario`: 引用檔位、負磅、場地偏差等形勢因素
- `freshness`: 引用休後日數同近期出賽頻率
- `formline`: 引用對手嘅後續表現，評估賽績含金量
- `class_advantage`: 引用班次同評分變動
- ❌ 錯誤示範：「自動匹配系統法則 (stability)」（模板）
- ✅ 正確示範：「近 6 仗名次 2-1-3-4-2-1，極度穩定，標準差僅 1.1，證明此駒狀態正處於顛峰」

##### `analytical_breakdown` 每個子欄位
- 每個欄位必須有**針對呢匹馬嘅獨特分析**
- 引用 WorkCard 入面嘅具體數據支持你嘅判斷

##### `fine_tune`（微調）
- `direction`: 基於你嘅分析判斷應該 `+`（升級）、`-`（降級）或 `無`
- `trigger`: 解釋微調嘅具體原因（例如「檔位由 14 改善至 2，形勢大幅提升」）

#### 正確工作流程

1. **讀取** `.runtime/Horse_N_WorkCard.md` — 認真讀完所有數據
2. **思考** — 分析呢匹馬嘅優勢、劣勢、形勢
3. **撰寫** — 逐個欄位寫出有數據支撐嘅分析
4. **填寫** `Race_X_Logic.json` → `horses.N` 嘅對應欄位
5. **等待** Orchestrator 自動驗證 → 通過後進入下一匹

#### 如果工作量太大
- **停止當前工作**
- **通知用戶**：「剩餘 X 匹馬未分析，建議開新 Conversation 繼續」
- **記錄進度**到 `_session_tasks.md`
- **絕對唔好用腳本代替真正分析** — 寧可做少啲，但做得好

#### 絕對禁止
1. 建立任何 `auto_fill` / `auto_expert` / `auto_analyst` Python 腳本去批量填充
2. 用 `while True` loop 或 `hashlib` 模板池生成罐頭分析
3. 繞過 Orchestrator 嘅 per-horse watch loop
4. 自動注入 `_validation_nonce`（NONCE 只可由 skeleton 腳本生成）

---

## 2. 系統需求

| 項目 | 最低要求 |
|:---|:---|
| Python | 3.9 或以上 |
| Git | 最新版本 |
| 記憶體 | 4 GB+ |
| 磁碟空間 | 2 GB+ |
| 網絡 | 穩定連線（數據提取需要） |
| AI IDE | Cursor / Gemini CLI（任一） |

---

## 3. 安裝步驟

### 3.1 Clone Repository

```bash
# 如果使用 Google Drive 共享
# 直接透過 Google Drive Desktop 同步即可

# 如果使用 Git
git clone <REPO_URL>
cd Antigravity
```

### 3.2 安裝 Python 依賴

```bash
pip install -r requirements.txt
```

> **注意**：如果你使用虛擬環境 (venv)：
> ```bash
> python -m venv .agents/skills/hkjc_racing/hkjc_race_extractor/venv
> source .agents/skills/hkjc_racing/hkjc_race_extractor/venv/bin/activate  # macOS/Linux
> # 或
> .agents\skills\hkjc_racing\hkjc_race_extractor\venv\Scripts\activate     # Windows
> pip install -r requirements.txt
> ```

### 3.3 安裝 Playwright 瀏覽器

Playwright 需要下載 Chromium 瀏覽器引擎嚟做 HKJC 網頁數據提取：

```bash
python -m playwright install chromium
```

> ⚠️ **如果呢步失敗**，嘗試：
> ```bash
> python -m playwright install --with-deps chromium
> ```

### 3.4 更新 MCP 配置（如適用）

`.agents/mcp_config.json` 包含 SQLite 資料庫嘅絕對路徑。如果你嘅 home 目錄唔係 `/Users/imac`，需要更新：

```json
{
  "mcpServers": {
    "sqlite": {
      "args": ["-y", "mcp-server-sqlite", "/YOUR/HOME/.gemini/antigravity/databases/wong_choi.db"]
    }
  }
}
```

將 `/YOUR/HOME` 替換為你嘅實際 home 目錄路徑。

---

## 4. Windows 額外設定

> [!IMPORTANT]
> Windows 用戶**必須**執行以下設定，否則中文數據處理會出錯。

### 4.1 設定 PYTHONUTF8 環境變數（永久）

**方法 A — PowerShell（推薦）：**
```powershell
[System.Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
```

**方法 B — 系統設定：**
1. 搜索「環境變數」→ 編輯使用者環境變數
2. 新增：變數名 = `PYTHONUTF8`，值 = `1`
3. 重啟終端機

### 4.2 確認 Python 指令

Windows 通常使用 `python`（唔係 `python3`）：
```bash
python --version  # 確認顯示 Python 3.9+
```

### 4.3 Google Drive Desktop

如果使用 Google Drive 同步：
- 確保 Google Drive Desktop 已安裝並同步中
- 建議將 Google Drive 設定為「Mirror files」模式（非 Streaming）

---

## 5. 首次運行驗證

完成安裝後，執行以下指令驗證環境：

```bash
# 1. 驗證 safe_file_writer.py
python .agents/scripts/safe_file_writer.py --help

# 2. 驗證 Playwright
python -c "from playwright.sync_api import sync_playwright; print('✅ Playwright OK')"

# 3. 驗證 BeautifulSoup
python -c "from bs4 import BeautifulSoup; print('✅ BeautifulSoup OK')"

# 4. 驗證 encoding
python -c "import sys; print(f'stdout encoding: {sys.stdout.encoding}')"
# 應該顯示 utf-8

# 5. 驗證 NBA 依賴（如需）
python -c "from nba_api.stats.static import players; print(f'✅ NBA API OK — {len(players.get_players())} players')"
```

如果全部通過，你嘅環境就準備好喇！🎉

---

## 6. 使用指南

### 6.1 HKJC 賽馬分析

**觸發方式：** 喺 AI IDE 入面 tag `@hkjc-wong-choi`

**Pipeline 流程：**
1. 畀 AI 一個 HKJC 賽事 URL 或者日期
2. AI 自動讀取 `AGENTS.md` → `SKILL.md` → 執行 Orchestrator
3. Orchestrator 自動完成數據提取 → 模板注入 → 分析 → 報告

**手動執行 Orchestrator：**
```bash
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <URL或資料夾>
```

**輸出：**
- `Race X Facts.md` — 賽事數據
- `Race X Analysis.md` — 深度分析
- `Race_X_Logic.json` — 結構化評級
- `Final_Report.csv` — 匯總報告
- `Monte_Carlo_Results.json` — Monte Carlo 模擬

### 6.2 AU 賽馬分析

**觸發方式：** tag `@au-wong-choi`

**Pipeline 流程：**
1. 畀 AI 一個 Racenet 賽事連結或者馬場名 + 日期
2. AI 自動讀取 SKILL.md → 執行 AU Orchestrator
3. Claw Code 自動提取數據 → 分析 → 報告

**手動執行：**
```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py <URL或資料夾>
```

### 6.3 NBA 分析

**觸發方式：** tag `@nba-wong-choi`

**Pipeline 流程：**
1. 畀 AI 日期（例如 `分析今日 NBA`）
2. AI 自動讀取 SKILL.md → 執行 NBA Orchestrator
3. 自動爬 Sportsbet → nba_api 提取 → 生成分析報告

**手動執行：**
```bash
python .agents/skills/nba/nba_orchestrator.py --date YYYY-MM-DD
python .agents/skills/nba/nba_orchestrator.py --date YYYY-MM-DD --list    # 列出賽事
python .agents/skills/nba/nba_orchestrator.py --date YYYY-MM-DD --status  # 查看進度
```

**輸出：**
- `Game_XXX_Full_Analysis.md` — 每場分析
- `NBA_All_SGM_Report.txt` — SGM 組合
- `NBA_Banker_Report.txt` — 穩膽推薦

### 6.4 LoL 電競分析

**觸發方式：** tag 相應 Agent 或者直接指示 AI

**目前階段：** 基於 LLM 指令觸發，暫無專用 Orchestrator。
分析框架同其他引擎類似：數據收集 → 深度分析 → 輸出報告。

---

## 7. 架構概覽

```
.agents/
├── ARCHITECTURE.md          # 完整架構文檔
├── agents/                  # 22 個 AI Agent 定義
│   ├── hkjc-wong-choi.md   # HKJC 賽馬 Agent
│   ├── au-wong-choi.md     # AU 賽馬 Agent
│   ├── nba-wong-choi.md    # NBA Agent
│   └── ...                 # 其他 19 個通用 Agent
├── skills/                  # 46 個技能模組
│   ├── hkjc_racing/        # HKJC 賽馬技能
│   │   ├── hkjc_wong_choi/
│   │   ├── hkjc_race_extractor/
│   │   ├── hkjc_horse_analyst/
│   │   └── hkjc_reflector/
│   ├── au_racing/          # AU 賽馬技能
│   ├── nba/                # NBA 技能
│   └── ...
├── workflows/               # 16 個工作流程
├── rules/                   # 全域規則（GEMINI.md）
└── scripts/                 # 核心共用腳本
    ├── safe_file_writer.py  # 防鎖死寫檔工具
    ├── rating_engine_v2.py  # 評級引擎
    ├── run_monte_carlo.py   # Monte Carlo 模擬
    └── ...
```

### 核心腳本清單

| 腳本 | 功能 |
|:---|:---|
| `safe_file_writer.py` | Google Drive 防鎖死安全寫檔 |
| `rating_engine_v2.py` | 通用評級引擎 (HKJC + AU) |
| `run_monte_carlo.py` | Monte Carlo 動態模擬 |
| `completion_gate_v2.py` | 分析品質驗證 |
| `compile_final_report.py` | 最終報告編譯 |
| `inject_hkjc_fact_anchors.py` | HKJC 數據注入 |
| `preflight_environment_check.py` | 環境預檢 |

### 分析品質防線（Firewall）

Orchestrator 內建多層自動驗證防線，確保每匹馬嘅分析品質：

| 防線 | 功能 |
|:---|:---|
| WALL-008 | 防偽標籤 (NONCE) 必須存在 |
| WALL-009 | 評級矩陣至少 6/8 維度有效 |
| WALL-010 | 分數差異度 ≥ 2 種（防全同填充） |
| WALL-011 | core_logic 不含模板化語句 |
| WALL-012 | core_logic ≥ 50 字中文（防空泛） |
| WALL-013 | 矩陣 reasoning ≥ 4 個維度有實質分析 |
| WALL-014 | core_logic 必須提及馬名（防通用模板） |
| WALL-017 | 偵測已知 bypass 腳本特徵碼 |
| WALL-019 | NONCE 前綴驗證（只接受 `SKEL_` 開頭） |

> ⚠️ **重要**：嚴禁建立任何 auto_fill / auto_expert 腳本去繞過以上防線。
> 詳見 `.antigravityrules` 嘅「Wong Choi 分析品質標準」。

---

## 8. 常見問題 FAQ

### Q: Windows 上中文亂碼點算？
**A:** 確保已設定 `PYTHONUTF8=1` 環境變數（見 [Section 4.1](#41-設定-pythonutf8-環境變數永久)）。

### Q: `python3` 指令 Windows 搵唔到？
**A:** Windows 正常用 `python`。所有 Orchestrator 腳本已內建自動偵測：
```python
PYTHON = "python3" if shutil.which("python3") else "python"
```

### Q: Playwright 安裝失敗？
**A:** 
```bash
pip install playwright
python -m playwright install --with-deps chromium
```
如果企業防火牆阻擋，嘗試設定 proxy：
```bash
set HTTPS_PROXY=http://your-proxy:port
python -m playwright install chromium
```

### Q: Google Drive 同步鎖死？
**A:** 所有寫檔操作已透過 `safe_file_writer.py` 處理。如果仍然卡死：
1. 暫停 Google Drive 同步
2. 完成操作後恢復同步

### Q: 數據提取失敗？
**A:** 常見原因：
1. 網絡問題 → 確認可以訪問 racing.hkjc.com
2. Playwright 未安裝 → `python -m playwright install chromium`
3. 賽事未開始 → HKJC 通常喺賽前 2 天先有完整數據

### Q: `venv` 點設定？
**A:** HKJC pipeline 可選用 venv：
```bash
cd .agents/skills/hkjc_racing/hkjc_race_extractor
python -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r ../../../../requirements.txt
python -m playwright install chromium
```

---

## 9. 故障排解

### 數據提取失敗
```bash
# 測試 HKJC 連線
python -c "import requests; r = requests.get('https://racing.hkjc.com'); print(f'Status: {r.status_code}')"

# 測試 Playwright
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://racing.hkjc.com')
    print(f'Title: {page.title()}')
    browser.close()
"
```

### Orchestrator 崩潰
```bash
# 重新執行（會從上次中斷位置繼續）
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <目錄> --auto
```

### LLM 分析品質下降
1. 確認 `AGENTS.md` → `SKILL.md` → `GEMINI.md` 嘅規則鏈完整
2. 確認 Orchestrator 狀態檔未損壞
3. 嘗試重新開始新 session

---

> 💡 **提示：** 如有任何問題，請聯絡 repository 管理員。
