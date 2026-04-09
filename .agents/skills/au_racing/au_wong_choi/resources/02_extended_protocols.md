## Step 1: 資料提取 (Data Extraction)
收到 Racenet URL 後,你必須呼叫 `AU Race Extractor` 技能。
指示它依照該技能的規則執行,並取得目標資料夾**絕對路徑**。

AU Race Extractor 建立嘅資料夾格式為 `[YYYY-MM-DD] [Venue Name] Race [Start]-[End]`。
路徑會自動偵測平台:
- macOS: `./2026-03-04 Caulfield Heath Race 1-8/`
- Windows: `g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-03-04 Caulfield Heath Race 1-8/`

你必須記錄以下關鍵變量供後續步驟使用:
- `TARGET_DIR` — 資料夾絕對路徑
- `VENUE` — 馬場名稱
- `DATE` — 賽事日期
- `TOTAL_RACES` — 總場次數

**CRITICAL**: 你從此刻起必須強制將接下來的所有輸出(分析結果與報表),**全數儲存於 `TARGET_DIR` 內**,統一歸檔。

**CRITICAL**: 即使用戶只要求分析某一場,你仍必須在此步驟一次性提取**全日所有場次**的 Racecard 與 Formguide,確保所有數據就位後,才可進行任何分析工作。絕不可邊提取邊分析。

**Session Recovery 檢查**:初始化時,你必須檢查 `TARGET_DIR/Race Analysis/` 內是否已存在 `* Analysis.md` 檔案(亦檢查 `* Analysis.txt` 向後兼容)。若存在,代表之前嘅 session 已完成部分場次。你應:
1. 列出已完成嘅場次(例如 Race 1-5 已有 Analysis.md)
2. 讀取 `_session_state.md`(如存在)恢復品質基線同進度狀態
3. **🚨 強制重讀 Output Templates(P26 — Session Recovery Resource Reload):**
   - 無論係恢復邊一場,**必須**重讀 `au_horse_analyst/resources/06_templates_core.md`
   - 此步驟防止 LLM 喺新 session 中因記憶漂移而違反格式規範(歷史教訓:HKJC 2026-03-27 Session Recovery 時跳過 template 讀取,導致格式違規)
   - 若正在恢復某場賽事嘅中途批次,亦需重讀 `06_templates_core.md` 確認最後一批嘅 Part 3/4 結構
4. 通知用戶:「偵測到已完成 Race X-Y 嘅分析,是否從 Race Z 繼續?」
5. 若用戶確認,直接跳到未完成嘅場次,避免重複分析。
6. 自動計算剩餘場次,通知用戶:「剩餘 X 場未分析。」

> ⚠️ **失敗處理**:見底部「統一失敗處理協議」。觸發條件:AU Race Extractor 執行失敗或輸出不完整。

**Issue Log 初始化**:TARGET_DIR 確立後,建立 `{TARGET_DIR}/_session_issues.md`,內容如下:
```
# Session Issue Log
**Date:** {DATE} | **Venue:** {VENUE}
**Status:** IN_PROGRESS
---
```
此檔案將用於記錄整個分析 session 中發現嘅所有問題。

**⏸ 提取完成 Checkpoint（驗證後自動推進）：**
提取完成後，你必須執行以下驗證，**通過後自動推進到 Step 1.5**：
1. **檔案命名檢查：** 確認日期前綴正確
2. **內容抽查：** 隨機 `view_file` 一個排位表前 5 行，確認有實際數據
3. **簡短匯報：** 在聊天中列出已提取檔案(1-2 行)，然後自動推進到 Step 1.5
**唔好問用戶「是否繼續」。** 用戶叫你分析某個場地 = 意圖係全套流程到底。

**📂 Extractor 輸出結構(v2 — Per-Race Split):**
Extractor 會為每場賽事生成獨立檔案:
```
TARGET_DIR/
├── {MM-DD} Formguide_Index.md   ← 索引檔(先讀此檔!)
├── {MM-DD} Race 1 Formguide.md  ← 每場約 50-100KB
├── {MM-DD} Race 1 Racecard.md
├── {MM-DD} Race 2 Formguide.md
├── {MM-DD} Race 2 Racecard.md
├── ...
├── Meeting_Summary.md
└── _Race_Day_Briefing.md
```

## Step 1.5: Race Day Briefing(賽日總覽 — P30)

> **設計理念:** 提取完成後、天氣預測前,提供全日賽事「鳥瞰圖」。令用戶同 AI 都清楚今日工作量、Session 分割計劃、同潛在風險,避免盲目開始分析。

**A. 解析排位表(Smart Slice Protocol):**
1. **先讀 Index 檔案**:`view_file` 讀取 `{TARGET_DIR}/{MM-DD} Formguide_Index.md`(~2KB)
2. Index 包含每場嘅 Distance、Class、Runners 同 Horse Quick Reference
3. **唔好一次讀晒所有 Formguide** — 只用 Index 做 Briefing

從 Index + 每場嘅 Racecard `.md` 中提取**每場**嘅:
- 距離 (Distance)
- 距離類別 — SPRINT (≤1300m) / MIDDLE (1400-1600m) / STAYING (≥1800m)
- 班級 (Class) — 例如 BM58/BM72/Group 1/Listed/Maiden/HCP
- 賽道表面 (Surface) — Turf / Synthetic
- 出賽馬匹數 (Field Size)(已扣除退出 Scratchings)

**B. 生成 Race Day Briefing(格式必須完全遵守):**
```
📋 Race Day Briefing
Date: {DATE} | Venue: {VENUE} | Total Races: {TOTAL_RACES}
BATCH_SIZE: {BATCH_SIZE}(由環境掃描決定)

| Race | Distance | Category | Class  | Surface | Field | Est. Batches | Session |
|------|----------|----------|--------|---------|-------|-------------|---------|
| R1   | 1100m    | SPRINT   | BM58   | Turf    | 12    | 4+V         | S1      |
| R2   | 1400m    | MIDDLE   | Maiden | Turf    | 14    | 5+V         | S1      |
| R3   | 2000m    | STAYING  | BM72   | Turf    | 8     | 3+V         | S1      |
| R4   | 1200m    | SPRINT   | Listed | Turf    | 10    | 4+V         | S1      |
| R5   | 1600m    | MIDDLE   | G3     | Turf    | 9     | 3+V         | S2      |
| ...  | ...      | ...      | ...    | ...     | ...   | ...         | ...     |

📊 Resource Estimate:
- Total Runners:{TOTAL_HORSES}
- Total Batches(incl. Verdict):{TOTAL_BATCHES}
- Est. Session Splits:{NUM_SESSIONS} sessions
  → S1: Race 1-4 | S2: Race 5-8 | S3: Race 9+
- Est. Time Per Race:~20-30 min

⚠️ Risk Flags:
- 🔴 Large Fields(≥12 runners):[list races, e.g. R1(12), R2(14)]
- 🔵 Staying Races(≥2000m):[list races]
- 🟣 Synthetic Surface:[list races if any]
- 🟠 Weather/Track:[pending Step 2]

```

**C. 計算邏輯:**
- `Est. Batches` = ceil(Field / BATCH_SIZE) + 1 (Verdict batch),顯示為 `N+V`
- `Session Splits` = 每 4 場為 1 個 session(S1: R1-4, S2: R5-8, S3: R9+)
- `Large Field Flag` = Field ≥ 12 嘅場次
- `Staying Flag` = 距離 ≥ 2000m 嘅場次
- `Synthetic Flag` = Surface = Synthetic 嘅場次(Pakenham / Geelong)

**D. 寫入持久化檔案:**
將以上 Briefing 寫入 `{TARGET_DIR}/_Race_Day_Briefing.md`。後續 Session Recovery 時可直接讀取此檔案,無需重新解析排位表。

**E. 自動推進到 Step 2。** 唔好問用戶確認分析範圍。Default = 全日分析由 Race 1 開始。若用戶想指定場次,佢哋會自己講。

> [!TIP]
> **Session Recovery 時嘅行為:** 若 `_Race_Day_Briefing.md` 已存在,直接讀取並顯示(標記已完成場次),無需重新解析。

## Step 2: 預測場地與情報搜集 (Track Condition & Intelligence)

**⛈️ 自動天氣與場地降格預測 (P22 Python-First Offloading):**
在進行任何情報搜集前，你必須先強制執行以下腳本來獲取「預測場地掛牌」：
```bash
python .agents/skills/au_racing/au_racecourse_weather_prediction/scripts/track_predictor.py --course "{VENUE}" --date "{DATE}"
```
此腳本會自動調用本地 `wong_choi_racing.db` 的去水系數，結合 OpenWeatherMap 的降雨/蒸散量(ET) 預測，回傳一段 JSON（內含 `Predicted Rating` 等）。
你**必須絕對信任**此腳本的 `Predicted Rating`，這就是該日的預估場地掛牌！

使用 `search_web` 工具,一次性搜索以下當日賽事公共數據:
- 今日官方場地狀態 / 跑道偏差 (Track Bias)
- 今日欄位 (Rail Position)
- 傷患與退出報告 (Scratchings)
- 配備變動報告 (Gear Changes)

將所有搜索結果連同 Python 計算出嘅預測掛牌，整理為**固定情報包 (Intelligence Package)**，格式如下:
```
📋 Meeting Intelligence Package
- 預測掛牌 (Predicted Going): [填入 Python 腳本輸出的 Predicted Rating]
- 官方掛牌 (Official Going): [X]
- 跑道偏差 (Track Bias): [X]
- 欄位 (Rail Position): [X]
- 天氣預測 (Weather): [填入 Python 腳本輸出的 Rainfall, Temp, Wind]
- 退出馬匹 (Scratchings): [X]
- 配備變動 (Gear Changes): [X]
```

