# NBA Wong Choi Pipeline & Execution Protocol

本文件定義 NBA Wong Choi 分析管線的標準執行流程。

> [!IMPORTANT]
> **V3 Orchestrator 自動化提示**：以下 Step 2-5 嘅大部分步驟已由 `nba_orchestrator.py` 自動串連執行。
> 手動介入只需要喺 **Phase 2**（LLM 填寫 `[FILL]` 欄位）同少數例外情況。
> 本文件保留完整流程作為 Reference，但實際操作時以 Orchestrator 輸出為準。

## Pre-Flight Environment Scan (強制 — Step 1 之前執行)

**Step E1 — Output Token Capacity Test:**
嘗試生成預測，以確保環境正常。

**Step E2 — Resource Verification:**
確保你已讀取所有要求的 resources 檔案。

**Step E3 — MCP Server Availability Check:**
檢查以下 MCP Servers 是否已安裝並可用:
1. `SQLite MCP` (歷史數據庫查詢)
2. `Memory MCP` (Knowledge Graph 記憶)
Playwright MCP 已非必需 — Sportsbet 盤口由 Python 腳本自動提取。

---

## Step 1: 接收用戶輸入 + 賽事確認

收到用戶指令後:
1. **確認分析日期**: 解析日期意圖(「今晚」= 今日、「聽日」= 明日)。預設為澳洲 AEST/AEDT 時間。
2. **確認賽事範圍**: 搜尋該日 NBA 賽事,或只分析用戶指定場次。
3. **建立工作資料夾**: `{YYYY-MM-DD} NBA Analysis/`
4. **Session Recovery 檢查**: 檢查 `TARGET_DIR` 內是否存在已分析的 `Game_*_Full_Analysis.txt` 或 `NBA_Data_Package.txt`，並向提出是否繼續。
5. **Issue Log 初始化**: 建立 `{TARGET_DIR}/_session_issues.md` 追蹤問題。

**⏸ 賽事確認 Checkpoint(強制停頓):**
向用戶匯報已確認賽事數量，並詢問：「是否開始數據提取同分析？」

---

## Step 2-3: 逐場賽事循環 (Single-Game Sandbox Lock)

> [!CAUTION]
> 嚴禁合併賽事分析。必須做到「一場賽事 = 一次獨立提取 = 一次獨立呼叫 Analyst = 一個輸出檔案」。

### Sub-Step 2A-Pre: 歷史交叉驗證（Tier 2 — MCP）
若 MCP 可用，呼叫 SQLite 及 Memory 進行歷史球員對位及傷病復出查詢。

### Sub-Step 2A: 資料提取 (Data Extraction)
- **呼叫 `@nba data extractor` (NBA Data Extractor)** 負責提取當日盤口。
- 執行 Sportsbet 提取腳本:
  `python .agents/skills/nba/nba_data_extractor/scripts/claw_sportsbet_odds.py`

### Sub-Step 2B: 數據品質驗證
按照 `01_data_validation.md` 對 `sportsbet_latest.json` 進行驗證，追加至 `NBA_Data_Package.txt`。

### Sub-Step 2C: Python 數據包生成 (Data Brief)
> ⚠️ 由 Orchestrator 自動調用 `generate_nba_reports.py` 生成含 10-Factor 調整的 Full Analysis skeleton。

### Sub-Step 3A: LLM Analyst 獨立分析 (逐場)
- **呼叫 `@nba analyst` (NBA Analyst)** 進行獨立賽事分析。
- 專員需讀取當場 `Data_Brief_{GAME_TAG}.json`。
- 必須回應 Python 提供之前 5 名高 Edge 建議 (✅ / ⚡ / ❌)。
- 輸出 `Game_{GAME_TAG}_Full_Analysis.md`。

### Sub-Step 3B/C/D: 賽事間自檢與存檔
- 若品質掃描失敗 2 次，自動啟用 Systematic Debugging。
- **Completion Gate**: `python .agents/scripts/completion_gate_v2.py <你的檔案> --domain nba`。任何 `❌ [FAILED]` 必須即時重寫。
> ⚠️ 由 Orchestrator 呼叫 `validate_nba_output.py` 自動執行防火牆驗證。
- 向用戶匯報當場進度。每完成 3 場賽事必須停頓並向用戶確認。

### 循環完成後: 全日審計
全部單場完成後，執行 Parlay 多角度審計，準備跨場組合。

---

## Step 4: 品質檢查 + 合規審計

- **Step 4a**: **呼叫 `@nba compliance` (NBA Compliance)** Agent 執行合規檢查。
- **Step 4b**: **呼叫 `@nba batch qa` (NBA Batch QA)** 執行所有場次的質量及字數驗證。

---

## Step 5: 最終匯報與數據歸檔

1. **跨場組合匯出 (由 Orchestrator 自動執行)**:
   V3 Orchestrator 會自動調用 `generate_nba_sgm_reports.py`。手動執行可用：
   `python .agents/skills/nba/nba_wong_choi/scripts/generate_nba_sgm_reports.py --dir "{TARGET_DIR}"`
   此腳本會自動將所有 `Full_Analysis.md` 內嘅 Combo 區塊匯總成為：
   - 📄 `NBA_All_SGM_Report.txt`
   - 📄 `NBA_Banker_Report.txt`
2. **向用戶發送最終匯總提示與報告連結**。
   執行 `python .agents/skills/nba/nba_data_extractor/scripts/nba_db_logger.py --parse "{TARGET_DIR}/{REPORT_NAME}.txt"`
3. **Step 5b (Cost Tracker)**:
   執行 `python .agents/scripts/session_cost_tracker.py "{TARGET_DIR}" --domain nba`

---

## Step 6: Day 2 覆盤與回測階段 (Embedded Backtester)

當遇到回測或對答案需求:
1. 啟動腳本: `python .agents/skills/nba/nba_data_extractor/scripts/nba_backtester.py --date {YYYY-MM-DD}`
2. 匯報命中率及反思。
3. 執行 Instinct 評估 (P35): `python .agents/scripts/instinct_evaluator.py "{TARGET_DIR}" --domain nba`
