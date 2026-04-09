# Engine Adaptation

# 🤖 ENGINE ADAPTATION(P31 — 2026-03-31 新增 — Priority 0)

> **歷史教訓:** 2026-03 月下旬起主要使用 Gemini 3.1 Pro 跑分析,發現 Batch 1 完成後 LLM 停機等用戶、Verdict 被遺漏。根本原因:Gemini 唔會好似 Opus 咁自動連鎖多個 tool calls。
>
> **適配規定(Priority 0 — 適用所有引擎):**
>
> 1. **LOOP_CONTINUATION_MARKER(每個 batch 寫完後強制輸出):**
>    喺每個 batch 嘅 tool call 完成後,你必須喺你嘅內部思考中明確寫:
>    `CONTINUE_LOOP: Batch [N] done, [M] batches + VERDICT remaining. Proceeding to Batch [N+1].`
>    若 M = 0(所有馬匹 batch 完成),寫:
>    `CONTINUE_LOOP: All horse batches done. VERDICT BATCH remaining. Proceeding to write VERDICT.`
>    **呢個標記嘅目的**係提醒你自己仲有嘢做,唔好停機。
>
> 2. **PREMATURE_STOP_GUARD(回覆用戶前攔截器):**
>    若你準備向用戶輸出文字回覆(非 tool call),必須先問自己:
>    「Analysis.md 入面有冇 🏆 Top 4 位置精選?」
>    → 若冇 → ⛔ 你仲未寫完!返回 batch 循環繼續!
>    → 若有 → 繼續正常流程
>
> 3. **Tool Call Chaining 指引:**
>    - 每完成一個 batch 嘅寫入 + QA → 立刻進入下一個 batch
>    - 唔好等用戶回覆、唔好輸出中間報告
>    - 唯一允許停機嘅情況:(a) 全場完成含 Verdict、(b) 錯誤需要用戶介入
>
> 4. **GEMINI ANTI-LAZINESS REINFORCEMENT(防止 Gemini 跳過邏輯):**
>    Gemini 引擎傾向喺 token 壓力下壓縮或跳過分析步驟。以下措施強制對抗:
>    - **Emoji 計數自檢:** 每匹馬寫完後,喺內部思考中數 emoji 標題:⏱️🐴🔬⚡📋🔗🧭⚠️📊💡⭐ = 11 個。少於 11 個 = 你壓縮咗 → 立即補全。
>    - **字數門檻硬執行:** 每匹馬完成後估算字數。S/A ≥500 | B ≥350 | C/D ≥300。若明顯不足 → 你偷懶咗 → 擴展分析。
>    - **禁止「因為評級低所以簡寫」:** D 級馬同 S 級馬用同一個骨架模板。D 級需要用數據解釋「點解差」,唔係寫一句「近績差唔推薦」就算。
>    - **骨架 [FILL] 零容忍:** 若寫完嘅分析仍然包含 `[FILL]` 文字 → 你跳過咗填充 → 立即補回。
>    - **🐴 馬匹剖析 5 項必填:** 班次負重 + 引擎距離 + 步態場地 + 配備意圖 + 人馬組合。缺任何一項 = 骨架未完全填充。
>    - **🐴 馬匹剖析格式嚴規 (P35 — 2026-04-06 新增 — Priority 0):**
>      - 馬匹剖析**僅為簡潔分類標籤**，每項以 `[標籤]` 格式撰寫，禁止寫成段落或散文。
>      - ✅ 正確示範: `- **步態場地:** [未有 Soft 地數據，但血統顯示應能應付]`
>      - ✅ 正確示範: `- **引擎距離:** [Type A 短途爆發]`
>      - ✅ 正確示範: `- **人馬組合:** [Rachel King 騎法硬朗，適合此駒]`
>      - ❌ 錯誤示範: `- **步態場地:** [無]` （禁止用「無」一字帶過）
>      - ❌ 錯誤示範: 在馬匹剖析下寫整段 200+ 字分析文章（這些內容屬於 💡結論 > 核心邏輯）
>      - **深度法醫分析（戰術推演、歷史比較、風險評估、綜合判定）必須全部歸入 `💡 結論 > 核心邏輯` 區域。**
>      - **自檢觸發器:** 若你嘅馬匹剖析任何一項超過 30 字 → 你已違規 → 將多餘內容搬去核心邏輯。

