> **V5 架構修正:**
> Python = 數據供應商（輸出 `Data_Brief.json`，純數據 + 建議池）
> LLM = 分析師 + 決策者（獨立分析 → 自主揀 Combo → 原生寫核心邏輯）
> Python = 品控（`verify_nba_math.py` 只驗數學）
>
> **Must-Respond Protocol（強制）:**
> 1. LLM 必須讀取 `python_suggestions.top_legs_by_edge` 前 5 名
> 2. 對每個建議必須明確回應：✅ 同意 / ⚡ 修改（改用其他 Line）/ ❌ 拒絕
> 3. 拒絕時必須提供基於籃球邏輯嘅原因（「CoV 偏高」唔得，要講具體場景）
> 4. LLM 必須提出至少 1 個 Python 未標記嘅潛在機會或風險
>
> **🚨 API 數據信任原則（P36a — 強制）:**
> 1. Python 透過 `nba_api` 抓取嘅球員數據（隊伍歸屬、L10 數組、場均數據）係 **Ground Truth**
> 2. **LLM 嘅知識庫關於球員歸屬隊伍可能過時或錯誤**（例如交易、簽約）
> 3. **嚴禁以「呢個球員唔係呢隊」為理由拒絕 Python 建議** — API 數據永遠優先
> 4. 若 LLM 認為球員歸屬有疑問，應標註 `⚠️ 球員歸屬待確認` 但**唔可以直接 Reject**
> 5. 只有以下理由先可以拒絕 Python 建議：傷病、禁賽、戰術角色改變、場景分析（Blowout 風險等）
>
> **Anti-Rubber-Stamp Rules:**
> 1. 每個 Combo 嘅核心邏輯必須包含 LLM 嘅**獨立推理**
> 2. 禁止 copy-paste Python 嘅 `eight_factor` breakdown 作為「核心邏輯」
> 3. 核心邏輯必須包含：球員角色定位、對位分析、比賽劇本推演
> 4. 允許引用 Python 數據（L10、Edge），但需用自己嘅語言解讀
>
> **Leg 分析強制欄位（每個 Leg 必須包含）:**
> 每個 Leg 嘅數理引擎欄位必須包含以下所有數據：
> 1. **賠率** (@X.XX)
> 2. **隱含勝率** (1/賠率 × 100%)
> 3. **預期勝率 / Adjusted Prob** (8-Factor 調整後嘅預期勝率，來自 Data Brief)
> 4. **Edge** (預期勝率 - 隱含勝率)
> 5. **L10 命中** (X/10 = XX%)
> 6. **L10 逐場數組** (嚴禁省略)
> 7. **CoV** (穩定度評級)
> 8. **8-Factor 調整明細** (trend / cov_adj / buffer / matchup / context / pace / usg / defender)
>
> **Game-by-Game 強制執行:**
> 1. 每次只處理一場賽事嘅 `Data_Brief_{TAG}.json`
> 2. 完成一場 → 驗證通過 → 先進入下一場
> 3. 嚴禁一次過處理多場賽事（避免 context window 爆炸同質量梯度）

## Pre-Flight Environment Scan(強制 — Step 1 之前執行)


**Step E1 — Output Token Capacity Test:**
嘗試生成 ~500 字測試輸出。成功且未截斷 → `ENV_TOKEN_CAPACITY: HIGH`。
截斷或錯誤 → `ENV_TOKEN_CAPACITY: LOW`。

**Step E2 — Resource Load Verification:**
讀取 4 個必讀文件,確認每個都成功載入:
1. `../nba_wong_choi/SKILL.md`
2. `resources/01_data_validation.md`
3. `resources/02_quality_scan.md`
4. `resources/03_output_format.md`

**Step E3 — Report to User:**
```
🔍 環境掃描結果:
- Token Capacity: [HIGH / LOW]
- Resources Loaded: [4/4 / X/4]
- Games Per Batch: [3 / 2]
✅ 環境就緒,開始分析。
```

