# 🚀 Antigravity Agent Setup Guide

> 本指南覆蓋所有 Agent Pipeline（HKJC 賽馬、AU 賽馬、NBA 籃球、LoL 電競）。
> 跟住步驟做，確保你嘅環境同主機完全一致。

---

## 📋 目錄

1. [系統需求](#1-系統需求)
2. [安裝步驟](#2-安裝步驟)
3. [Windows 額外設定](#3-windows-額外設定)
4. [首次運行驗證](#4-首次運行驗證)
5. [使用指南](#5-使用指南)
6. [架構概覽](#6-架構概覽)
7. [常見問題 FAQ](#7-常見問題-faq)
8. [故障排解](#8-故障排解)

---

## 1. 系統需求

| 項目 | 最低要求 |
|:---|:---|
| Python | 3.9 或以上 |
| Git | 最新版本 |
| 記憶體 | 4 GB+ |
| 磁碟空間 | 2 GB+ |
| 網絡 | 穩定連線（數據提取需要） |
| AI IDE | Cursor / Gemini CLI（任一） |

---

## 2. 安裝步驟

### 2.1 Clone Repository

```bash
# 如果使用 Google Drive 共享
# 直接透過 Google Drive Desktop 同步即可

# 如果使用 Git
git clone <REPO_URL>
cd Antigravity
```

### 2.2 安裝 Python 依賴

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

### 2.3 安裝 Playwright 瀏覽器

Playwright 需要下載 Chromium 瀏覽器引擎嚟做 HKJC 網頁數據提取：

```bash
python -m playwright install chromium
```

> ⚠️ **如果呢步失敗**，嘗試：
> ```bash
> python -m playwright install --with-deps chromium
> ```

### 2.4 更新 MCP 配置（如適用）

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

## 3. Windows 額外設定

> [!IMPORTANT]
> Windows 用戶**必須**執行以下設定，否則中文數據處理會出錯。

### 3.1 設定 PYTHONUTF8 環境變數（永久）

**方法 A — PowerShell（推薦）：**
```powershell
[System.Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
```

**方法 B — 系統設定：**
1. 搜索「環境變數」→ 編輯使用者環境變數
2. 新增：變數名 = `PYTHONUTF8`，值 = `1`
3. 重啟終端機

### 3.2 確認 Python 指令

Windows 通常使用 `python`（唔係 `python3`）：
```bash
python --version  # 確認顯示 Python 3.9+
```

### 3.3 Google Drive Desktop

如果使用 Google Drive 同步：
- 確保 Google Drive Desktop 已安裝並同步中
- 建議將 Google Drive 設定為「Mirror files」模式（非 Streaming）

---

## 4. 首次運行驗證

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

## 5. 使用指南

### 5.1 HKJC 賽馬分析

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

### 5.2 AU 賽馬分析

**觸發方式：** tag `@au-wong-choi`

**Pipeline 流程：**
1. 畀 AI 一個 Racenet 賽事連結或者馬場名 + 日期
2. AI 自動讀取 SKILL.md → 執行 AU Orchestrator
3. Claw Code 自動提取數據 → 分析 → 報告

**手動執行：**
```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py <URL或資料夾>
```

### 5.3 NBA 分析

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

### 5.4 LoL 電競分析

**觸發方式：** tag 相應 Agent 或者直接指示 AI

**目前階段：** 基於 LLM 指令觸發，暫無專用 Orchestrator。
分析框架同其他引擎類似：數據收集 → 深度分析 → 輸出報告。

---

## 6. 架構概覽

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

## 7. 常見問題 FAQ

### Q: Windows 上中文亂碼點算？
**A:** 確保已設定 `PYTHONUTF8=1` 環境變數（見 [Section 3.1](#31-設定-pythonutf8-環境變數永久)）。

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

## 8. 故障排解

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