# 🚨 OUTPUT_TOKEN_SAFETY(P28 — 2026-03-29 新增 — Priority 0)

> **歷史教訓:** 2026-03-29 HKJC Heison 140/140 匹馬 FAILED。根本原因:**output token limit exceeded**。
>
> **適應性規定(Priority 0):**
>
> 1. **DEFAULT BATCH_SIZE = 3**(標準)。環境掃描通過後可以使用 3。
> 2. **環境掃描失敗 → BATCH_SIZE = 2**(安全 fallback)。
> 3. **VERDICT BATCH 必須為獨立 tool call**。
> 4. **Token 壓力自測**:若壓縮內容 → 立即停止拆到下一個 batch。
> 5. **若任何 batch 被截斷 → 自動降級為 BATCH_SIZE=2 並重做。**



## Pre-Flight Environment Scan(強制 — Step 1 之前執行)

**Step E1 — Output Token Capacity Test:**
嘗試生成 ~500 字測試輸出。成功且未截斷 → `ENV_TOKEN_CAPACITY: HIGH`。
截斷或錯誤 → `ENV_TOKEN_CAPACITY: LOW`。

**Step E2 — Resource Load Verification:**
讀取 4 個必讀文件,確認每個都成功載入:
1. `../au_wong_choi/SKILL.md`(確認 P28 存在)
2. `au_horse_analyst/01_system_context.md` (位於 resources 目錄下)
3. `au_horse_analyst/06_templates_core.md` (位於 resources 目錄下，結構骨架)
4. `au_horse_analyst/06_templates_rules.md` (位於 resources 目錄下，Verdict 觸發規則)
4. 場地模組(按場地選 1 個)

**Step E3 — BATCH_SIZE Decision:**
```
IF ENV_TOKEN_CAPACITY == HIGH:
  BATCH_SIZE = 3  ← 標準
 ELSE:
  BATCH_SIZE = 2  ← 安全 fallback
```

**Step E4 — Report to User:**
```
🔍 環境掃描結果:
- Token Capacity: [HIGH / LOW]
- Resources Loaded: [4/4 / X/4]
- BATCH_SIZE: [3 / 2]
- Verdict: [獨立 tool call]
✅ 環境就緒,開始分析。
```

若 Resources 未完全載入 → 停低通知用戶。

**Step E5 — MCP Server Availability Check (P32 新增):**
檢查以下 MCP Servers 是否已安裝並可用:
1. **Playwright MCP** — `@playwright/mcp@latest` (網頁即時數據抓取後備)
2. **SQLite MCP** — `mcp-server-sqlite` (歷史數據庫查詢)
3. **Memory MCP** — `@modelcontextprotocol/server-memory` (Knowledge Graph 記憶)

檢查方法:嘗試呼叫 `list_tables`(SQLite)或 `read_graph`(Memory)。若失敗:
```
⚠️ MCP 狀態:
- Playwright: [✅ 已連接 / ❌ 未安裝]
- SQLite: [✅ 已連接 / ❌ 未安裝]
- Memory: [✅ 已連接 / ❌ 未安裝]

若未安裝,請將以下配置加入 mcp_config.json:

**macOS 配置:**
```json
{
  "mcpServers": {
    "playwright": { "command": "npx", "args": ["-y", "@playwright/mcp@latest"] },
    "sqlite": { "command": "npx", "args": ["-y", "mcp-server-sqlite", "~/.gemini/antigravity/databases/wong_choi.db"] },
    "memory": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"] }
  }
}
```

**Windows 配置:**
```json
{
  "mcpServers": {
    "playwright": { "command": "cmd.exe", "args": ["/c", "npx", "-y", "@playwright/mcp@latest"] },
    "sqlite": { "command": "cmd.exe", "args": ["/c", "npx", "-y", "mcp-server-sqlite", "%USERPROFILE%\\.gemini\\antigravity\\databases\\wong_choi.db"] },
    "memory": { "command": "cmd.exe", "args": ["/c", "npx", "-y", "@modelcontextprotocol/server-memory"] }
  }
}
```
⚠️ 請根據你的操作系統選擇對應配置。DB 路徑需按實際安裝位置調整。
然後重新啟動 Antigravity。
```
Step 8 數據庫歸檔功能需要 MCP Servers 運作,但即使未安裝也不影響 Step 1-7 核心分析流程。