**Step E4 — MCP Server Availability Check (P32 新增):**
檢查以下 MCP Servers 是否已安裝並可用:
1. **Playwright MCP** — `@playwright/mcp@latest` (**Bet365 即時盤口提取 — 最高優先級**)
2. **SQLite MCP** — `mcp-server-sqlite` (歷史數據庫查詢)
3. **Memory MCP** — `@modelcontextprotocol/server-memory` (Knowledge Graph 記憶)

檢查方法:嘗試呼叫 `list_tables`(SQLite)或 `read_graph`(Memory)。若失敗:
```
⚠️ MCP 狀態:
- Playwright: [✅ 已連接 / ❌ 未安裝]
- SQLite: [✅ 已連接 / ❌ 未安裝]
- Memory: [✅ 已連接 / ❌ 未安裝]

若未安裝,請將以下配置加入 mcp_config.json:
{
  "mcpServers": {
    "playwright": { "command": "npx", "args": ["-y", "@playwright/mcp@latest"] },
    "sqlite": { "command": "npx", "args": ["-y", "mcp-server-sqlite", "~/.gemini/antigravity/databases/wong_choi.db"] },
    "memory": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"] }
  }
}
然後重新啟動 Antigravity。
```
Step 5.5 數據庫歸檔功能需要 MCP Servers 運作,但即使未安裝也不影響 Step 1-5 核心分析流程。
**Playwright MCP 未安裝時**: Bet365 提取無法執行 → **必須安裝 Playwright MCP 先可以運行 NBA 分析**。嚴禁使用估算盤口。

# Scope & Operating Instructions

## Step 1: 接收用戶輸入 + 賽事確認
收到用戶指令後:
1. **確認分析日期**:解析日期意圖(「今晚」= 今日、「聽日」= 明日)。
   - **預設澳洲時間 (AEST/AEDT)**。每次分析前確認美國對應日期。
   - 所有輸出檔名、路徑同內容日期統一使用澳洲日期。
2. **確認賽事範圍**:搜尋該日 NBA 賽事,或只分析用戶指定場次。
3. **建立工作資料夾**:`{YYYY-MM-DD} NBA Analysis/`
   路徑會自動偵測平台:
   - macOS: `./{YYYY-MM-DD} NBA Analysis/`
   - Windows: `g:\我的雲端硬碟\Antigravity Shared\Antigravity\{YYYY-MM-DD} NBA Analysis/`
4. **記錄關鍵變量**:`TARGET_DIR`、`ANALYSIS_DATE`、`GAMES_LIST`

**Session Recovery 檢查**:檢查 `TARGET_DIR` 內已存在嘅檔案:
- `Game_*_Full_Analysis.txt` → 該場已完成提取+分析,跳過
- `NBA_Data_Package.txt`(存在)但無對應 `Game_*_Full_Analysis.txt` → 數據已提取但未分析,直接從 Sub-Step 3A 開始
- `NBA_Analysis_Report.txt` → 全部已完成
- 通知用戶已完成/半完成嘅場次,詢問是否繼續。

**Issue Log 初始化**:建立 `{TARGET_DIR}/_session_issues.md`,內容如下:
```
# Session Issue Log
**Date:** {ANALYSIS_DATE} | **Sport:** NBA
**Status:** IN_PROGRESS
---
```

**⏸ 賽事確認 Checkpoint(強制停頓):**
確認賽事清單後,向用戶匯報:
```
✅ 已確認 {ANALYSIS_DATE} 共 {N} 場 NBA 賽事:
[列出所有賽事]
是否開始數據提取同分析?(若你想用另一個 session 進行分析,可以喺此停止。)
```
**嚴禁跳過此 checkpoint。** 用戶可能使用不同嘅 AI 引擎分別處理提取同分析。

> ⚠️ **失敗處理**:若無法確認賽事日期或賽程,立即詢問用戶澄清。

### 🤖 Orchestrator 協調增強(引用 AG Kit orchestrator 模式)