此情報包將傳遞給所有後續的 Analyst 調用,**避免每場重複搜索**。Analyst 僅需按需搜索馬匹專屬的騎練組合數據。

**寫入情報包到文件(Pattern 13 — 跨 Session 持久化):**
將以上情報包寫入 `{TARGET_DIR}/_Meeting_Intelligence_Package.md`,格式如下:
```markdown
# Meeting Intelligence Package
**Date:** {DATE} | **Venue:** {VENUE}
**Generated:** {timestamp}

## 預測掛牌 (Predicted Going)
[PREDICTED_TRACK_CONDITION]

## 官方掛牌 (Official Going)
{data}

## 跑道偏差 (Track Bias)
{data}

## 欄位 (Rail Position)
{data}

## 天氣 (Weather)
{data}

## 天氣穩定性 (Weather Stability)
[STABLE / UNSTABLE]

## 退出馬匹 (Scratchings)
{data}

## 配備變動 (Gear Changes)
{data}
```
此文件可供後續 session 直接讀取,無需重新搜索。若任何數據搜索失敗 3 次,標記為 `[搜索失敗 — 需人手補充]`。

## Step 3.5: 歷史交叉驗證 (Intelligence-First Tier 2 — P35 新增)

> **設計理念:** 受 ECC `search-first` 啟發。在即時情報搜集後，加入歷史數據交叉驗證，提升情報包可靠度。
> 完整 checklist 見 `shared_instincts/intelligence_checklist.md`。
> **此步驟依賴 MCP。若 MCP 不可用 → 自動跳過，唔影響分析。**

**若 MCP Servers 可用（Step E5 檢查通過），執行以下 Tier 2 驗證：**

1. **場地偏差歷史：** `read_graph` 查詢 `{VENUE}_*_bias` entities，獲取同場地過往 3 次 track bias 觀察
2. **命中率歷史：** `read_query` 查詢 `SELECT * FROM au_ratings WHERE venue='{VENUE}' ORDER BY date DESC LIMIT 30`
3. **天氣 Pattern：** `search_nodes` 查詢 `weather_accuracy_*`，比對同類天氣條件下嘅掛牌偏差
4. **SIP 記錄：** `read_graph` 查詢 `FP_pattern_*` / `FN_pattern_*`，檢索過往同場地嘅 SIP 修正

**將結果加入 `_Meeting_Intelligence_Package.md` 嘅新 section：**
```markdown
## 歷史場地 Pattern（Tier 2 — MCP 交叉驗證）
- 過往 3 次場地偏差: [內欄優勢 × 2 / 中立 × 1]
- 過往 3 次命中率: [🏆 X% / ✅ Y% / ⚠️ Z%]
- 天氣轉換 Pattern: [預測偏軟 → 實際偏硬 × N/M 次]
- 活躍 SIP: [SIP-RR17 (濕地膨脹), SIP-RF01 (寬恕校準)]
- **Intelligence Confidence: [🟢 HIGH / 🟡 MEDIUM / 🔴 LOW]**
```

**MCP 不可用時：**
- 跳過 Tier 2，加入 `⚠️ Tier 2 歷史驗證已跳過（MCP 不可用）`
- Intelligence Confidence 設為 🟡 MEDIUM
- **分析流程完全唔受影響**


## 問題嚴重程度定義 (Issue Severity)

| 級別 | 定義 | 處理方式 |
|------|------|----------|
| **CRITICAL** | 影響分析正確性嘅重大問題（邏輯錯誤、數據錯配） | 累積到賽間報告,建議修正 |
| **MINOR** | 品質瑕疵但不影響核心結論（格式微偏、字數略低） | 記錄到 issue log,全場後處理 |
| **DISCOVERY** | 框架未涵蓋嘅新模式或異常 | 記錄供覆盤參考 |

## Step 4: 戰略分析 (Strategy Analysis)

### 🤖 Orchestrator 協調增強(引用 AG Kit orchestrator 模式)

**A. Agent 邊界執行 (Agent Boundary Enforcement):**
Wong Choi 調度嘅子 Agent 必須嚴格遵守各自嘅職責邊界:

| Agent | CAN Do | CANNOT Do |
|-------|--------|-----------|
| AU Race Extractor | 數據爬取、格式化 | ❌ 任何分析判斷 |
| AU Horse Analyst | 馬匹分析、評級 | ❌ 數據提取、Excel 生成 |
| AU Batch QA | 結構驗證、字數檢查 | ❌ 修改分析內容 |
| AU Compliance | 全場合規審查 | ❌ 修改分析內容 |

若偵測到 Agent 越界行為 → 立即停止並回退到正確嘅 Agent。

**B. 子 Agent 輸出衝突解決 (Conflict Resolution):**
若 Batch QA 同 Compliance 嘅判斷出現矛盾(例如 QA PASSED 但 Compliance FAILED):
1. 記錄兩邊嘅具體分歧
2. 以 Compliance(更嚴格)嘅判斷為準
3. 通知用戶:「QA 同合規判斷出現分歧:[具體內容],以合規結果為準。」

**C. 進度追蹤格式 (Status Board):**
每場賽事嘅 Batch 進度匯報統一為:

| Agent | Status | Current Task | Progress |
|-------|--------|-------------|----------|
| Extractor | ✅/🔄/⏳ | [任務描述] | X/Y |
| Analyst | ✅/🔄/⏳ | [任務描述] | X/Y |
| Batch QA | ✅/🔄/⏳ | [任務描述] | X/Y |

---

**逐場分析協議**:
- 每次只分析 **1 場賽事**

> **[Per-Batch Skeletal JIT Injection] (強制防呆機制 — 學自 HKJC P33)**
> 在每次執行獨立 tool call 寫入 Batch 的分析前,你**必須強制**使用 `view_file` 讀取 `../au_wong_choi/resources/horse_analysis_skeleton.md`。
> 將骨架 × BATCH_SIZE 注入到 Analyst prompt 中。LLM 嘅任務從「生成分析」變為「填充骨架」,保證 100% 結構完整性。
> **核心邏輯/結論部分為 LLM 自由發揮區域。**
> 嚴禁憑記憶默寫結構。你必須將該骨架原封不動地複製並向下填充,確保所有 13 個欄位一個不漏!

。
- **批次自動推進但獨立寫入:** 分析期間嚴禁向用戶詢問「是否繼續下一批」。但「自動推進」≠「合併寫入」——每個 Batch 必須為獨立嘅 tool call。

**📖 Smart Slice Protocol(Per-Race Data Loading — 2026-04 新增):**
分析每場賽事時,**只讀當場嘅 Formguide 同 Racecard**,唔好讀其他場次嘅數據:
```
分析 Race N 前:
  1. view_file → {MM-DD} Race N Racecard.md(確認出馬數同馬匹名)
  2. view_file → {MM-DD} Race N Formguide.md(只讀本場,~50-100KB)
  3. 計算 BATCH_PLAN
  4. é–‹å§‹ Batch Loop

⛔ 嚴禁:一次過讀取多場嘅 Formguide
⛔ 嚴禁:讀取上一場/下一場嘅 Formguide(除非做跨場對手分析)
✅ 每場分析完成後,該場 Formguide 數據應從 context 中自然淡出
```
此協議確保每個 batch 嘅 context window 只包含必要數據,防止後段場次質素衰退。

