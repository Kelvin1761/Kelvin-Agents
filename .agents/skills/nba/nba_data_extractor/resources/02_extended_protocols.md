### Part B: Player-Level 數據卡
每位候選球員嘅完整 14 項數據卡(格式見 `resources/02_data_card_template.md`)。

# Output Contract
你嘅輸出將由 NBA Analyst 直接消費。數據包必須:
1. 包含所有 Meeting-Level 同 Player-Level 數據
2. 每位球員嘅數據卡必須完整填寫所有 14 項
3. 所有數據必須標明來源網站
4. 缺失數據標記為 `N/A (數據不足)`

# Recommended Tools & Assets
- **Tools**:
  - `run_command`：核心工具，用於執行 `claw_sportsbet_odds.py`（Sportsbet 盤口提取）及 `nba_extractor.py`（球員數據提取），亦用於數據包寫檔（透過 safe_file_writer 管道）
  - `search_web`：後備工具，僅用於補充個別球員缺失數據（禁止用於全套提取）
  - ⚠️ `write_to_file`：**P33-WLTM 完全禁止**
  - ⚠️ `mcp_playwright_browser_*`：**禁止用於 Sportsbet**（會被反爬蟲攞截）
- **Assets**:
  - `resources/01_data_protocols.md`:搜尋規則與防錯機制
  - `resources/02_data_card_template.md`:14 項數據卡格式
  - `resources/03_defensive_profiles.md`:防守大閘分類清單

# Test Case
**User Input:**
「幫我提取今晚 Lakers vs Celtics 嘅數據」

**Expected Agent Action:**
1. 讀取 `resources/01_data_protocols.md`、`02_data_card_template.md`、`03_defensive_profiles.md`。
2. 確認今日日期與賽程。
3. 搜尋 Lakers vs Celtics 先發陣容 + 傷病報告。
4. 根據防守大閘清單掃描雙方防守者狀態。
5. 提取賽事情境(讓分盤、總分盤、B2B、節奏)。
6. 逐位球員提取 14 項數據卡。
7. 輸出完整結構化數據包。