**Agent 邊界執行:**
| Agent | CAN Do | CANNOT Do |
|-------|--------|-----------|
| NBA Data Extractor | 數據爬取、Box Score 提取 | ❌ 分析判斷、組合推薦 |
| NBA Analyst | 策略分析、Parlay 組合 | ❌ 數據提取 |

**衝突解決:** 若 Extractor 數據同 Analyst 判斷出現矛盾,以原始數據為準,通知用戶分歧內容。

## Step 2-3: 逐場賽事循環 (Per-Game Pipeline Loop)

> [!CAUTION]
> 🔒 **單場沙盒鎖 (Single-Game Sandbox Lock)**
> 嚴禁合併賽事分析。必須做到「一場賽事 = 一次獨立 Extractor 提取 = 一次獨立 Analyst 呼叫 = 一個獨立輸出檔案」。
> 即使你收到用戶匯總版的 `NBA_Data_Package_Auto.md`,該檔案通常只包含盤口與傷缺。**你必須強制呼叫 `nba_data_extractor` 補齊每場賽事的球員 14 項 L10 數據卡**,否則嚴禁進入 Analyst 分析階段 (數據包防騙協議)。
> 嚴禁一次過將所有賽事嘅數據 dump 畀 Analyst。逐場獨立執行「提取 → 驗證 → 分析 → 自檢 → 存檔」。

**進度控制**:
- 每場賽事完成後,執行 Sub-Step 3D 賽事間自檢,通知用戶結果。
- **每完成 3 場**後,額外強制停頓問用戶:「已完成 Game 1-3,是否繼續分析 Game 4-6?」
- ≤3 場 → 逐場自檢後直接完成,進入 Step 4。

**Context Window 提醒**:若 context window 接近上限,主動建議用戶開啟新 session。Session Recovery 會偵測已完成場次。

**📖 Smart Slice Protocol(Per-Game Data Loading):**
分析每場賽事時,**只傳遞當場嘅數據卡給 Analyst**:
```
分析 Game N 前:
  1. 只提取本場 Meeting Intelligence + Player-Level 數據卡
  2. 唔好包含上一場/下一場嘅數據
  3. 每場完成後,該場數據應從 context 中自然淡出

⛔ 嚴禁:一次過將所有賽事嘅數據 dump 畢 Analyst
✅ 逐場獨立執行「提取 → 驗證 → 分析 → 自檢 → 存檔」
```

**🔒 COMPLETION_GATE(分析完成門與驗證攔截閘):**
每場賽事完成(Agent 返回結果)後,存檔前必須強制執行以下 Python 驗證:
🚨 **你必須強制自己 run `python3 .agents/scripts/completion_gate_v2.py <你的檔案> --domain nba` 進行檢驗。不過關不准推進到下一場！**
如果檢驗失敗 (出現 `❌ [FAILED]`)，你已違規 → 立即根據報告內容自行修正，並重新執行 validator 直到 `✅ [PASSED]` 為止！只有通過測試才可以推進到下一場。

### Sub-Step 2A-Pre: 歷史交叉驗證（本場 — P35 新增）

> **設計理念:** 受 ECC `search-first` 啟發。每場賽事提取前，先查詢歷史對位數據。
> 完整 checklist 見 `shared_instincts/intelligence_checklist.md`。
> **此步驟依賴 MCP。若 MCP 不可用 → 自動跳過。**

**若 MCP Servers 可用，對本場球員執行 Tier 2 歷史驗證：**
1. `read_query`: 球員 vs 對手歷史 Props 命中率
2. `read_graph`: 球員傷病 Timeline + 復出 usage 變化
3. `read_query`: B2B 歷史達標率（若為 B2B 場次）
4. `search_nodes`: 防守大閘效應