**Step E6 — MCP Memory Integration (P35 — Racing Memory Graph):**
若 Memory MCP 已連接，在分析前必須執行查詢以提取該賽事/馬匹/馬房的跨季與跨場記憶。
指令: `read_graph({ entities: ["馬名/練馬師名/馬場偏差"] })`
若發現重要記憶（例如「此馬曾在沙田爛地爆冷」或「此檔位容易有死亡偏差」），將強制納入分析上下文。

# 🛡️ B17 Racing Ralph Loop (80+ 信心分數系統)
> **自審機制 (Ralph Loop):** 
> 每次完成馬匹分析，提交前必須自評 `Confidence Score` (1-100)。
> 評分標準：
> - 數據是否完整無缺 (PI, L400, EEM)？
> - 邏輯鏈是否自洽（例如步速預測與最終結果是否吻合）？
> - 若 Score < 80，你必須 **自動拒絕提交** 並進入修正迴圈 (Correction Loop)，補充遺漏邏輯或數據，直至 Score ≥ 80 才能進入下一隻馬或生成 Verdict。

# 🔀 狀態機與執行日誌 (P24 & P26 雙重把關)
> **STATE MACHINE CHECKPOINTS (P24):** 
> Wong Choi 必須將每一個 Step 視為一個獨立嘅 State。喺執行每一個 Step 之前，必須確認【Entry Condition】；喺進入下一個 Step 之前，必須確認【Exit Condition】。嚴禁喺未有真實檔案產出嘅情況下，自行「發夢」推進下一個 Step。
> 
> **EXECUTION JOURNAL (P26):**
> 每完成一個主要 Step (例如：環境掃描、資料擷取完成、某個 Batch 分析完成)，你必須強制 append 一行 Log 到目標資料夾的 `_execution_log.md` 中。
> - 工具：使用 `safe_file_writer.py --mode append` 寫入。
> - 格式：`> 📝 LOG: Step [Name] | Tool: [Tool] | Status: [Success/Fail] | Notes: [Brief]`
> - 目的：即使中斷，用戶亦可睇 Log 追查進度。嚴禁覆蓋舊 Log。


> 🚫 **BROWSER POLICY(P32 — MCP Integration 更新):** `MCP Playwright (mcp_playwright_browser_*)` 同 `read_browser_page` 仍然**嚴禁使用**。但系統已掛載 **Playwright MCP Server**,提供輕量 `playwright_navigate`、`playwright_screenshot`、`playwright_click`、`playwright_fill` 等工具。允許喺以下場景使用 Playwright MCP:
> - (a) Python 腳本提取失敗嘅 fallback(例如 JS-rendered 頁面)
> - (b) 即時 Scratchings / 馬匹更替確認
> - (c) Live Odds 走勢抓取
> - **使用原則:優先用 Python scripts + `read_url_content`,Playwright MCP 係後備方案。**


# 🐍 Python 自動化卸載指引 (Python-First Offloading)
> **編譯最終報表 (compile_final_report.py):**
> 喺全日賽事分析完結之後，你**嚴禁**自己手寫 Markdown 或 CSV 表格（避免 Context 爆滿導致排版錯誤）。你必須呼叫 `run_command python3 .agents/scripts/compile_final_report.py --target_dir [目標資料夾]`，腳本會自動將所有 `Analysis.md` 內嘅 CSV 區塊結合成一個 `Final_Report.csv` 檔案俾用戶。
>
> **狀態機守護神 (session_state_manager.py):**
> 為了防範中斷，每完成一場賽事，請呼叫 `run_command python3 .agents/scripts/session_state_manager.py --target_dir [目標資料夾] --action update --key "completed" --value "Race 1, Race 2"` 來備份進度。重新啟動時用 `--action read` 讀取，避免重新掃描目錄。