> [!CAUTION]
> **🚨🚨🚨 BATCH EXECUTION LOOP — 強制批次執行循環(P23 — 2026-03-27 新增):**
>
> **歷史教訓(反覆發生 5+ 次):** 「全自動推進所有批次」被 LLM 理解為「一次過寫晒所有馬匹」。即使有 BATCH_ISOLATION_HARD、MANDATORY_BATCHING 等事後檢查規則,LLM 仍然將 8-14 匹馬合併到同一個 tool call。根本原因:**冇喺生成前強制定義每個 batch 嘅邊界。**
>
> **強制執行流程(每場必須嚴格遵守 — Priority 0):**
>
> **Step A — 分析前必須先計算批次分配:**
> ```
> TOTAL_HORSES = [從 Racecard 數出嘅出賽馬匹數(已扣除退出)]
> NUM_BATCHES = ceil(TOTAL_HORSES / BATCH_SIZE)
>   BATCH_PLAN:
>   Batch 1: Horse #1, #2, #3
>   Batch 2: Horse #4, #5, #6
>   ...
>   Batch N: Horse #X, #Y(最後一批馬匹)
>   VERDICT BATCH(獨立): Top 4 + 盲區 + CSV
> ```
>
> **Step A2 — 批次計劃寫入 task.md(P27 — 2026-03-27 新增):**
> 計算完 BATCH_PLAN 後,必須將批次分解寫入 task.md。嚴禁只寫「分析 Race N」一行 — 必須逐批列出:
> ```
> - [ ] Race N 分析(M 匹馬 × K 批次 + VERDICT)
>   - [ ] Batch 1: #1, #2, #3
>   - [ ] Batch 2: #4, #5, #6
>   - [ ] ...
>   - [ ] Batch K: #X, #Y(最後一批馬匹)
>   - [ ] VERDICT BATCH: Top 4 + ç›²å € + CSVï¼ˆç ¨ç«‹ tool call)
>   - [ ] Compliance Check
> ```
> æ­¤å šæ³•ä»¤ LLM 在執行時有明確嘅 checklist é€ é …æ‰" ✅,減å°'è·³æ‰¹æˆ–å ˆä½µæ‰¹æ¬¡å˜…æ©Ÿæœƒã€'
>
> **Step A3 — Speed Map 初稿生成（Python 輔助）:**
> 若 Racecard 檔案可用，執行 Speed Map 初稿生成器：
> `
> python .agents/scripts/au_speed_map_generator.py <Racecard.md> --distance <Distance>
> `
> 輸出包含 PACE_TYPE_SUGGESTION + LEADER_COUNT，LLM 必須 Review & Adjust（唔係盲信），可大幅減少 Speed Map 幻覺風險。
>
> **Step B — é€ æ‰¹åŸ·è¡Œä»¥ä¸‹å¾ªç'°ï¼ˆä¸ å ¯è·³é Žä»»ä½•æ­¥é©Ÿï¼‰ï¼š**
> 
> **[Per-Batch Skeletal JIT Injection] (強制防呆機制)**
> 在每次執行獨立 tool call 寫入 Batch 的分析前,你**必須強制**使用 `view_file` 重新讀取 `au_horse_analyst/resources/06_templates_core.md` 裡的 `<Horse_Microscope_Skeleton>` (第二部分)。
> 嚴禁憑記憶默寫結構。你必須將該骨架原封不動地複製並向下填充,確保 10大欄位(段速法醫、EEM能量、賽績線、風險儀表板、評級矩陣等)一個不漏!
> 
> ```
> FOR EACH batch IN BATCH_PLAN:
>   0. 🗺️ PART 1 (僅 Batch 1) — 若為本場第一個 batch,**必須先寫入 [第一部分] 🗺️ 戰場全景:**
>      - 賽事格局表（班次/條件/路程/馬場/場地/步速預測）
>      - Speed Map（領放群/前中段/中後段/後上群）
>      - **⚠️ 嚴禁跳過 Part 1 直接寫馬匹分析！**
>   1. 📠 WRITE — 用 `run_command` Python Heredoc One-Step Pattern (P33-WLTM): cat PYEOF > .agents.agents/tmp/batch_N.py → python3 .agents.agents/tmp/batch_N.py → safe_file_writer.py 寫入該 batch（最多 BATCH_SIZE 匹馬）
>   2. 🔠 SCAN — view_file 驗證 10 section headers 存在
>   3. ✅ QA — 執行 Batch QA Agent
>   4. 🔒 TOKEN — 寫入 BATCH_QA_RECEIPT 到 Analysis.md
>   5. 📋 REPORT — 在聊天中回覆用戶 Batch QA 結果
>   6. ☑️ TASK — 在 task.md 中將該批次標記為 [x]
>   7. ➡️ NEXT — 只有完成以上 6 步後,才開始下一個 batch
> END FOR
> ```
>
> **[SIP-DA01] 多角度裁決協議 (Multi-Perspective Verdict Protocol)**
> 
> **寫 Verdict 之前必須完成以下 5 步自我辯論，嚴禁跳過。**
> 
> **Step A — Form Selection (表面實力選馬):**
> 基於全場分析，列出實力最高嘅 Top 3。
> 只考慮: 近6場、班際、騎練配搭、季績。
> 
> **Step B — Track/Pace Challenge (步速場地挑戰):**
> 針對每匹 Top 3 馬:
> - Speed Map 有利定不利？
> - 步速若同預測唔同，受惠定受損？
> - Track Bias 影響？
> 
> **Step C — Place Probability Audit (位置概率審計):**
> ⚠️ 最關鍵！針對每匹 Top 3 馬:
> 1. 真係跑得入前3名嗎？
> 2. 有冇「死穴」？(大外檔+慢步速 / EEM耗盡 / 場地唔啱)
> 3. 有冇其他馬 Place Probability 更高？→ 必須提名替代馬
> 
> **Step D — Value Check (值博率檢查):**
> - 邊匹被過度追捧 (Underlay)?
> - 邊匹賠率相對高但實力唔差 (Overlay)?
> 
> **Step E — Final Verdict (最終裁決):**
> 綜合 A-D，產出修訂版 Top 4。
> 必須標註:「原始 Top 3: [A, B, C] → 修訂後: [A, D, B]（C 被替換因為 [理由]）」
> 
> **[JIT Template Protocol]** 在所有馬匹分析 Batch 完成,並準備寫入「Verdict Batch / 第三部分」前,你必須強制作出一次 `view_file` tool call,重新讀取 `resources/session_start_checklist.md` 裡面的 `<Top4_Verdict_Skeleton>`。 在未重讀該模板前,嚴禁直接吐出任何 Top 4 結果。
>
> **[Python Verdict Skeleton 自動生成 — P38 新增]**
> 若 LLM 已完成全場馬匹分析，可執行以下 Python 工具自動生成 Part 3+4+5 骨架：
> ```
> python .agents/skills/au_racing/../au_wong_choi/scripts/compute_rating_matrix_au.py --input <dimensions.json> --output <verdict_skeleton.md>
> ```
> Python 會自動：預填 Top 4 馬號馬名、評級✅數、Emergency Brake 判斷、Exotic Box 觸發條件、Upset Potential 計算。
> LLM 只需補充 `{{LLM_FILL}}` 標記嘅自由文字區（核心理據、風險、Speed Map 回顧等）。
> **使用條件：** 需要先準備 `dimensions.json`（從分析中提取每匹馬嘅 8 維度評級）。若唔方便製備 JSON → 照舊用 JIT 手動骨架。

>
> **⛔ COMPLETION_GATE(強制 — 回覆用戶前必須通過 — P31):**
> 喺 batch 循環結束後、通知用戶之前,你必須強制執行以下 Python 驗證:
> 🚨 **你完成分析後，必須強制自己 run `python3 .agents/scripts/completion_gate_v2.py <你正在分析的檔案路徑> --domain au` 進行檢驗。不過關不准完成任務！**
> 如果檢驗失敗 (出現 `❌ [FAILED]`)，你已違規 → 立即根據報告內容，自行修正錯誤的段落 (例如補回標籤、擴充字數或補回漏寫章節) 並重新執行 validator 直到 `✅ [PASSED]` 為止！
>
> **🔢 COMPLETION_GATE 通過後 — 強制數學驗證 (學自 HKJC — Priority 0):**
> COMPLETION_GATE 通過後，**必須**再執行以下 Python 驗證：
> ```
> python .agents/skills/au_racing/../au_wong_choi/scripts/verify_math.py "<分析檔案路徑>" --fix
> ```
> 此工具自動修正：
> - Base grade 同 matrix 查表結果唔一致
> - Final grade 漂移超過 1 級
> - 矩陣算術 ✅/❌ 計數錯誤
> - CSV grade 同正文 grade 唔同步
> - `[FILL]` / `{{LLM_FILL}}` 殘留偵測（代表 LLM 跳過咗填充）
>
> ⚠️ 若 `--fix` 修正咗任何內容 → 自動 re-verify。若仍有 FILL 殘留 → 停低通知用戶。
>
> **⛔ 硬性攔截器:** 若你發現自己正在一個 tool call 中寫入超過 BATCH_SIZE 匹馬 → **立即停止生成**,刪除多餘內容,拆分為獨立 tool calls。
> **⛔ 反模式偵測:** 若你嘅 tool call 中同時出現 `Batch 1` 和 `Batch 2` 嘅馬匹 → 你已違反此規則 → 立即停止。
- **每場分析完畢並儲存後,必須先執行合規檢查,然後才執行「賽間推進協議」。**

> [!CAUTION]
> **⛔ P33 — VERDICT JIT TEMPLATE CHECKPOINT（學自 HKJC — Priority 0）**
>
> **強制規定:**
>
> 1. **寫入 VERDICT BATCH 之前,必須 `view_file` 讀取 `06_templates_core.md`（Part 3 格式）同 `06_templates_rules.md`（觸發規則）。** 冇讀 = 禁止寫入 VERDICT。
> 2. **VERDICT BATCH 結構自檢清單(寫入後逐項驗證,缺一 = 重做):**
>    - [ ] `## [第三部分] 🏆 全場最終決策` — 正確標題
>    - [ ] Speed Map 回顧
>    - [ ] `Top 4 位置精選` — 使用 🥇🥈🥉🏅 清單格式(非 numbered list / 非 table)
>    - [ ] 每個選項有 4 sub-bullets: 馬號馬名 / 評級✅數 / 核心理據 / 最大風險
>    - [ ] 🎯 Top 2 入三甲信心度(🟢/🟡/🔴)
>    - [ ] [SIP-FL03] 🎰 Exotic 建議
>    - [ ] [SIP-RR01] 📗📙 雙軌 Top 4(若 SIP-1 觸發)
>    - [ ] [第四部分] 分析陷阱 — 含步速逆轉保險 + 緊急煞車
>    - [ ] 🐴⚡ 冷門馬總計
>    - [ ] [第五部分] CSV Block — ` ```csv ` 存在
>    - [ ] CSV 中 Rank 1 嘅馬 = 🥇 第一選
> 3. **呢個 checkpoint 適用於所有場次、所有引擎、即使係 Session Recovery。**

> [!CAUTION]
> **⛔ P34 — VERDICT FORMAT ANTI-DRIFT HARDENER（學自 Race 6 2026-04-06 — Priority 0）**
>
> **歷史教訓:** 2026-04-06 Race 6 Verdict 嚴重格式漂移 — Top 4 使用了壓縮式單行 bullet（`🥇 首選 (1st): [5] Wrathful (A+) — 理由...`）而非模板規定的多行結構清單。同時遺漏了 Speed Map 回顧、Top 2 信心度、Exotic 建議、第四部分分析陷阱、及第五部分 CSV。根本原因：LLM 跳過了 P33 JIT 讀取步驟，憑記憶生成自創格式。
>
> **強制規定:**
>
> 1. **TOP 4 格式鐵律（零容忍）：** 每個選項 **必須** 使用以下精確結構，禁止壓縮成單行：
>    ```
>    🥇 **第一選**
>    - **馬號及馬名:** [號碼] [名字]
>    - **評級與✅數量:** `[評級]` | ✅ [數量]
>    - **核心理據:** [理由]
>    - **最大風險:** [風險]
>    ```
>    **違規模式黑名單（嚴禁使用以下任何格式）：**
>    - ❌ `🥇 首選 (1st): [X] Name (Grade) — 理由`（壓縮式單行）
>    - ❌ `| 排名 | 馬名 | 評級 |`（表格式）
>    - ❌ `1. Wrathful (A+)`（數字清單式）
>    - ❌ 任何自創標題如「📊 Top 4 排名」「🎯 行動指令」「💡 投注策略建議」
>
> 2. **Verdict 五大區段完整性門檻（缺一 = FAILED）：**
>    - `[第三部分]`: Speed Map 回顧 + Top 4 位置精選 + Top 2 信心度 + Exotic 建議
>    - `[第四部分]`: 市場預期警告 + 步速逆轉保險 + 緊急煞車 + 冷門馬總計
>    - `[第五部分]`: CSV Block
>
> 3. **POST-WRITE 格式驗證（寫入後立即執行）：**
>    寫完 Verdict 後，在內部思考中執行以下 3 秒快檢：
>    - 搜索 `🥇 **第一選**` — 存在？✅/❌
>    - 搜索 `- **馬號及馬名:**` — 存在 ≥4 次？✅/❌
>    - 搜索 `Top 2 入三甲信心度` — 存在？✅/❌
>    - 搜索 `步速逆轉保險` — 存在？✅/❌
>    - 搜索 ` ```csv ` — 存在？✅/❌
>    **任何一項 ❌ → 立即重寫 Verdict，不得繼續。**