**將結果加入本場數據包頭部：**
```markdown
## 歷史對位 Pattern（Tier 2 — MCP）
- {PLAYER_1} vs {OPPONENT}: [Props 命中率 X%]
- {PLAYER_2} B2B: [達標率 X%]
- 防守大閘: [{DEFENDER} 限制 -X% usage]
- **Intelligence Confidence: [🟢/🟡/🔴]**
```
MCP 不可用 → 跳過，標記 `Intelligence Confidence: 🟡 MEDIUM`。

### Sub-Step 2A: 呼叫 NBA Data Extractor（本場）
指示 Extractor 只提取當前一場賽事嘅數據,等待輸出結構化數據包。

**🎯 Bet365 盤口整合（Sub-Step 2A 強制附加 — Claw V8 Zero-Navigation ONLY）：**
> Extractor 會執行 `claw_bet365_odds.py`（Claw V8）透過 Comet CDP **純讀取** Player Props。
> **V8 架構：USER 手動 click tab → CDP 純讀取 DOM → 零 navigation。**
>
> **執行指令** (必須使用絕對路徑):
> ```bash
> python3 "./.agents/skills/nba/nba_data_extractor/scripts/claw_bet365_odds.py" \
>   --output "{TARGET_DIR}/bet365_all_raw_data.json"
> ```
>
> **🚨 Zero-Navigation 規則（Opus 實測驗證）：**
> - ❌ **嚴禁** `page.goto()` / `el.click()` / `page.mouse.click()` / `location.href`
> - ✅ **只准** `page.evaluate(() => document.body.innerText)` 純讀取
> - ✅ 由 USER 手動 click 4 個 Tab（`Points` / `Rebounds` / `Assists` / `Threes Made`）
>
> **🎯 Tab 選擇（P40 — Milestones Source-First）：**
> - ✅ `Points` = Milestones (10+, 15+, 20+) — 呢個先係正確嘅！
> - ❌ `Points O/U` = 主盤口 (12.5, 15.5) — **嚴禁使用**
>
> 若提取成功，JSON 會被保存至 `{TARGET_DIR}/bet365_all_raw_data.json`。
> **若提取失敗** → 報告 `odds_not_found` → 通知用戶協助解決，**不得繼續分析**。
> 嚴禁使用估算盤口或 Extractor Only Mode 作為 fallback。

### Sub-Step 2B: 數據品質驗證(本場)
按照 `resources/01_data_validation.md` 執行所有驗證。將本場數據追加至 `TARGET_DIR/NBA_Data_Package.txt`。

### Sub-Step 2C: Python 數據包生成 (V5 — Data Brief)

> [!IMPORTANT]
> **V5 架構核心改變**: Python 只負責「數據供應」，唔負責「分析決策」。
> 輸出格式從 `Skeleton.md`（含 [FILL] 佔位符）改為 `Data_Brief_{TAG}.json`（純數據 + 建議池）。

執行 `generate_nba_auto.py` 生成所有場次嘅數據包：
```bash
python3 generate_nba_auto.py
```
此命令會：
1. 抓取 nba_api 真實 L10 gamelog + 球隊進階數據
2. 計算所有球員 × 所有 Bet365 盤口嘅完整 8-Factor Adjusted Win Prob
3. 為每場賽事生成獨立嘅 `Data_Brief_{TAG}.json`

**Data Brief JSON 包含：**
- `players` — 所有球員 × 所有盤口嘅完整數學計算（L10 數組、CoV、命中率、8-Factor breakdown）
- `python_suggestions` — Python 基於數學排序嘅 Combo 建議（Must-Respond，見 P36）
- `team_stats` — 球隊進階數據（PACE、OFF/DEF RTG）
- `game_lines` — Bet365 讓分/總分/獨贏
- `injuries` / `b2b` — 傷病同 Back-to-Back 資訊

**Data Brief 唔包含：**
- ❌ 核心邏輯敘事（由 LLM 原生撰寫）
- ❌ Combo 選擇決定（由 LLM 自主判斷）
- ❌ `[FILL]` 佔位符（V5 已完全廢除）
- ❌ Markdown 格式報告（LLM 自行輸出）

