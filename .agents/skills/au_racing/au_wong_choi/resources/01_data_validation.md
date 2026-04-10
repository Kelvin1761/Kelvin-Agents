# 環境與數據驗證協議 (Data & Environment Validation)

為了確保在分析過程中不會因為系統或資源問題而中斷，AU Wong Choi 在正式啟動 Pipeline 前，必須執行本文件內的掃描。

## Pre-Flight Environment Scan (強制 — Step 1 之前執行)

喺開始任何分析之前，你必須執行以下環境掃描，確保當前環境能夠支持完整分析：

### Step E1 — Output Token Capacity Test
嘗試生成一個包含大約 ~500 字嘅測試輸出（例如在思考過程中重複測試字串）。
- 若成功完成且未被截斷 → 記錄 `ENV_TOKEN_CAPACITY: HIGH`。
- 若被截斷或出現「exceeded maximum output」錯誤 → 記錄 `ENV_TOKEN_CAPACITY: LOW`。

### Step E2 — Resource Load Verification
讀取以下 4 個必讀文件，確認每個都成功載入：
1. `au_wong_choi/SKILL.md`
2. `au_horse_analyst/resources/01_system_context.md`
3. `au_horse_analyst/resources/06_templates_core.md` (結構骨架)
4. 當日場地對應之 track file（例如 `04b_track_caulfield.md` 等）
*注意：若任何資源無法載入，請即時停下通知用戶。不要在未配備所有裝備前上陣。*

### Step E3 — BATCH_SIZE Decision
根據 E1 的測試結果：
```
IF ENV_TOKEN_CAPACITY == HIGH:
  BATCH_SIZE = 3  ← 標準模式
ELSE:
  BATCH_SIZE = 2  ← 安全模式
```

### Step E4 — MCP Server Availability Check
檢查以下 MCP Servers 是否已安裝並可用:
1. **Playwright MCP** — `@playwright/mcp@latest` (網頁即時數據抓取後備)
2. **SQLite MCP** — `mcp-server-sqlite` (歷史數據庫查詢)
3. **Memory MCP** — `@modelcontextprotocol/server-memory` (Knowledge Graph 記憶)

檢查方法:嘗試呼叫 `list_tables`(SQLite) 或 `read_graph`(Memory)。若失敗，提供修改 `mcp_config.json` 的指引，並告訴用戶雖然 Step 8 (數據庫寫入) 無法使用，但 Step 1-7 分析仍可繼續。

### Step E5 — Report to User
掃描後向用戶呈現簡潔狀態報告：
```
🔍 環境掃描結果:
- Token Capacity: [HIGH / LOW]
- Resources Loaded: [4/4 / X/4]
- BATCH_SIZE: [3 / 2]
- Verdict: [獨立 tool call]
✅ 環境就緒,開始分析。
```