> [!CAUTION]
> **⛔ P36 — ZERO-TOLERANCE ANTI-DRIFT PROTOCOL（學自 2026-04-06 Race 8 — Priority 0）**
>
> **歷史教訓:** 雖然已有 P33 同 P34 規定 JIT 讀取，但喺長時間連續運作 (長達 Race 8) 時，LLM 仍然會因為 Context Window 衰退而偷懶跳過讀取，憑模糊記憶生成結構不全、字數極度不足的 Bullet points。
>
> **強制對策 (三連擊):**
> 1. **JIT 零容忍宣讀 (Zero-Tolerance Template Refresh):** 每次準備生成 Batch 寫檔腳本之前，**無論自認記憶多麼清晰，都必須強制 view_file 讀取 `06_templates_core.md` 的 Horse_Microscope_Skeleton。** 無宣讀 = 違規。
> 2. **強制落實「預建骨幹法」 (Skeleton Copy-Paste Enforcement):** 生成 Python Markdown 變量時，**不准逐行寫**。必須先由 Template 完美 Copy 出整個馬匹的骨幹（全套 11 個 Emoji 標題），死板地貼齊後，才開始將分析內容填入相應位置，保證結構 100% 不丟失。
> 3. **落實 Session 切割 (Hard Session Splits for Context Relief):** 到達 Race 4 結束必須強制截斷並輸出交接指令 (Handoff Prompt)，嚴格執行「換 Chat 重新連線」，避免記憶體超載而出現妥協式偷懶。

> [!CAUTION]
> **🧠 P38 — CONTEXT WINDOW 4 層管理協議（學自 HKJC — Priority 0）**
>
> **歷史教訓:** AU 引擎分析到 Race 4+ 時品質衰退明顯（段速簡化、核心邏輯變短、矩陣壓縮）。根因：Context Window 壓力無明確管理策略，前幾場分析嘅 token 開銷佔據可用空間。
>
> **4 層防禦機制:**
>
> **Layer 1 — 禁止回讀（Per-Race Context Isolation）:**
> 每場分析完成後，嚴禁回讀前場嘅分析內容（除非做跨場對手分析）。
> - ⛔ 嚴禁「參考 Race 1 嘅格式去寫 Race 4」
> - ⛔ 嚴禁 `view_file` 讀取已完成場次嘅 Analysis.md
> - ✅ 只允許讀取 `_session_state.md` 恢復品質基線數字
>
> **Layer 2 — 資源懶加載（Race 2+ Lazy Reload）:**
> Race 2+ 開始前，只需重讀以下 3 個核心資源（唔好重讀所有 Tier 1）：
> 1. `06_templates_core.md`（骨架 JIT reload）
> 2. 當場 Racecard + Formguide
> 3. `_Meeting_Intelligence_Package.md`（若場地有變化）
> 其餘 Tier 1 資源（01_system_context, 02a-02d 等）應已在記憶中保留。
>
> **Layer 3 — 動態 Batch Size 降級:**
> 若偵測到以下蒸發訊號 → 自動將 BATCH_SIZE 從 3 降至 2：
> - 當前場次為 Race 4+（Session 內第 4 場或以上）
> - 連續 2 批 QG-CHECK 需要打回重寫
> - 任何 batch 出現截斷或結構不完整
>
> **Layer 4 — 蒸發標記偵測:**
> 每個 Batch 完成後，在內部思考中快速自檢：
> - 📏 當前批次平均字數 vs Batch 1 平均字數 → 若 < 70% → 蒸發警報
> - 📊 矩陣理據是否變成「一般」「正常」等空泛詞 → 若 ≥2 個維度為空泛 → 蒸發警報
> - 🧭 陣型預判是否被省略 → 若缺失 → 蒸發警報
> 任何蒸發警報 → 標記 `⚠️ CONTEXT_EVAPORATION_DETECTED` → 降級 BATCH_SIZE + 強制 JIT reload