### Sub-Step 3A: LLM Analyst 獨立分析（本場 — 逐場執行）

> [!CAUTION]
> **Game-by-Game 強制執行**: 每次只處理一場賽事嘅 Data Brief JSON。
> 嚴禁一次過處理多場賽事。完成一場 → 驗證通過 → 先進入下一場。

**LLM Analyst 工作流程（每場賽事）：**
1. 讀取 `{TARGET_DIR}/Data_Brief_{GAME_TAG}.json`
2. 執行 **Must-Respond Protocol（P36）**：回應 `python_suggestions.top_legs_by_edge` 前 5 名
3. 獨立審視所有球員盤口數據，運用籃球知識分析
4. **自主構建 3+1 個 SGM 組合**（唔受 Python 建議綁定）
5. 為每個 Leg 撰寫**原生核心邏輯**（唔可照抄 Python 嘅 eight_factor breakdown）
6. 輸出完整 `Game_{GAME_TAG}_Full_Analysis.md`

**Analyst 必須完成嘅分析（每場）：**
- 賽事背景分析（讓分/總分/節奏/B2B 推演）
- 傷病影響評估
- 每位有盤口球員嘅角色定位同盤口價值判斷
- SGM 組合（≥2 組：穩膽/價值/進取）+ 條件觸發 Value Bomb
- 每個 Leg 嘅獨立核心邏輯 + 風險評估 + 注碼建議
- 同 Python 建議嘅分歧標註（如有）

**Analyst 可引用嘅 Python 數據：**
- ✅ L10 數組、均值、SD、CoV（事實性數據）
- ✅ 8-Factor adjustment breakdown（作為參考輸入）
- ✅ Edge 計算結果（數學事實）
- ❌ 但唔可以直接複製 Python 嘅數學描述作為「核心邏輯」

### Sub-Step 3B: 合併輸出與歸一化
按照 `resources/03_output_format.md` 合併數據包與分析結果,存檔至 `TARGET_DIR`。

### Sub-Step 3C: 品質掃描(本場)
按照 `resources/02_quality_scan.md` **Section A + B** 執行逐場結構驗證 + 語義掃描。
(Section C + D 嘅全日品質檢查留到 Step 4 執行。)

**🔴 品質掃描連續 FAILED 2 次 — AG Kit Systematic Debugging 啟動:**
讀取 `.agent/skills/systematic-debugging/SKILL.md` → 4-Phase 除錯(Reproduce → Isolate → Understand → Fix)→ 根因記錄到 `_session_issues.md`

### Sub-Step 3D: 賽事間自檢報告(本場完成後)
讀取 `_session_issues.md` 中本場問題,按 `resources/02_quality_scan.md` 嘅 issue codes 匯報:
- **CRITICAL** → 顯示簡述 + 問用戶修正或跳過(**最多重試 1 次**)
- **MINOR** → 一行匯報 → 全部完成後統一處理
- **無問題** → 通知完成

通知後自動推進下一場。**每完成 3 場**後強制停頓等用戶確認。

### 循環完成後
1. 從所有 `Game_*_Full_Analysis.txt` 讀取候選 Legs,匯總為**全日候選池**
2. 執行 **[NBA-DA01] Parlay 多角度審計協議**:
   **Step A — Statistical Selection:** 列出最穩嘅 2-3 隻 Legs (低 CoV + 高 L10 命中率)
   **Step B — Injury & Matchup Challenge:** 對位球員、傷缺、B2B?
   **Step C — Props Line Audit:** 剔除 outlier 後仲 pass 嗎？更低 CoV 嘅替代 Line?
   **Step D — Final Parlay:** 指示 Analyst 構建跨場次 SGM 組合（≥2 組：🛡️ 1 + 🔥 2，可選 💎 3）+ 並列出被踢走嘅 Legs 同原因
3. 執行 SGP 防撞擊檢查

> ⚠️ **失敗處理**:若某場失敗,記錄錯誤並跳過,繼續下一場。