> [!CAUTION]
> **⛔ P37/P39 — ANTI-HALLUCINATION DEEP VERIFICATION（P37 學自 Rosehill, P39 學自 Sale 2026-04-08 — Priority 0）**
>
> **歷史教訓:**
> - P37: 2026-04-06 Rosehill — Colourful Emperor、Point And Shoot、Hellabella 往績數據被幻覺扭曲。
> - P39: 2026-04-08 Sale — **8 場中 5 場驗證失敗，共 15 個名次錯誤。** Harpalee (Rating 70) 被虛構為 S- 首選但實際應為 D。
>   根因：(1) Anchoring Bias (2) Settled Position 混淆(最普遍) (3) Trial 混淆 (4) Last10 `0`=10th 忘記 (5) Odds 偏差
>
> **=== 第一道防線：Python 預提取（將數據提取從 LLM 轉移到 Python）===**
>
> 1. **inject_fact_anchors.py V2（Racecard + Formguide 雙重提取 + 賽場檔案）：**
>    Wong Choi 喺開始分析前，**必須**先執行：
>    ```
>    python3 .agents/scripts/inject_fact_anchors.py "<Racecard.md>" "<Formguide.md>" --max-display 5 --venue {VENUE}
>    ```
>    輸出會自動寫入同目錄下嘅 `Facts.md` 文件（例如 `04-08 Race 1 Facts.md`）。
>    V2 版本自動提取並注入：
>    - `Last 10` string + 自動解碼近績序列（含 `0`=10th 處理）
>    - Racecard `Last:` ＋ Trial 自動偵測標記
>    - **最近 10 場非 Trial 正式比賽**嘅完整賽績檔案（Markdown Table 格式，顯示最近 5 場）
>    - 每場含：場地、路程、名次、跑位軌跡、PI、EEM 跑法/消耗、備註/幹事報告
>    - 🆕 **賽場檔案** (`--venue`): 自動從 `04b_track_*.md` 提取周長/直路/偏差/距離檔位特性
>
> 1b. **generate_skeleton.py（自動骨架生成 — 取代 LLM 複製貼上）：**
>    生成 Facts.md 後，**必須**執行：
>    ```
>    python3 .agents/scripts/generate_skeleton.py "<Facts.md>"
>    ```
>    輸出會自動寫入 `Analysis.md`，包含：
>    - 📋 完整賽績檔案表格（已從 Facts.md 自動嵌入，LLM 唔需要複製）
>    - 📊 段速趨勢 + ⚡ EEM 能量摘要（已從 Facts.md 自動嵌入）
>    - 所有分析欄位嘅 `[FILL]` 佔位符（LLM 只需填充分析部分）
>
> 1c. **🔗 賽績線 — Top-3 對手追蹤 (V2 2026-04-08 升級):**
>    每匹馬近 5 場正式比賽嘅前 3 名對手（頭馬/亞軍/季軍），自動查冊後續成績。
>    由 `claw_profile_scraper.py` + `compute_form_lines_via_api()` 自動執行。
>    **三級強度分類:**
>    | 等級 | 標籤 | 判定標準 |
>    |:---|:---|:---|
>    | 超強組 | ✅✅ | 對手勝 ≥2 次，或勝 ≥1 次且在 Metro 賽場 |
>    | 強組 | ✅ | 對手後續有 1 次勝出 |
>    | 中組 | ⚠️ | 對手 Place Rate ≥ 40% 但未贏 |
>    | 弱組 | ❌ | 對手 Place Rate < 40% 且未贏 |
>    **5 級綜合評估:** ✅✅極強 / ✅強 / 中強 / 中弱 / ❌弱
>
> **⛔ P40 — Facts.md 為唯一數據源 (2026-04-08 新增 — Priority 0)：**
>    Analyst 嘅任務係「基於呢啲已驗證嘅事實做分析判斷」，唔係自行從 Formguide 重新提取數據。
>    ⭐ LLM 必須以 `Facts.md` 中嘅完整賽績表格作為分析嘅唯一數據來源。
>    ⛔ Analyst 嚴禁修改 `📌 事實錨點` 及 `📋 完整賽績檔案` 區域嘅任何數據。
>    ⛔ 所有中間產物（Facts.md 等）必須保存到賽事資料夾內，不可使用 /tmp。
>
> **=== 第二道防線：LLM 行為鐵律（6 條規則，所有引擎適用）===**
>
> 2. **RATING_BLINDNESS（反錨定偏差 — Rule 1）：**
>    分析每匹馬時，**先完成 Formguide 近績法醫**（名次、段速、賽後評語 — 已由 Python 預提取），
>    **然後才睇** Rating 同練馬師配搭。嚴禁先預設「呢匹馬好勁」再搵證據支持。
>    ⚠️ 大馬房 + 高 Rating ≠ 一定勁。必須用近績數據證明。
>
> 3. **SETTLED ≠ FINISHED（反跑位混淆 — Rule 2 — 最常見錯誤！）：**
>    Formguide 嘅 `Xth@800m / Xth@400m / Xth@Settled` 係「賽中跑位追蹤」，
>    **絕對唔等於最終名次**。真正名次必須且只能從以下來源確認：
>    (a) Last 10 string 解碼（Python 已預提取到事實錨點）
>    (b) Formguide result line 搵出分析對象嘅名字位置
>    ⛔ 嚴禁將 Settled position 寫入「上仗名次」欄位。自檢：上仗名次 X 係咪等於事實錨點嘅 Last 10 首位？
>
> 4. **LAST_10_ZERO_RULE（0=10th — Rule 3）：**
>    Last 10 string 中嘅 `0` = 第 10 名。讀取方向：左到右 = 最新到最舊，`x` = trial（跳過）。
>
> 5. **TRIAL_AWARENESS（試閘識別 — Rule 4）：**
>    Racecard `Last:` field 經常指向 Trial。Python V2 已自動標記 `⚠️[TRIAL]`。
>    若 Last: 係 Trial → **上仗**必須引用 Last 10 解碼嘅首個真實比賽名次。
>
> 6. **FORMGUIDE CROSS-READ（強制交叉閱讀 — Rule 5）：**
>    每匹馬寫入「上仗名次」前，必須核對 Python 預提取嘅 `📋 Formguide 近 N 場正式比賽` 區域。
>    三者一致（Last 10 解碼 / Formguide result / 分析寫入）才可確認。
>
> 7. **ODDS_INDEPENDENCE（反賠率偏差 — Rule 6）：**
>    分析每匹馬時，必須先完成評級矩陣，**然後才允許參考 Flucs 賠率**。
>    Odds 只可在以下位置使用：(a) 第一部分賽事格局表 (b) Verdict 嘅 Value Check
>    ⛔ 嚴禁因為一匹馬係大熱門就自動給高評級。評級必須由 8 維度矩陣客觀產出。
>
> **=== 第三道防線：自動驗證（Python 硬對比）===**
>
> 8. **verify_form_accuracy.py V2（每 Batch 完成後強制執行）：**
>    每個 Batch 寫入完成後，必須執行：
>    ```
>    python3 .agents/scripts/verify_form_accuracy.py "<Analysis.md>" "<Racecard.md>" "<Formguide.md>"
>    ```
>    V2 檢查：(a) 上仗名次 vs Last 10 (b) Settled Position 混淆偵測 (c) Trial 識別 (d) 0=10th 驗證
>    ❌ 若有 ❌ 或 🔄 錯誤 → 必須修正後再繼續。
>
> 9. **completion_gate_v2.py 自動偵測（唔再需要 --racecard）：**
>    `completion_gate_v2.py` 現已自動偵測同目錄下嘅 Racecard 同 Formguide，
>    無需手動傳入 `--racecard` 參數。Form Accuracy 驗證變成 MANDATORY 步驟。
>
> **=== Gemini 引擎專屬加固（P39-GEMINI）===**
>
> 10. **GEMINI_FACT_CHECK_GATE：** 每匹馬寫完後，Gemini 必須喺內部思考中
>     自問：「我寫嘅上仗名次 X 係從邊度嚟？事實錨點 Last 10 解碼首位係幾多？兩者一致嗎？」
>     若唔一致 → 立即改正。
>
> 11. **GEMINI_ANTI_NARRATIVE：** 禁止使用以下虛構性描述除非有 Formguide Video/Note 直接引用支持：
>     - 「全場最快末段」「驚人追勢」「段速水平遠超對手」「城市級表現」
>     → 必須引用 Formguide 嘅 Note/Video 原文作為來源。Python 已將 Note/Video 預提取到事實錨點中。
>
> 12. **GEMINI_SESSION_PRESSURE：** Race 5+ 開始，若 verify_form_accuracy 偵測到 ≥2 個名次錯誤
>     → 強制 BATCH_SIZE 降為 2 + 強制 JIT reload templates

> [!CAUTION]
> **強制執行順序(不可變更):** 全場馬匹分析完畢 → 合規檢查 → 合規通過 → 賽間推進協議。**嚴禁跳過合規檢查。**

### 逐場手動推進協議 (P33-WLTM — 2026-03-25)

合規檢查完成後,讀取 `_session_issues.md` 中 Race [X] 嘅問題,按以下邏輯推進:

**🟢 合規 PASSED + 冇 CRITICAL:**
→ 顯示合規結果摘要(1 行)+ MINOR 問題列表(各 1 行)
→ 更新 `_session_state.md`
→ **停低等用戶指示**:用戶確認後才開始下一場(嚴禁自動推進)

**🔴 合規 PASSED + 有 CRITICAL:**
→ 顯示 CRITICAL 問題簡述 + 建議修正方案
→ **停低等用戶指示**:修正 / 跳過 / 停止
→ 若用戶選擇修正:最多重試 1 次(熔斷機制)
→ 若重試後仍有 CRITICAL:降級為 MINOR,繼續下一場

**❌ 合規 FAILED:**
→ 自動重試 1 次
→ 仍然 FAILED → **停低等用戶指示**

**🛑 Race 4 完成後 — 強制 Session 分割 + 自動生成 Handoff Prompt:**
→ 合規通過後,先更新 `_session_state.md`,然後**硬性停止**
→ **自動生成以下完整 handoff prompt** 供用戶直接複製貼到新 chat:

```
📋 請複製以下完整指令到新 chat:
---
🚨 STOP — 你必須先完整讀取 @au wong choi 所有 protocol 才可開始分析！嚴禁憑記憶生成任何內容！

@au wong choi, 繼續分析 {VENUE} {DATE} Race 5+ for {ANALYST_NAME}

Race 1-4 已完成,分析檔案在:
{ANALYSIS_FOLDER_PATH}

Racecard: {RACECARD_PATH}
Formguide: {FORMGUIDE_PATH}
Meeting Intelligence: _Meeting_Intelligence_Package.md

場地: {TRACK_CONDITION}, {WEATHER}
天氣穩定性: {WEATHER_STABILITY}

⚠️ 強制資源載入（在分析任何馬匹之前必須完成）:
你必須先用 view_file 逐一讀取以下文件,讀完後回覆 checklist 確認。未完成不准開始分析:
1. ../../au_wong_choi/SKILL.md（完整讀取 — 確認 P33-WLTM 寫入協議）
2. ../../au_wong_choi/resources/horse_analysis_skeleton.md（確認雙軌閘門規則）
3. ../au_horse_analyst/resources/06_templates_core.md（確認 Part 1 戰場全景 + 骨架格式）
4. ../au_horse_analyst/resources/06_templates_rules.md（Verdict 觸發規則）
4. 場地模組（按今場選 1 個）

⚠️ 強制執行規則:
- BATCH_SIZE: {BATCH_SIZE}
- Batch 1 必須先寫 [第一部分] 戰場全景（Speed Map + 賽事格局表）
- 天氣 {WEATHER_STABILITY}: STABLE 則省略📗📙 / UNSTABLE 則強制輸出
- 所有寫入用 P33-WLTM Python Heredoc One-Step Pattern（嚴禁 write_to_file）
- 每匹馬完整 5-block × 13-subfield 分析
- Verdict 必須獨立 tool call 寫入
- 完成後必須跑 completion_gate_v2.py
---
```
→ 變數填充規則:
  - `{VENUE}` = 今場馬場名(如 Randwick Kensington / Flemington / Caulfield)
  - `{DATE}` = 賽事日期(如 2026-03-25)
  - `{ANALYST_NAME}` = 當前操作員名稱(如 Kelvin / Heison)
  - `{ANALYSIS_FOLDER_PATH}` = 分析檔案資料夾相對路徑
  - `{RACECARD_PATH}` = Racecard 檔案相對路徑
  - `{FORMGUIDE_PATH}` = Formguide 檔案相對路徑
  - `{TRACK_CONDITION}` = 場地狀態(如 Heavy 8 / Good 4)
  - `{WEATHER}` = 天氣(如 晴天 24°C)
  - `{BATCH_SIZE}` = 當前 session 使用嘅 BATCH_SIZE(2 或 3)
  - `{WEATHER_STABILITY}` = 天氣穩定性(STABLE 或 UNSTABLE)
→ 若用戶堅持繼續 → 允許但喺 Analysis.md 加入 `⚠️ CONTEXT_PRESSURE_WARNING` 標記

> [!CAUTION]
> **🚨 MUST_OUTPUT_HANDOFF — 強制輸出交接指令(P29 — 2026-03-29 新增):**
>
> **歷史教訓:** Handoff prompt 有時生成有時唔生成,用戶需要人手拼接指令。
>
> **強制規定(Priority 0):**
> 1. **Race 4 合規通過後,handoff prompt 係你嘅最後一個輸出。** 唔可以喺 handoff 之前停止。
> 2. **所有 `{VARIABLE}` 必須被實際值替換。** 嚴禁輸出未填充嘅佔位符。
> 3. **Handoff prompt 必須喺代碼區塊內**,方便用戶一鍵複製。
> 4. **自檢觸發器:** 若你完成 Race 4 合規但冇輸出 handoff prompt → 你已違規 → 立即補上。
> 5. **Context Pressure handoff 亦適用此規則。**

**🔶 任何時候感覺到 Context Pressure(回應變慢 / 開始壓縮 / 忘記格式):**
→ 立即更新 `_session_state.md`(確保所有進度已記錄)
→ 通知用戶並**輸出完整 handoff prompt**:
```
⚠️ 偵測到 context window 壓力。建議開新 chat 繼續。

📋 請複製以下指令到新 chat:
---
🚨 STOP — 你必須先完整讀取 @au wong choi 所有 protocol 才可開始分析！嚴禁憑記憶生成任何內容！

@au wong choi, 繼續分析 {VENUE} {DATE} Race {NEXT_RACE}+ for {ANALYST_NAME}

已完成場次: Race 1-{LAST_COMPLETED_RACE}
分析檔案在: {ANALYSIS_FOLDER_PATH}

Racecard: {RACECARD_PATH}
Formguide: {FORMGUIDE_PATH}
Meeting Intelligence: _Meeting_Intelligence_Package.md

場地: {TRACK_CONDITION}, {WEATHER}
天氣穩定性: {WEATHER_STABILITY}

⚠️ 強制資源載入（在分析任何馬匹之前必須完成）:
你必須先用 view_file 逐一讀取以下文件,讀完後回覆 checklist 確認。未完成不准開始分析:
1. ../../au_wong_choi/SKILL.md
2. ../../au_wong_choi/resources/horse_analysis_skeleton.md
3. ../au_horse_analyst/resources/06_templates_core.md
4. ../au_horse_analyst/resources/06_templates_rules.md
4. 場地模組

⚠️ 強制執行規則:
- BATCH_SIZE: {BATCH_SIZE}
- Batch 1 必須先寫 [第一部分] 戰場全景
- 天氣 {WEATHER_STABILITY}: STABLE 則省略📗📙 / UNSTABLE 則強制輸出
- 所有寫入用 P33-WLTM Python Heredoc One-Step Pattern
- 每匹馬完整 5-block × 13-subfield 分析
- Verdict 必須獨立 tool call 寫入
- 完成後必須跑 completion_gate_v2.py
---
```

**最後一場完成後 → 正常進入 Step 4.5。**

**🧹 CONTEXT_WINDOW_RELIEF v3 — 六層防禦(P18v3 — 2026-03-25 更新):**

> **歷史教訓:** 分析到 Race 3+ 時,已完成批次/場次嘅 Analysis 內容仍留在 context window 中。LLM 注意力被攤薄,導致後期分析質量逐漸下降。量化數據:Race 4 完成後達 ~185K/200K tokens。

**第 1 層 — 禁止回讀:**
1. **每完成一個 Batch 後不再回讀前面輸出。** 後續 Batch 只需 `view_file` 最後 5 行,**嚴禁**回讀前面 Batch。
2. **完成一場後不再回讀前場輸出。** 嚴禁再次 `view_file` 該場嘅 Analysis.md。
3. **嚴禁「參考前批/前場分析格式」。** 格式標準來自 SKILL.md 和 `06_templates_core.md`。

**第 2 層 — Resource 懶加載(Race 2+ 節省 ~25K tokens):**
- **Race 1:** Analyst 正常讀取全部 resources
- **Race 2+:** Wong Choi 指示 Analyst **只重讀** `01_system_context.md` + `06_templates_core.md` + 相關場地檔

**第 3 層 — 動態 Batch Size(P28 更新):** ENV_TOKEN_CAPACITY=HIGH: `BATCH_SIZE: 3`,LOW: `BATCH_SIZE: 2`

**第 4 層 — 提取蒸發標記:** Form Guide 提取完成後輸出 `📤 EXTRACTION_CONSUMED` 標記

**第 5 層 — 強制 Session 分割:** Race 4 完成後硬性停止

**第 6 層 — 跨場數據最小化:** 只保留 Top 4 摘要 + 品質基線 + `_session_state.md` 路徑

**🗂️ Session State Persistence(_session_state.md — P16):**
Race 1 完成後建立 `{TARGET_DIR}/_session_state.md`:
```
# Session State
- BATCH_BASELINE: [Race 1 平均字數/匹]
- COMPLETED_RACES: [1]
- QUALITY_TREND: Stable
- LAST_RACE_WORDCOUNT: [平均字數]
- URL: [原始 URL]

## Decision Diary [Improvement #1]
### Race N
- Pace Judgement: [e.g. Genuine -> #3 + #7 leaders]
- Key Downgrade/Upgrade: [e.g. #5 SIP-RF01 -> B+]
- Controversial Decision: [e.g. #8 EEM vs recent form -> B]
- Longshot Alert: [e.g. #11 lightweight + good draw -> C+]

## Cross-Race Intelligence
### Track Bias Observations
- [e.g. Inside draw advantage - R1 top 4 all from barrier 1-4]
### Pace Pattern
- [e.g. Overall pace bias fast - 3 races had leader collapse]
```
每完成一場更新此檔。新 session `@wong_choi 繼續` 時自動讀取恢復。

**Reflector Closed Loop [Improvement #4] (Step 1.5c):**
After Step 1.5 Intelligence Package generation, additionally execute:
1. Search TARGET_DIR for most recent Reflector Report (*_Reflector_Report.md)
2. If found, extract: recent SIP changes, Engine Health Scan results, Observation Log active items
3. Add to Race Day Briefing:
   ```
   Warning: Reflector Reminder (from latest review):
   - [SIP change summary]
   - [Engine health status]
   - [Observations requiring attention]
   ```
4. If no Reflector report found, skip this step. No impact on normal flow.



呼叫 `AU Horse Analyst` 分析當場賽事。

**傳遞畀 Analyst 嘅數據包**:

**A) 賽事元數據 (Race Metadata)**:
1. 賽事資訊:`[DATE]`、`[VENUE]`、`[Race Number]`
2. **Meeting Intelligence Package**(完整傳遞)

**B) 場地與賽制參數 (Track Parameters)**:
3. **場地路由:** `[TRACK_MODULE: RANDWICK / ROSEHILL / FLEMINGTON / CAULFIELD / MOONEE_VALLEY / EAGLE_FARM / DOOMBEN / PROVINCIAL]`
   - 判斷邏輯:根據 VENUE 名稱直接對應(Canterbury / Morphettville / Ascot Perth 等省賽場 → PROVINCIAL)
4. **賽制:** `[RACE_TYPE: STANDARD / STRAIGHT_SPRINT]`
   - 判斷邏輯:Flemington 1000-1200m 直路起步 → STRAIGHT_SPRINT,其餘 → STANDARD
5. **場地表面:** `[SURFACE: TURF / SYNTHETIC]`
   - 判斷邏輯:Geelong / Pakenham → SYNTHETIC,其餘 → TURF
6. **場地狀態:** `[GOING: GOOD_3 / SOFT_5 / SOFT_6 / SOFT_7 / HEAVY_8 / ...]`
7. **距離類別:** `[DISTANCE_CATEGORY: SPRINT / MIDDLE / STAYING]`
   - 判斷邏輯:≤1300m → SPRINT,1400-1600m → MIDDLE,≥1800m → STAYING

**C) 操作約束 (Operational Constraints)**:
8. 強制使用本地 Racecard/Formguide .md 檔案,未經准許不可自行上網搜尋已提供嘅公共數據
9. **活躍名單:** `[ACTIVE_TRAINERS: 練馬師1, 練馬師2, ...]`、`[ACTIVE_JOCKEYS: 騎師1, 騎師2, ...]`
   - 從排位表提取當場嘅練馬師/騎師名單
10. **賽事組成:** `[DEBUT_RUNNERS: N]`(從排位表識別無近績紀錄嘅馬匹數量)
11. **審核級別:** `[FULL_AUDIT: NO]`(預設值 — 標準分析只需核心自檢。僅在高風險賽事或用戶特別要求時設為 `YES` 以啟用完整擴展審核)
12. **[SIP-1 雙軌觸發指令]:** 若情報包中包含 `[WEATHER_UNSTABLE: TRUE]` 或預測場地為 Heavy,你必須在呼叫 Analyst 時**強制附加以下指令**:「⚠️ **天氣不穩定/預測為重地**:你必須啟動『SIP-1 雙軌敏感度分析 (Dual-Track Sensitivity Check)』,在分析中明確指出哪些馬匹是『場地極敏感』(僅 Heavy 有優勢)並在結論提供容錯建議。」
13. **[ODDS_SOURCE 賠率來源 — P22]:** Analyst 使用嘅賠率必須來自 Racenet Formguide 中每匹馬嘅 `Flucs:` 行。**最後一個數值 = 當前最新市場賠率**。嚴禁使用其他來源或猜測賠率。分析文件嘅 Part 1 戰場全景必須包含 Flucs 賠率表,每匹馬嘅個別分析亦必須引用 Flucs 走勢(如 `$3.2→$3.1 穩定` 或 `$12→$17 漂出`)。