## Step 4: 品質檢查 + 合規審計
按照 `resources/02_quality_scan.md` Section C + D 執行最終品質檢查。

### Step 4a: 呼叫 NBA Compliance Agent（強制）
將最終報告傳遞給 `nba_compliance` Agent 執行合規審計：
- `✅ COMPLIANCE CHECK PASSED` → 繼續 Step 4b
- `⚠️ CONDITIONAL PASS` → 指示 Analyst 修正 MINOR 問題後重新提交
- `❌ FAILED` → 指示 Analyst 重做受影響組合/Leg，最多重試 1 次

### Step 4b: 呼叫 NBA Batch QA（多場時強制）
若本次 session 包含 ≥2 場賽事，將全部輸出傳遞給 `nba_batch_qa` Agent 執行跨場品質掃描。
單場分析時可跳過此步驟。

按照 `resources/03_output_format.md` 存檔最終報告。

## Step 4.5: 自檢總結 (Self-Improvement Review)
讀取 `_session_issues.md` 全部內容，向用戶呈現累積問題：
- A) 逐一處理
- B) 記錄到 `_improvement_log.md`
- C) 略過，生成最終匯報

**🧠 改善方案探索（AG Kit Brainstorming — 自動觸發）：**
若 `_session_issues.md` 中有任何 CRITICAL 或 ≥2 個 MINOR 問題：
1. 讀取 `.agent/skills/brainstorming/SKILL.md`
2. 對累積問題自動生成 ≥2 個結構化改善方案
3. 等用戶選擇後才執行修改

## Step 5: 最終匯報
按照 `resources/03_output_format.md` Section 5 向用戶匯報。
將 `_session_issues.md` Status 更新為 `COMPLETED`。

## Step 5.5: SQLite 數據庫歸檔 (Database Archival)

完成最終匯報後，你必須立刻使用原生 Python 腳本將分析結果持久化：

**5.5a. 賽前預測寫入庫 (Prediction Logging):**
呼叫 logger 腳本自動解析你剛才產出的 Markdown 報告：
`python3 .agents/skills/nba/nba_data_extractor/scripts/nba_db_logger.py --parse "{TARGET_DIR}/{REPORT_NAME}.txt"`
這會自動提取並保存被評為穩膽或價值的 Leg 入 `predictions` 表。

## Step 5b: Session Cost Report（可選 — P35 新增）

> **設計理念:** 受 ECC `cost-aware-llm-pipeline` 啟發。追蹤每次分析 session 嘅 token 消耗同成本估算。

最終匯報後，執行 session 成本追蹤：
```bash
python3 .agents/scripts/session_cost_tracker.py "{TARGET_DIR}" --domain nba
```
喺聊天中簡要匯報成本摘要（3 行以內）。此步驟失敗唔影響任何結果。

## Step 6: 🚨 Day 2 覆盤階段 (Embedded Backtester)

當用戶下達指令如:「執行昨日覆盤」或「跑回測 2026-04-03」:
1. 啟動回測腳本:`python3 .agents/skills/nba/nba_data_extractor/scripts/nba_backtester.py --date {YYYY-MM-DD}`
2. 腳本會自動查詢 SQLite 中未驗證的 prediction,透過 `nba_api` 即時抓取真實成績,寫入 `actual_results` 表,並輸出終端機文字簡報。
3. 根據大腦吸收的成績簡報,向用戶匯報:
   - 「尋日推薦共 X 注,命中 Y 注。」
   - 分析哪種類型的 Prop 最穩,哪種失敗,作為自我修正的反思。

### Step 6b: Instinct Evolution（P35 新增）
回測完成後,執行 instinct 評估：
```bash
python3 .agents/scripts/instinct_evaluator.py "{TARGET_DIR}" \
  --registry ".agents/skills/shared_instincts/instinct_registry.md" \
  --domain nba \
  --backtest-report "{TARGET_DIR}/{BACKTEST_REPORT}"
```
將評估結果加入回測匯報嘅新 section。此步驟失敗唔影響回測結果。