**批次監督與結構驗證**:
BATCH_SIZE 由 Pre-Flight Environment Scan 決定(標準=3 / fallback=2)。

> [!CAUTION]
> **🚨 BATCH QUALITY PROTOCOL — 統合品質規則(P17/P21/P24/P28 — Priority 0)**
>
> **A. 批次結構規則:**
> 1. **分批寫入強制性。** 按 BATCH_SIZE 分批,超出 = 違規。
> 2. **每個 Batch = 獨立 file write (Safe-Writer Protocol (P33-WLTM))。** 由於 IDE 工具存在系統性 deadlock，**完全禁止**使用 `write_to_file` / `replace_file_content` / `multi_replace_file_content`。必須使用 **heredoc → /tmp → base64 → safe_file_writer.py (WLTM)** 三步管道。B1 用 `--mode overwrite`，B2+ 用 `--mode append`。詳見底部 P33-WLTM 完整說明。
> 3. **VERDICT BATCH 獨立且必須極度嚴格遵循模板。** Part 3 + Part 4 + CSV 必須為獨立 tool call。**絕對不允許**使用簡化自創格式。必須包含 `06_templates_core.md` + `06_templates_rules.md` 規定之:`Speed Map 回顧`、`Top 4 位置精選 (強制包含 🥇第一選 清單結構及評級>✅數鐵律)`、`Top 2 入三甲信心度`、`🎰 Exotic 組合投注建議`、以及第四部分的 `分析陷阱`。任何遺漏視同嚴重違規!*(執行 Verdict 前必須在內心清單覆誦檢查這 5 大欄位)*。
> 4. **截斷恢復:** 若被 output token limit 截斷 → BATCH_SIZE 降為 2,重做該 batch。
>
> 批次示例(BS=3):7匹 → B1(3)+B2(3)+B3(1)+VERDICT | (BS=2):7匹 → B1(2)+B2(2)+B3(2)+B4(1)+VERDICT
>
> **B. 全欄位零容忍:**
> 1. **每匹馬(含 D 級)必須包含完整獨立段落,缺一 = 整批重做:**
>    `📌情境` → `賽績總結` → `近六場走勢`(每場各一行) → `馬匹分析` → `🔬段速法醫`(≥3行) → `⚡EEM能量`(≥3行) → `📋寬恕檔案`(≥2行) → `🔗賽績線` → `📊評級矩陣`(8維度各1行) → `💡結論`(核心邏輯+優勢+風險) → `⭐最終評級`
> 2. **自檢:** 寫完數 emoji(🔬⚡📋🔗📊💡⭐),少於 7 = 壓縮中 → 補全。
> 3. **D 級馬用數據解釋差在哪。** 嚴禁「(精簡)」。嚴禁 inline 矩陣。
> 4. **首出馬豁免:** 🔬⚡📋 可寫 N/A,標題必須在。
>
> **C. 品質一致性:**
> 1. **字數門檻:** S/A ≥500字 | B ≥350字 | C/D ≥300字
> 2. **品質基線鎖定:** Race 1 B1 = 基線,後續 ≥ 基線 × 70%。
> 3. **禁止預判評級 → 減少深度。** 先完成全部欄位再得出評級。
> 4. **禁用詞語:** `efficiently`/`quickly`/`精簡`/`壓縮`。評級係結果,唔係減少分析嘅原因。
> 5. **Race 2+ 必須傳遞基線字數提醒。**

**📊 CSV_BLOCK_MANDATORY:** VERDICT BATCH 必須包含 CSV Top 4 數據區塊。自檢:搜索 ` ```csv `,缺 → 補上。

---

**🔍 骨架模板注入(每 Batch 必須):**
每個 Batch 開始前,Wong Choi 注入馬匹分析骨架模板到 Analyst prompt。LLM 嘅任務從「生成分析」變為「填充骨架」。**核心邏輯/結論部分為 LLM 自由發揮區域,但必須嚴格遵守以下品質標準。**

> [!CAUTION]
> **🎯 核心邏輯品質標準 (P33 — 2026-04-04 新增 — Priority 0)**
>
> **歷史教訓:** Race 2/3 的核心邏輯品質極高(生動廣東話 + 數據驅動推理),但 Race 4 嚴重退化為平淡書面語,分析深度大幅下降。根因:「自由發揮」被解讀為「可以偷懶」。
>
> **強制規定:**
>
> **1. 語言風格 — 必須用香港廣東話口吻:**
> - ✅ 正確:「呢匹馬係卡士最高嘅頂王」「完全係湊人數格局」「擺明車馬要強攻」
> - ❌ 錯誤:「今季復出以來狀態反覆」「形勢將非常被動，難以看好」「長期無表現，陪跑分子」
> - 每句核心邏輯必須有「賽馬佬」嘅語氣,好似一個資深馬評人喺同朋友傾偈咁分析
>
> **2. 分析深度 — 必須包含具體數據點:**
> - ✅ 正確:「上仗 1600m 明顯路程偏短都只係緊緊飲恨,今場重返首本 2000m 路程」(引用具體路程 + 賽果邏輯鏈)
> - ✅ 正確:「今季 7 戰未嘗一勝,上仗甚至包尾大敗,近績劣過地底泥」(引用勝率 + 近績序列)
> - ❌ 錯誤:「近況極為低落,接連在次等賽事未能上名」(無具體數據)
> - ❌ 錯誤:「長期無表現，陪跑分子。」(一句帶過,毫無分析可言)
> - 最少引用 2-3 個具體數據點(勝率、段速、場地紀錄、排位效應等)
>
> **3. 篇幅門檻:**
> - S/A 級馬:核心邏輯 ≥ 80 字
> - B 級馬:核心邏輯 ≥ 60 字
> - C 級馬:核心邏輯 ≥ 50 字
> - D 級馬:核心邏輯 ≥ 40 字(必須用數據解釋點解差)
>
> **4. 自檢觸發器:** 若你寫完核心邏輯後發現少於 40 字或者用咗書面語 → 你已違規 → 立即重寫。

---

**📋 Batch 執行循環(每 Batch 必須遵守 — P23):**

```
FOR EACH batch:
  1. 📝 WRITE (Safe-Writer P33-WLTM) — Python Heredoc One-Step: cat PYEOF > .agents.agents/tmp/batch_N.py → python3 .agents.agents/tmp/batch_N.py → safe_file_writer.py --mode append（≤ BATCH_SIZE 匹馬）
  2. 🔍 SCAN — view_file 驗證 11 section headers（⭐⚗️🐴🔬⚡📋🔗🧭⚠️📊💡）
  3. 🐍 VALIDATE — 執行 Python 驗證:
     python scripts/validate_analysis.py "[ANALYSIS_PATH]"
     ❌ FAILED → 重做該 batch | ✅ PASSED → 繼續
  4. ✅ QA — 調用 AU Batch QA Agent
  5. 🔒 TOKEN — 寫入 BATCH_QA_RECEIPT
  6. 📋 REPORT — 回覆用戶 QA 結果
  7. ☑️ TASK — task.md 標記 [x]
  8. ➡️ NEXT — 推進(唔好問用戶「是否繼續」)