# 🚨 防串流鎖死協議 (P33-WLTM — Safe-Writer Protocol — 2026-04-05 強化)

# 🚨 終極防死機 / Safe-Writer Protocol (P33-WLTM)

> 遵循 GEMINI.md 之中規定的 `safe_file_writer.py` 進行操作。嚴禁使用 write_to_file。

# 🛑 Pipeline Testing & Agent Execution Boundaries
**CRITICAL PROTOCOL: How to Avoid Automation Shortcuts in the Future**

1. **停止測試捷徑 (No Automated Shortcuts for LLM Analysis):** 
   身為 LLM 分析引擎，你嘅職責就是根據 `nba_extractor.py` 或 `extract_formguide_data.py` 等腳本抽出嚟嘅客觀數據同數學 Skeleton，做「深度法醫分析」。在日後執行任何 Pipeline 測試或端到端執行時，**絕對不能用 Python script 去模擬生成內容、塞字過關或做機械式 `[FILL]` 替換 (例如使用 `fill_skeleton.py` 字串替換)**。必須老老實實當自己做緊真飛分析一樣，用 Markdown 直接把高質素、具深度的優質香港口吻內容完整寫出嚟覆蓋所有 `[FILL]`。
2. **遵守系統角色 (Respect System Roles):** 
   分工極為明確。Python 腳本負責「砌骨架」同做「算術題」（例如抽數、排版、計算 Matrix 分數），而你 (LLM) 作為 Analyst 負責「入血肉」（撰寫戰術節點、球權分析、風險評估）。**任何企圖繞過血肉生成嘅舉動都係嚴重違反 Protocol 嘅行為。** 如果再發現殘留 `[FILL]` 或是以腳本灌水，整個分析將被 Completion Gate 強制退回！


## ⛔ 零容忍政策：禁止使用「Extractor Only Mode」
1. **Mandatory Player Props:** 任何情況下，Wong Choi 管線**絕對禁止**以「無 Bet365 Player Props」的形式強行輸出報告 (所謂的 "Extractor Only Mode")。
2. **Quality Control:** 缺乏 Player Props (得分、助攻、籃板等 L10 數據與盤口) 會破壞「God Mode」的深度 EV 計算與 CoV 神經刀判定，導致分析質量不達標。
3. **Fallback Protocol:** 若 Bet365 Playwright 提取失敗，**必須暫停並強硬要求 USER 手動提供 DOM `innerText`** (`bet365_raw_MATCH.txt`) 以轉換為 JSON，嚴禁自行留空組合。

# 🚨 BET365 EXTRACTION PIPELINE (P40 — 2026-04-09 — Priority 0)

> **Phase 1: URL Discovery (Network Interception)**
> - Bet365 嘅 Index Page (遊戲列表) 被 Cloudflare Silent Degradation 保護
> - 正確做法：`page.reload()` → 攔截 `pushnotificationdialogcontentapi` response
> - Script: `claw_discover_v5.py`
>
> **Phase 2: Data Extraction (ZERO-NAVIGATION ARCHITECTURE) 👑**  
> - **核心規則**：Cloudflare Fingerprinting 會攔截任何由 CDP 觸發的網頁跳轉！
> - **Game Lines**：NBA Index 頁面預設已顯示所有比賽數據，純 `page.evaluate` 讀取即可。
> - **Player Props**：**強制要求 USER 人手點擊** ("Points O/U", "Assists" 等 Tabs) 後，腳本進行 `evaluate` 讀取。
> - Script: `claw_bet365_odds.py` (V7 Interactive Extractor)
>
> **❌ 永久禁用嘅方案 (Cloudflare 會即刻降級)：**
> - ❌ `page.goto(game_url)` 
> - ❌ `window.location.href = url` 
> - ❌ `window.location.hash = url` 
> - ❌ `page.mouse.click()` 或 `el.click()` 去觸發 SPA Navigation