END FOR
```

**🔒 QA Receipt Token:** `🔒 BATCH_QA_RECEIPT: PASSED | Batch [N] | Race [X] | SCAN: [N]/[N]`

---

### Step 4b: 🚨 強制合規檢查

> [!IMPORTANT]
> **不可跳過。** 全場完畢 → 調用合規 Agent + 執行 `validate_analysis.py`。

**Python 驗證(強制):**
```bash
python3 .agents/scripts/completion_gate_v2.py "[ANALYSIS_PATH]" --domain au
python3 .agents/skills/au_racing/../au_wong_choi/scripts/verify_math.py "[ANALYSIS_PATH]" --fix
```

**合規硬性指標(任一不合格 = FAILED):**
- (a) 每匹馬 ≥250 字 | (b) 所有欄位標題存在 | (c) 字數 min÷max ≥0.35 | (d) CSV 存在

**合規結果回覆(不可省略):**
```
🔒 Race [X] 合規
- ✅/❌ | 馬匹 [N]/[N] | 批次 [N]/[N]
- validate_analysis.py: ✅/❌
- 問題:[NONE / 列表]
```

**🔒 Compliance Receipt:** `🔒 COMPLIANCE_RECEIPT: PASSED | Race [X] | [timestamp]`

**🔴 合規連續 FAILED 2 次 — AG Kit Systematic Debugging 完整閉環:**
當 `validate_analysis.py` 或合規 Agent 連續 2 次返回 FAILED,啟動 3-Phase 自動修復流程:

**Phase 1: 診斷 (Diagnose)**
讀取 `.agent/skills/systematic-debugging/SKILL.md`,執行 4-Phase 除錯:
- **Reproduce:** `view_file` 被標記 FAILED 嘅 Analysis.md 段落,確認問題範圍
- **Isolate:** 係全場結構問題?個別 Batch?字數不足?欄位缺失?
- **Understand:** 5-Whys → 根因(Token 壓力?骨架跳過?排位表數據缺失?)
- **Fix 方向:** 確定具體修正對策(見 Phase 2 表格)
- 根因記錄到 `_session_issues.md`:`DEBUG-ROOT-CAUSE: [描述]`

**Phase 2: 修正 (Fix)**
根據 Phase 1 診斷出嘅根因類別,自動執行對應修正行動:

| 根因類別 | 修正行動 |
|---------|----------|
| Token 壓力 / 字數不足 | 降 BATCH_SIZE 至 2 → 指示 Analyst 重寫受影響 Batch |
| 欄位缺失 / 骨架跳過 | 重新讀取 `session_start_checklist.md` 骨架 → 指示 Analyst 補回缺失欄位 |
| 排位表數據缺失 | 回退到 Step 2 → 重新提取受影響場次數據 → 再交 Analyst |
| 重複數據 (QG-CHECK) | 清除受影響 Batch → 指示 Analyst 逐匹獨立數據重寫 |
| 結構不合規 (格式) | 提供正確骨架範本 → 指示 Analyst 按範本重寫 |

**Phase 3: 重做 (Redo)**
1. **只重做受影響嘅 Batch**(唔洗重做全場)
2. 重做時強制附帶根因修正參數:
   `🔧 REDO_CONTEXT: [根因] | FIX_APPLIED: [修正行動] | AFFECTED_BATCHES: [N,M]`
3. 重做完成後重新執行 `validate_analysis.py`
4. ✅ PASSED → 發出 Compliance Receipt → 恢復正常流程推進下一場

> [!CAUTION]
> **🛑 Loop 防護(硬性熔斷):** Phase 3 重做後若仍然 FAILED → **立即停止所有自動修復**。
> 通知用戶:「⚠️ 自動修復失敗。根因:[X],已嘗試修正:[Y],重做後仍不合規。請手動介入。」
> **嚴禁**再次進入 Phase 1-3 循環。整個 Debug 閉環最多只執行 **1 次**。

---

> [!CAUTION]
> **🚨 TOP4_FORMAT_ENFORCEMENT(P25 — P31 更新 Top 3→4):**
> 1. **Top 4 必須用 `🥇🥈🥉🏅` + bullet list 格式。** 嚴禁 Markdown 表格。
> 2. **每個選項 4 必填欄位:** 馬號馬名 / 評級✅數 / 核心理據(LLM 自由發揮)/ 最大風險
> 3. **完整結構:** Part 3 Verdict(含 Top 4 + 信心度 + 步速逆轉 + 緊急煞車 + Exotic Box)→ Part 4 盲區(含冷門馬總計)→ CSV
> 4. **排名 = Absolute Ranking Mandate。** 評級高排前,同級比 ✅ 數。

**CSV 覆蓋權**:Wong Choi 擁有最終 Top 4 排序權。
**存檔**:`{TARGET_DIR}/[Date]_[Racecourse]_Race_[N]_Analysis.md`
## Step 4.5: 自檢總結 (Self-Improvement Review)

當所有場次分析完畢(或用戶決定停止),喺生成 Excel 之前,讀取 `_session_issues.md` 全部內容。

> **注意:** 大部分自我改善機制已集中到 `AU Compliance Agent` 嘅自我改善引擎(Step 4)。
> Wong Choi 單繼續執行以下簡化版總結。

**若有任何累積嘅問題(包括合規 Agent 發現嘅 DISCOVERY / CALIBRATION):**
→ 呈現分類匯總:
  - CRITICAL/MINOR 問題清單(附場次、問題碼、簡述)
  - DISCOVERY 發現清單
  - CALIBRATION 建議清單
→ 問用戶:「以上為本次分析嘅累積問題與發現,是否需要:
  A) 逐一處理(指定要修正嘅項目)
  B) 全部記錄到改進日誌供日後覆盤參考
  C) 略過,直接生成 Excel」

**若無任何問題:**
→ 「全部場次分析完成,未發現需要改善嘅問題。」直接進入 Step 5。

## Step 5: 產製 Excel 總結表 (Report Generation)
當所有指定場次分析完畢(或用戶決定停止),你必須透過 Python 腳本生成一份 Excel 總結表,匯總所有已完成場次嘅 Top 4 精選。

```bash
python .agents/skills/au_racing/../au_wong_choi/scripts/generate_reports.py "[TARGET_DIR 絕對路徑]"
```

此腳本會讀取所有 Analysis.md 中嘅 `csv` Top 4 數據,寫入 `Top4_Summary.xlsx`。

> ⚠️ **失敗處理**:見底部「統一失敗處理協議」。觸發條件:腳本執行失敗。

## Step 6: 最終匯報 (Final Briefing)
向用戶匯報所有場次的 Top 4 精選總覽(簡表形式),並提供所有輸出檔案的絕對路徑。

**輸出檔案清單**(只有以下 3 類):
1. 📄 Racecard + Formguide .md 檔案(由 AU Race Extractor 提取)
2. 📝 每場獨立嘅 Analysis.md
3. 📊 `Top4_Summary.xlsx`(所有場次 Top 4 匯總)

## Step 7: 任務完成 (Task Completion)
將 `_session_issues.md` 嘅 Status 更新為 `COMPLETED`。
通知用戶一切已準備就緒。

## Step 7b: Session Cost Report（可選 — P35 新增）

> **設計理念:** 受 ECC `cost-aware-llm-pipeline` 啟發。追蹤每次分析 session 嘅 token 消耗同成本估算。

完成 Step 7 後，執行 session 成本追蹤：
```bash
python3 .agents/scripts/session_cost_tracker.py "{TARGET_DIR}" --domain au --batch-size {BATCH_SIZE}
```
喺聊天中簡要匯報成本摘要（3 行以內）。此步驟失敗唔影響任何結果。

## Step 8: 數據庫歸檔 (Database Archival — P32 新增)

完成 Step 7 後,使用 MCP 工具將本次分析結果持久化(此步驟為可選但強烈建議):

**8a. SQLite 歸檔(結構化數據 — 用於命中率追蹤):**
使用 SQLite MCP 嘅 `write_query` tool 將每場嘅 Top 4 Verdict 寫入資料庫:
```sql
INSERT INTO au_ratings (date, venue, race_number, horse_number, horse_name, final_grade, verdict_rank, track_condition)
VALUES ('{DATE}', '{VENUE}', {RACE_NUM}, {HORSE_NUM}, '{HORSE_NAME}', '{GRADE}', {RANK}, '{TRACK_CONDITION}');
```
每場 Race 嘅 Top 4 各寫一行。同時寫入 `verdicts` table 作為跨引擎追蹤。

**8b. Knowledge Graph 記憶(語義知識 — 用於跨 Session 學習):**
使用 Memory MCP 嘅 `create_entities` + `create_relations` 將以下關鍵發現寫入長期記憶:
- 場地偏差觀察(例:「2026-04-01 Randwick Turf — Rail +3m, 外欄優勢」)
- 騎練組合新發現
- 天氣過渡影響(例:「Caulfield Good→2後轉 Soft 5 — 前速馬崩潰」)
- Decision Diary 中嘅 DISCOVERY 類目

**8c. 可選 — CSV 匯出至 Google Drive:**
若需要喺其他設備查看歷史數據,使用 `read_query` 匯出為 CSV 後存檔到 TARGET_DIR。

> ⚠️ **失敗處理**:若 MCP 工具不可用,跳過此步驟不影響分析結果。記錄到 `_session_issues.md`。

# Recommended Tools & Assets
- **Tools**: `search_web`, `run_command`, `view_file`, `grep_search` (⚠️ `write_to_file`/`replace_file_content`/`multi_replace_file_content` 已被 P33-WLTM 完全封殺 — 只用 `run_command` + heredoc pipeline)
- **MCP Tools (P32 新增)**:
  - `playwright_navigate` / `playwright_screenshot` — 網頁即時數據抓取(Python 腳本失敗時嘅後備)
  - `read_graph` / `create_entities` / `create_relations` — Knowledge Graph 記憶(場地偏差、跨 session 筆記)
  - `read_query` / `write_query` / `list_tables` — SQLite 數據庫查詢(歷史評級、命中率追蹤)
- **Assets**:
  - `scripts/generate_reports.py`:自動將分析結果轉換成 Excel 格式。
---

# 操作協議(Read-Once — 啟動時載入)
你必須喺 session 開始時讀取 `resources/01_protocols.md`,內含:
- **統一失敗處理協議** — 所有失敗場景嘅處置方式
- **🚨 File Writing Protocol** — 使用 Safe-Writer P33-WLTM Python Heredoc One-Step Pattern — `write_to_file` 工具已完全封殺

# 🚨 終極防死機 / Safe-Writer Protocol (P33-WLTM)

> 遵循 GEMINI.md 之中規定的 `safe_file_writer.py` 進行操作。嚴禁使用 write_to_file。

# 🛑 Pipeline Testing & Agent Execution Boundaries
**CRITICAL PROTOCOL: How to Avoid Automation Shortcuts in the Future**

1. **停止測試捷徑 (No Automated Shortcuts for LLM Analysis):** 
   身為 LLM 分析引擎，你嘅職責就是根據 `extract_formguide_data.py` (或其他抽取器) 抽出嚟嘅客觀數據，做「深度法醫分析」同判定 Grade。在日後執行任何 Pipeline 測試或端到端執行時，**絕對不能用 Python script 去模擬生成內容或塞字過關**。必須老老實實當自己做緊真飛分析一樣，用 Markdown 直接把高質素、具深度的優質內容完整寫出嚟。
2. **遵守系統角色 (Respect System Roles):** 
   分工極為明確。Python 腳本負責「砌骨架」同做「算術題」（例如抽數、排版、計算 Matrix 分數），而你 (LLM) 負責「入血肉」（撰寫戰術節點、寬恕檔案、段速法醫及風險評估）。**任何企圖繞過血肉生成嘅舉動都係嚴重違反 Protocol 嘅行為。**

