
你必須在 `.agents` 資料夾**外部**建立一個絕對路徑資料夾,格式為 `[YYYY-MM-DD]_[Racecourse] (Kelvin)`。
路徑會自動偵測平台:
- macOS: `/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-03-04_HappyValley (Kelvin)`
- Windows: `g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-03-04_HappyValley (Kelvin)`

**CRITICAL**: 你從此刻起必須強制將接下來的所有輸出(原始資料、分析結果與 Excel 報表),全部儲存於 `TARGET_DIR` 內。

**Session Recovery 檢查**:初始化時,你必須檢查 `TARGET_DIR` 內是否已存在 `*_Analysis.md` 檔案(亦檢查 `*_Analysis.txt` 向後兼容)。若存在,代表之前嘅 session 已完成部分場次。你應:
1. 列出已完成嘅場次(例如 Race 1-5 已有 Analysis.md)
2. 讀取 `_session_state.md`(如存在)恢復品質基線同進度狀態
3. **🚨 強制重讀 Output Templates(P26 — Session Recovery Resource Reload):**
   - 無論係恢復邊一場,**必須**重讀 `hkjc_horse_analyst/resources/08_templates_core.md`
   - 此步驟防止 LLM 喺新 session 中因記憶漂移而違反格式規範(歷史教訓:2026-03-27 Race 1 Session Recovery 時跳過 template 讀取,導致 Top 4 使用咗 Markdown 表格而非 🥇🥈🥉🏅 清單格式,違反 P25)
   - 若正在恢復某場賽事嘅中途批次(例如 Race 1 Batch 4),亦需重讀 `08_templates_rules.md` 確認最後一批嘅 Part 3/4 結構
4. 通知用戶:「偵測到已完成 Race X-Y 嘅分析,是否從 Race Z 繼續?」
5. 若用戶確認,直接跳到未完成嘅場次,避免重複分析。
6. 自動計算剩餘場次,通知用戶:「剩餘 X 場未分析。」

**Issue Log 初始化**:TARGET_DIR 確立後,建立 `{TARGET_DIR}/_session_issues.md`,內容如下:
```
# Session Issue Log
**Date:** {DATE} | **Venue:** {VENUE}
**Status:** IN_PROGRESS
---
```
此檔案將用於記錄整個分析 session 中發現嘅所有問題。

## Step 2: 資料提取 (Data Extraction)
呼叫 `HKJC Race Extractor` 技能。
指示它依照該技能的規則,為**當日所有的場次(Race 1 至 N)**下載「排位表 (Race Card)」與「賽績 (Form Guide)」。

**強制規定(v2 — Per-Race Split):** 每場嘅排位表同賽績必須分場輸出為獨立檔案,並生成 Formguide Index。檔案結構:
```
TARGET_DIR/
├── {MM-DD} Formguide_Index.md   ← 索引檔(先讀此檔!)
├── {MM-DD} Race 1 排位表.md
├── {MM-DD} Race 1 賽績.md
├── {MM-DD} Race 2 排位表.md
├── {MM-DD} Race 2 賽績.md
├── ...
├── 全日出賽馬匹資料 (PDF).pdf
└── _Race_Day_Briefing.md
```

**⚡ 高速提取策略 (Turbo Extraction Strategy):**
當分場檔案已存在時,若需分析單一場次,**嚴禁**重新呼叫 Playwright 或下載工具。直接 `view_file` 讀取對應場次嘅獨立檔案即可。
確認所有文字檔都正確儲存在 `TARGET_DIR` 內。

**CRITICAL**: 即使用戶只要求分析 Race 1,你仍必須在此步驟一次性提取**全日所有場次**的排位表與賽績,確保所有數據就位後,才可進行任何分析工作。絕不可邊提取邊分析。

> ⚠️ **失敗處理**:若 `HKJC Race Extractor` 執行失敗或輸出不完整,立即停止並通知用戶,絕不繼續分析不完整的數據。

**⚠️ 提取後驗證 (Post-Extraction Validation — 不可跳過):**
提取完成後,你必須執行以下 3 項驗證,**任一項失敗 = 提取失敗,嚴禁繼續**:
1. **檔案命名檢查:** 確認所有輸出檔案嘅日期前綴為正確嘅 `[MM-DD]`(例如 `03-25`),唔係 `00-00`。若為 `00-00` = URL 缺少 `racedate` 參數 = 提取失敗,需要檢查傳入嘅 URL 格式。
2. **PDF 內容檢查:** 確認 `全日出賽馬匹資料 (PDF)` 檔案大小 > 500 bytes,且唔包含 `Error:` 字樣。若檔案只有錯誤訊息 = PDF 提取失敗,需要檢查日期格式是否正確(YYYYMMDD)。
3. **排位表/賽績內容抽查:** 隨機 `view_file` 一個排位表同一個賽績檔案嘅前 5 行,確認有實際賽事數據(例如 `場次:` 或 `馬號:` 欄位),唔係空白或錯誤訊息。

> 📋 **歷史教訓(2026-03-25):** Kelvin 場次提取時 URL 缺少 `racedate` 參數,batch_extract.py 靜默使用 `00-00` 作為日期前綴,all 18 files 命名錯誤。PDF 提取腳本將錯誤訊息寫入 stdout(而非 stderr),導致 40 bytes 嘅錯誤文字被當作 PDF 數據存檔。全程無任何錯誤提示。此驗證步驟為防止同類問題再發生。

**⏸ 提取完成 Checkpoint(強制停頓):**
全日所有場次嘅排位表同賽績提取完成後,你**必須暫停**並向用戶匯報:
```
✅ 全日 Race 1-{TOTAL_RACES} 嘅排位表同賽績已成功提取並合併存檔到 {TARGET_DIR}。
📂 檔案清單:[列出所有已提取檔案]
✅ 提取後驗證通過:命名正確 / PDF 有效 / 內容已抽查
是否繼續進行情報搜集同分析?(若你想用另一個 session 進行分析,可以喺此停止。)
```
**嚴禁跳過此 checkpoint 直接進入 Step 2.5。** 用戶可能使用不同嘅 AI 引擎分別處理提取同分析。

## Step 2.5: Race Day Briefing(賽日總覽 — P30)

> **設計理念:** 提取完成後、情報搜集前,提供全日賽事「鳥瞰圖」。令用戶同 AI 都清楚今日工作量、Session 分割計劃、同潛在風險,避免盲目開始分析。

**A. 解析排位表(Smart Slice Protocol):**
1. **先讀 Index 檔案**:`view_file` 讀取 `{TARGET_DIR}/{MM-DD} Formguide_Index.md`(~2KB)
2. Index 包含每場嘅距離、班級、出馬數同 Horse Quick Reference
3. **唔好一次讀晒所有場次嘅賽績** — 只用 Index + 每場 Racecard 做 Briefing

從 Index + 每場嘅排位表 `.md` 中提取**每場**嘅:
- 距離 (Distance)
- 班級 (Class) — 例如 C1/C2/C3/C4/C5/G1/G2/G3/HCP
- 賽道 (Track) — 草地 / 全天候跑道
- 出賽馬匹數(已扣除退出 Scratchings)
- 首出馬數量(排位表中冇近績紀錄嘅馬匹)

**B. 生成 Race Day Briefing(格式必須完全遵守):**
```
📋 Race Day Briefing
Date: {DATE} | Venue: {VENUE} | Total Races: {TOTAL_RACES}
BATCH_SIZE: {BATCH_SIZE}(由環境掃描決定)

| 場次 | 距離    | 班級 | 賽道   | 出馬 | 首出 | 預計批次 | Session |
|------|---------|------|--------|------|------|---------|---------|
| R1   | 1200m   | C4   | 草地   | 14   | 0    | 5+V     | S1      |
| R2   | 1400m   | C3   | 草地   | 12   | 1    | 4+V     | S1      |
| R3   | 1600m   | C2   | 草地   | 10   | 0    | 4+V     | S1      |
| R4   | 1000m   | C4   | 草地   | 14   | 2    | 5+V     | S1      |
| R5   | 2000m   | C1   | 草地   | 8    | 0    | 3+V     | S2      |
| ...  | ...     | ...  | ...    | ...  | ...  | ...     | ...     |

📊 資源預估:
- 總出賽馬匹:{TOTAL_HORSES}
- 總批次(含 Verdict):{TOTAL_BATCHES}
- 預計 Session 分割:{NUM_SESSIONS} 個 session
  → S1: Race 1-4 | S2: Race 5-8 | S3: Race 9-{TOTAL_RACES}
- 每場預計時間:~20-30 分鐘

⚠️ 潛在風險 Flag:
- 🔴 大場(≥12匹):[列出場次,例如 R1(14匹), R4(14匹)]
- 🟡 首出馬場次:[列出場次,例如 R2(1匹首出), R4(2匹首出)]
- 🔵 長途賽(≥2000m):[列出場次]
- 🟠 天氣/場地:[待 Step 3 確認]

🎯 請確認分析範圍:
A) 全日分析(Race 1-{TOTAL_RACES})
B) 指定場次(例如 R1, R3, R5)
C) 先做前半日(Race 1-{TOTAL_RACES/2})
```

**C. 計算邏輯:**
- `預計批次` = ceil(出馬數 / BATCH_SIZE) + 1 (Verdict batch),顯示為 `N+V`
- `Session 分割` = 每 4 場為 1 個 session(S1: R1-4, S2: R5-8, S3: R9+)
- `大場 Flag` = 出馬數 ≥ 12 嘅場次
- `首出馬 Flag` = 首出馬 ≥ 1 嘅場次
- `長途 Flag` = 距離 ≥ 2000m 嘅場次

**D. 寫入持久化檔案:**
將以上 Briefing 寫入 `{TARGET_DIR}/_Race_Day_Briefing.md`。後續 Session Recovery 時可直接讀取此檔案,無需重新解析排位表。

**E. 等待用戶確認分析範圍後,進入 Step 3。**

> [!TIP]
> **Session Recovery 時嘅行為:** 若 `_Race_Day_Briefing.md` 已存在,直接讀取並顯示(標記已完成場次),無需重新解析。

## Step 3: Meeting-Level 情報搜集 (Intelligence Pass) [一次性]
在開始任何 Analyst 分析之前,你必須**一次性完成**以下 meeting-level 情報搜集工作:

**3a. 場地狀態獲取:** 向用戶詢問或自動搜索當日的「場地狀態(例如:好地 Good, 好至黏地 Good-to-Yielding)」。

**3b. 公共情報搜索:** 使用 `search_web` 工具,一次性搜索以下當日賽事公共數據:
- 今日官方場地狀態 / 跑道偏差 (Track Bias)
- 今日欄位 (Rail Position)
- 今日天氣與降雨情況
- 傷患與配備變動報告 (Gear Changes)

將所有搜索結果整理為**固定情報包 (Intelligence Package)**,格式如下:
```
📋 Meeting Intelligence Package
- 場地狀態 (Going): [X]
- 跑道偏差 (Track Bias): [X]
- 欄位 (Rail Position): [X]
- 天氣: [X]
- 傷患/配備變動 (Gear Changes): [X]
```

此情報包將傳遞給所有後續的 Analyst 調用,**避免每場重複搜索**。Analyst 僅需按需搜索馬匹專屬的騎練組合數據。

**寫入情報包到文件(Pattern 13 — 跨 Session 持久化):**
將以上情報包寫入 `{TARGET_DIR}/_Meeting_Intelligence_Package.md`,格式如下:
```markdown
# Meeting Intelligence Package
**Date:** {DATE} | **Venue:** {VENUE}
**Generated:** {timestamp}

## 場地狀態 (Going)
{data}

## 跑道偏差 (Track Bias)
{data}

## 欄位 (Rail Position)
{data}

## 天氣 (Weather)
{data}

## 傷患/配備變動 (Gear Changes)
{data}
```
此文件可供後續 session 直接讀取,無需重新搜索。若任何數據搜索失敗 3 次,標記為 `[搜索失敗 — 需人手補充]`。

## Step 3.5: 歷史交叉驗證 (Intelligence-First Tier 2 — P35 新增)

> **設計理念:** 受 ECC `search-first` 啟發。在即時情報搜集後，加入歷史數據交叉驗證。
> 完整 checklist 見 `shared_instincts/intelligence_checklist.md`。
> **此步驟依賴 MCP。若 MCP 不可用 → 自動跳過，唔影響分析。**

**若 MCP Servers 可用（Step E5 檢查通過），執行以下 Tier 2 驗證：**

1. **場地偏差歷史：** `read_graph` 查詢 `{VENUE}_*_bias` entities
2. **同 Going 命中率：** `read_query` 查詢 `SELECT * FROM hkjc_ratings WHERE venue='{VENUE}' AND track_condition LIKE '%{GOING}%'`
3. **練馬師歷史：** `search_nodes` 查詢 `trainer_{NAME}_{VENUE}`
4. **AWT 特殊檢查（若為全天候跑道）：** `read_query` 查詢 AWT 歷史數據

**將結果加入 `_Meeting_Intelligence_Package.md` 嘅新 section：**
```markdown
## 歷史場地 Pattern（Tier 2 — MCP 交叉驗證）
- 過往 3 次場地偏差: [{VENUE} - 偏差記錄]
- 同 Going 命中率: [{GOING} 歷史 X%]
- 練馬師 Spotlight: [{TRAINER} 喺 {VENUE} 近期勝率 Y%]
- AWT 檢查: [適用 / 不適用]
- **Intelligence Confidence: [🟢 HIGH / 🟡 MEDIUM / 🔴 LOW]**
```

**MCP 不可用時：** 跳過 Tier 2，Intelligence Confidence 設為 🟡 MEDIUM。分析流程完全唔受影響。
## Step 3.7: 完整賽績檔案注入 (Facts.md Injection — V2 新增)

> **設計理念:** 合併兩個數據源（Formguide + HKJC 馬匹頁面 SSR HTML），生成包含所有 Python 計算維度嘅「完整賽績檔案」。LLM 分析時引用此檔案，嚴禁直接從 Formguide 重新計算。

**A. 提取 Horse ID（從排位表/賽果頁面）:**
每場賽事嘅 Horse ID 可從以下來源取得：
1. **排位表 PDF**（全日出賽馬匹資料）→ Brand Number（例如 K416）
2. **HKJC 排位表網頁 HTML** → 完整 horseid（例如 `HK_2024_K416`）
3. **HKJC 賽果頁面 HTML** → 完整 horseid（SSR HTML，可用 requests 提取）

**B. 執行 Python 注入腳本:**
```bash
cd {TARGET_DIR}
python3 ../.agents/scripts/inject_hkjc_fact_anchors.py \
    "{MM-DD} Race N 賽績.md" \
    --horse-ids "HK_2024_K416,HK_2024_K035,..." \
    --venue {ST|HV} --distance {DIST} --class {CLASS} \
    --output "{MM-DD} Race N Facts.md"
# ✅ 賽績線已默認啟用（有 --horse-ids 自動查冊）
# ℹ️ 若需停用: 加 --no-form-lines
```

**C. Facts.md 包含嘅數據維度（全部由 Python 計算）：**

| 維度 | 來源 | 說明 |
|:---|:---|:---|
| 📋 Markdown Table | 合併 | Formguide（能量/L400/XW消耗）+ 馬匹頁面（頭馬距離/體重/配備/走位/時間） |
| 📊 段速趨勢 | Formguide | L400 + 能量趨勢 |
| 🔧 引擎距離 | Formguide | 引擎分類 + 最佳距離 |
| 📏 頭馬距離趨勢 | 🆕 馬匹頁面 | 收窄/擴大/波動 |
| 📊 體重趨勢 | 🆕 馬匹頁面 | 增磅/減磅/穩定/急劇 |
| 🔧 配備變動 | 🆕 馬匹頁面 | 初戴/除去/SIP-HV2 觸發 |
| 📈 評分變動 | 🆕 馬匹頁面 | 升班/降班/穩定 |
| 🏃 走位 PI | 🆕 馬匹頁面 | 用實際位次計算 PI 趨勢 |
| 🔗 賽績線 | 🆕 自動查冊 | Top-3 對手追蹤 + 三級強度分類（見下表） |

**賽績線強度等級（三級制）:**
| 等級 | 標籤 | 判定標準 |
|:---|:---|:---|
| 超強組 | ✅✅ | 對手勝 ≥2 次，或勝 ≥1 次且升班後仍能贏 |
| 強組 | ✅ | 對手後續有 1 次勝出 |
| 中組 | ⚠️ | 對手 Place Rate ≥ 40% 但未贏 |
| 弱組 | ❌ | 對手 Place Rate < 40% 且未贏 |

**D. 嚴禁規則（最高優先級）：**
- ⛔ LLM **嚴禁**自行計算已由 Python 預填嘅數值（L400/走位消耗/體重趨勢/配備變動）
- ⛔ LLM **嚴禁**直接讀取 Formguide 重建賽績表格 — 必須引用 Facts.md
- ✅ LLM 只需**解讀、判斷、評級** — 數學全部由 Python 處理

**E. Horse ID 暫缺時嘅降級模式：**
若無法提供 `--horse-ids`，腳本仍可運行 — 輸出 Formguide 數據但不含馬匹頁面維度。

## 問題嚴重程度定義 (Issue Severity)

| 級別 | 代碼 | 定義 | 處理方式 |
|------|------|------|----------|
| **CRITICAL** | LOGIC-001, DATA-002, MODEL-002, MODEL-004 | 影響分析正確性嘅重大問題 | 累積到賽間報告,建議修正 |
| **MINOR** | LOGIC-003, LOGIC-004, LOGIC-006, MODEL-003, MODEL-005 | 品質瑕疵但不影響核心結論 | 記錄到 issue log,全場完成後統一處理 |
| **DISCOVERY** | DISC-001 | 框架未涵蓋嘅新模式或異常 | 記錄供日後改進參考 |

## Step 4: 戰略分析 (Strategy Analysis)

### 🤖 Orchestrator 協調增強(引用 AG Kit orchestrator 模式)

**A. Agent 邊界執行 (Agent Boundary Enforcement):**
Wong Choi 調度嘅子 Agent 必須嚴格遵守各自嘅職責邊界:

| Agent | CAN Do | CANNOT Do |
|-------|--------|-----------|
| HKJC Race Extractor | 數據爬取、格式化 | ❌ 任何分析判斷 |
| HKJC Horse Analyst | 馬匹分析、評級 | ❌ 數據提取、Excel 生成 |
| HKJC Batch QA | 結構驗證、字數檢查 | ❌ 修改分析內容 |
| HKJC Compliance | 全場合規審查 | ❌ 修改分析內容 |

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
- 每次只分析 **1 場賽事**。
- **批次自動推進但獨立寫入:** 分析期間嚴禁向用戶詢問「是否繼續下一批」。但「自動推進」≠「合併寫入」——每個 Batch 必須為獨立嘅 tool call。

**📖 Smart Slice Protocol（Per-Race Data Loading — V2 更新）：**
分析每場賽事時，**優先讀取 Facts.md**。只有在 Facts.md 不存在時才讀取原始賽績：
```
分析 Race N 前:
  1. view_file → {MM-DD} Race N 排位表.md（確認出馬數同馬匹名）
  2. view_file → {MM-DD} Race N Facts.md（✅ 優先讀取 — 含 Python 計算維度）
     ⚠️ 若 Facts.md 不存在 → 降級讀取 {MM-DD} Race N 賽績.md
  3. 計算 BATCH_PLAN
  4. 開始 Batch Loop

⛔ 嚴禁：一次過讀取多場嘅 Facts/賽績
⛔ 嚴禁：讀取上一場/下一場嘅數據（除非做跨場對手分析）
⛔ 嚴禁：直接從 Formguide 重新計算 Facts.md 已提供嘅數值
✅ 每場分析完成後，該場數據應從 context 中自然淡出
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
> TOTAL_HORSES = [從排位表數出嘅出賽馬匹數(已扣除退出)]
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
>   - [ ] Race N 分析(M 匹馬 × K 批次 + VERDICT)
>   - [ ] Batch 1: #1, #2, #3
>   - [ ] Batch 2: #4, #5, #6
>   - [ ] ...
>   - [ ] Batch K: #X, #Y(最後一批馬匹)
>   - [ ] VERDICT BATCH: Top 4 + 盲區 + CSV(獨立 tool call)
>   - [ ] Compliance Check
> ```
> 此做法令 LLM 在執行時有明確嘅 checklist 逐項打 ✅,減少跳批或合併批次嘅機會。
>
> **Step A3 — Gemini Engine Adaptation (P31 — 2026-03-30 新增):**
> 若使用 Gemini 引擎,必須在每個 Batch 寫入前,先執行 `thought` 檢查當前 context 剩餘空間。若空間不足,強制觸發 `CONTEXT_WINDOW_RELIEF` 並將當前 Batch 拆分為更小單位。
>
> **Step B — 逐批執行以下循環(不可跳過任何步驟):**
>
> **[Per-Batch Skeletal JIT Injection] (強制防呆機制 — 學自 AU Wong Choi P36)**
> 在每次執行獨立 tool call 寫入 Batch 的分析前,你**必須強制**使用 `view_file` 讀取 `hkjc_wong_choi/resources/horse_analysis_skeleton.md`。
> 嚴禁憑記憶默寫結構。你必須將該骨架原封不動地複製並向下填充,確保所有欄位一個不漏!
>
> ```
> FOR EACH batch IN BATCH_PLAN:
>   0. 🗺️ PART 1 (僅 Batch 1) — 若為本場第一個 batch,**必須先寫入 [第一部分] 🗺️ 戰場全景:**
>      - `view_file` 讀取 `resources/session_start_checklist.md` 嘅戰場全景骨架
>      - 填充賽事格局表 + Speed Map + 步速瀑布推演
>      - **⚠️ 嚴禁跳過 Part 1 直接寫馬匹分析！**
>   1. 📝 WRITE — 用 Safe-Writer P19v6 Python Heredoc One-Step Pattern:
>      cat PYEOF > /tmp/batch_N.py → python3 /tmp/batch_N.py → safe_file_writer.py
>      B1 用 `--mode overwrite`，B2+ 用 `--mode append`（最多 BATCH_SIZE 匹馬）
>   2. 🔍 SCAN — view_file 驗證 section headers 存在
>   3. ✅ QA — 執行 Batch QA Agent
>   4. 🔒 TOKEN — 寫入 BATCH_QA_RECEIPT 到 Analysis.md
>   5. 📋 REPORT — 僅在整場賽事(所有 Batches + The Verdict)全數寫完後,才向用戶匯報。
>   6. ☑️ TASK — 在 task.md 中將該批次標記為 [x]
>   7. ➡️ NEXT — 自動進入下一個 batch,不需停機等待用戶確認。
> END FOR
> ```
>
> **⛔ COMPLETION_GATE(強制 — 回覆用戶前必須通過 — P31):**
> 喺 batch 循環結束後、通知用戶之前,你必須強制執行以下 Python 驗證:
> 🚨 **你完成分析後，必須強制自己 run `python3 .agents/scripts/completion_gate_v2.py <你正在分析的檔案路徑> --domain hkjc` 進行檢驗。不過關不准完成任務！**
> 如果檢驗失敗 (出現 `❌ [FAILED]`)，你已違規 → 立即根據報告內容，自行修正錯誤的段落 (例如補回標籤、擴充字數或補回漏寫章節) 並重新執行 validator 直到 `✅ [PASSED]` 為止！
>
> 🔢 **數學驗證 + 自動修正（verify_math.py --fix）：**
> Completion Gate 通過後，強制執行：
> ```
> python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/verify_math.py <分析檔案路徑> --fix
> ```
> 此工具會自動：(1) 重數 ✅/➖/❌ 校驗矩陣算術、(2) 修正 base grade drift、(3) 修正 final grade drift（>1級）、(4) 同步 CSV grade、(5) 偵測殘留 `[FILL]`/`{{LLM_FILL}}` 標記。
> 若有修正，工具會自動覆寫檔案並重新驗證。**FILL 殘留 = 強制 FAIL，必須補填。**
> ```
> 
> 🔄 **[DEFAULT AUTONOMOUS COMMAND (預設全自動執行模式)]**
> 從今開始,當用戶要求「分析某場賽事」(例如: "start race 4" 或 "analyse race") 時,你**必須預設啟動全自動連續執行模式 (Autonomous Mode)**!
> 從 Batch 1 開始一直到最後一個 Batch,你必須在同一個回合內,連續且不間斷地發出多個寫入工具呼叫,自行將整場賽事(全量馬匹 + The Verdict Top 4 列表及盲區)一氣呵成地寫完!只要尚未完成 The Verdict,就絕對不能輸出短暫的回應文本給用戶而造成停機等待。**不需在 Batch 1 結束後向用戶請示,必須在整場賽事完全分析完畢後,才一次過向用戶匯報!**
> 
> 🔄 **[AUTONOMOUS LOOP OVERRIDE (無間斷連續執行指令)]**
> 若用戶明確下達「proceed batch by batch until you finish」或類似連續執行指令,你**絕對禁止在每個 Batch 寫完後停下來回覆用戶並等待確認**!
> 你必須在同一個回合內,連續且不間斷地發出多個 `run_command` heredoc tool calls,自行將整場賽事(所有 Batches + The Verdict)一氣呵成地寫完!只要還沒寫到 The Verdict,就絕對不能輸出回應文本給用戶造成停機等待。**必須一口氣自動完成全場賽事分析後,才一次過向用戶報告全量完成!**
> 
> **⛔ 硬性攔截器:** 若你發現自己正在一個 tool call 中寫入超過 BATCH_SIZE 匹馬 → **立即停止生成**,刪除多餘內容,拆分為獨立 tool calls。
> **⛔ 反模式偵測:** 若你嘅 tool call 中同時出現 `Batch 1` 和 `Batch 2` 嘅馬匹 → 你已違反此規則 → 立即停止。
- **每場分析完畢並儲存後,必須先執行 Step 4b 合規檢查,然後才執行「賽間推進協議」。**

> [!CAUTION]
> **強制執行順序(不可變更):** 全場馬匹分析完畢 → Step 4b 合規檢查 → 合規通過 → 賽間推進協議。**嚴禁跳過合規檢查。**

**🚨 PRE-NOTIFICATION SELF-CHECK(每次通知用戶前必須執行):**
在你準備向用戶匯報任何場次完成結果**之前**,你必須問自己以下問題:
```
[SELF-CHECK] Race [X] 完成 — 合規檢查有冇執行?
→ 若冇 → 立即停止,回退執行 Step 4b 合規檢查
→ 若有 → 確認 Analysis.md 末尾有「✅ COMPLIANCE CHECK PASSED」或「❌ COMPLIANCE CHECK FAILED」標記
→ 若標記唔存在 → 合規檢查未完成,立即回退執行
```
**此自檢為強制性。若發現自己正在跳過此自檢 → 代表你已出錯,立即回退。**

### 逐場手動推進協議 (P19v2 — 2026-03-25)

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
@hkjc wong choi, 繼續分析 {VENUE} {DATE} Race 5+ for {ANALYST_NAME}

Race 1-4 已完成,分析檔案在:
{ANALYSIS_FOLDER_PATH}

Racecard: {RACECARD_PATH}
Formguide: {FORMGUIDE_PATH}

場地:{TRACK_CONDITION}, {WEATHER}
BATCH_SIZE: {BATCH_SIZE}(由環境掃描決定)
P19v2 逐場手動推進協議 — 每場完成後等確認
每匹馬完整 5-block × 13-subfield (11-field HKJC) 分析
Verdict 必須獨立 tool call 寫入
---
```
→ 變數填充規則:
  - `{VENUE}` = 今場馬場名(如 Sha Tin / Happy Valley)
  - `{DATE}` = 賽事日期(如 2026-03-25)
  - `{ANALYST_NAME}` = 當前操作員名稱(如 Kelvin / Heison)
  - `{ANALYSIS_FOLDER_PATH}` = 分析檔案資料夾相對路徑
  - `{RACECARD_PATH}` = Racecard 檔案相對路徑
  - `{FORMGUIDE_PATH}` = Formguide 檔案相對路徑
  - `{TRACK_CONDITION}` = 場地狀態(如 Good / Yielding / Good To Firm)
  - `{WEATHER}` = 天氣(如 晴天 25°C / 有雨 20°C)
  - `{BATCH_SIZE}` = 當前 session 使用嘅 BATCH_SIZE(2 或 3)
→ 若用戶堅持繼續 → 允許但喺 Analysis.md 加入 `⚠️ CONTEXT_PRESSURE_WARNING` 標記

> [!CAUTION]
> **🚨 MUST_OUTPUT_HANDOFF — 強制輸出交接指令(P29 — 2026-03-29 新增):**
>
> **歷史教訓:** Handoff prompt 有時生成有時唔生成,用戶需要人手拼接指令。
>
> **強制規定(Priority 0):**
> 1. **Race 4 合規通過後,handoff prompt 係你嘅最後一個輸出。** 唔可以喺 handoff 之前停止。
> 2. **所有 `{VARIABLE}` 必須被實際值替換。** 嚴禁輸出未填充嘅 `{VENUE}` 等佔位符。
> 3. **Handoff prompt 必須喺 ``` 代碼區塊內**,方便用戶一鍵複製。
> 4. **自檢觸發器:** 若你完成 Race 4 合規但冇輸出 handoff prompt → 你已違規 → 立即補上。
> 5. **Context Pressure handoff 亦適用此規則** — 任何觸發 session 切割嘅情況都必須輸出完整 handoff prompt。

**🔶 任何時候感覺到 Context Pressure(回應變慢 / 開始壓縮 / 忘記格式):**
→ 立即更新 `_session_state.md`(確保所有進度已記錄)
→ 通知用戶並**輸出完整 handoff prompt**:
```
⚠️ 偵測到 context window 壓力。建議開新 chat 繼續。

📋 請複製以下指令到新 chat:
---
@hkjc wong choi, 繼續分析 {VENUE} {DATE} Race {NEXT_RACE}+ for {ANALYST_NAME}

已完成場次:Race 1-{LAST_COMPLETED_RACE}
分析檔案在:{ANALYSIS_FOLDER_PATH}

Racecard: {RACECARD_PATH}
Formguide: {FORMGUIDE_PATH}

場地:{TRACK_CONDITION}, {WEATHER}
BATCH_SIZE: {BATCH_SIZE}
P19v2 逐場手動推進協議 — 每場完成後等確認
每匹馬完整 5-block × 13-subfield (11-field HKJC) 分析
Verdict 必須獨立 tool call 寫入
---
```

**最後一場完成後 → 正常進入 Step 4.5。**

**🧹 CONTEXT_WINDOW_RELIEF v3 — 六層防禦(P18v3 — 2026-03-25 更新):**

> **歷史教訓:** 分析到 Race 3+ 時,已完成批次/場次嘅 Analysis 內容仍留在 context window 中。LLM 注意力被攤薄,導致後期分析質量逐漸下降。Race 1 Batch 1 質量最佳,之後衰退。量化數據:Wong Choi SKILL.md(~10K tokens) + Analyst resources(~40K tokens) + 每場分析(~20K tokens) + Form Guide(~12K tokens) = Race 4 完成後達 ~185K/200K tokens。

**第 1 層 — 禁止回讀(核心):**
1. **每完成一個 Batch 後不再回讀前面輸出。** 每個 Batch 寫入 Analysis.md 並通過 QA 後,後續 Batch 只需 `view_file` 最後 5 行以確定追加位置及 QA Receipt Token,**嚴禁**回讀前面 Batch 嘅完整分析。
2. **完成一場後不再回讀前場輸出。** 嚴禁再次 `view_file` 該場嘅 Analysis.md。
3. **嚴禁「參考前批/前場分析格式」。** 格式標準來自 SKILL.md 和 `08_templates_core.md` / `08_templates_rules.md`,不是前面嘅輸出。

**第 2 層 — Resource 懶加載(Race 2+ 節省 ~25K tokens):**
- **Race 1:** Analyst 正常讀取全部 16 個 resource 檔案
- **Race 2+:** Wong Choi 指示 Analyst **只重讀 3 個核心 resources**:
  - `01_system_context.md`(Anti-Laziness 規則)
  - `08_templates_core.md`（格式模板）
  - 相關場地檔(`10a`/`10b`/`10c`,按今場場地選 1 個)
  - 其餘 resources 已在 Race 1 吸收,唔需要重讀

**第 3 層 — 動態 Batch Size(P28 更新):**
- **ENV_TOKEN_CAPACITY=HIGH:** `BATCH_SIZE: 3`(標準)
- **ENV_TOKEN_CAPACITY=LOW:** `BATCH_SIZE: 2`(安全 fallback)
- **運行中被截斷:** 自動降級為 2 並重做被截斷嘅 batch

**第 4 層 — 提取蒸發標記:**
Form Guide 提取完成後輸出:`📤 EXTRACTION_CONSUMED: Race [N] Form Guide 已提取並傳遞。以上提取數據已不再需要。`

**第 5 層 — 強制 Session 分割:**
Race 4 完成後硬性停止(見上方半自動推進協議)。

**第 6 層 — 跨場數據最小化:**
只保留:Top 4 精選摘要(馬號+馬名+評級,每場 1 行)、品質基線數字、`_session_state.md` + `_session_issues.md` 路徑。

**🗂️ Session State Persistence(_session_state.md — P16):**
Race 1 完成後建立 `{TARGET_DIR}/_session_state.md`:
```
# Session State
- BATCH_BASELINE: [Race 1 平均字數/匹]
- COMPLETED_RACES: [1]
- QUALITY_TREND: Stable
- LAST_RACE_WORDCOUNT: [平均字數]

## Decision Diary [Improvement #1]
### Race N
- Pace Judgement: [e.g. Genuine -> #3 + #7 leaders]
- Key Downgrade/Upgrade: [e.g. #5 SIP triggered -> B+]
- Controversial Decision: [e.g. #8 EEM vs recent form -> B]
- Longshot Alert: [e.g. #11 lightweight + good draw -> C+]

## Cross-Race Intelligence
### Track Bias Observations
- [e.g. Inside draw advantage - R1 top 4 all from barrier 1-4]
### Pace Pattern
- [e.g. Overall pace bias fast - 3 races had leader collapse]
```
每完成一場更新此檔。Session Recovery 時讀取恢復狀態。

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



呼叫 `HKJC Horse Analyst` 分析當場賽事。

**傳遞畀 Analyst 嘅數據包**:
1. 賽事資訊:`[DATE]`、`[VENUE]`、`[Race Number]`
2. **Meeting Intelligence Package**(完整傳遞)
3. **場地路由:** `[TRACK_MODULE: SHA_TIN_TURF / HAPPY_VALLEY / AWT]`
   - 判斷邏輯:VENUE = Happy Valley → `HAPPY_VALLEY` | VENUE = Sha Tin + 草地 → `SHA_TIN_TURF` | VENUE = Sha Tin + 全天候跑道 → `AWT`
4. **活躍名單:** `[ACTIVE_TRAINERS: 練馬師1, 練馬師2, ...]`、`[ACTIVE_JOCKEYS: 騎師1, 騎師2, ...]`
   - 從排位表提取當場嘅練馬師/騎師名單
5. **賽事組成:** `[DEBUT_RUNNERS: N]`(從排位表識別無近績紀錄嘅馬匹數量)、`[IMPORT_RUNNERS: N]`(從排位表識別 PPG/ISG 標記嘅馬匹數量)
6. 強制使用本地 .md 檔案(排位表、賽績、全日出賽馬匹資料),未經准許不可自行上網搜尋已提供嘅公共數據
7. **審核級別:** `[FULL_AUDIT: NO]`(預設值 — 標準分析只需核心自檢。僅在高風險賽事或用戶特別要求時設為 `YES` 以啟用完整擴展審核)
8. **體重趨勢提醒:** Analyst 必須比較排位體重 vs 賽績歷史體重,標記 📈持續增磅 / 📉持續減磅 趨勢(Step 7.5)
9. **近績差馬 Flag:** 連續 ≥3 場第 8 名或以後嘅馬匹,自動標記 `🔍 [近績差 — 深度加審]`,強制逐仗寬恕審查 + 回勇訊號搜索(Step 7.6)
10. **入位常客 + 下行軌跡提醒:** Analyst 必須執行 SIP-HV11(近4仗≥3仗前6但0三甲 → 穩定性降)及 SIP-HV12(近≥3仗連續下滑 → 穩定性降一級)檢查

### Step 4a: 分析執行與批次監督

BATCH_SIZE 由 Pre-Flight Environment Scan 決定(標準=3 / fallback=2)。

> [!CAUTION]
> **🚨 BATCH QUALITY PROTOCOL — 統合品質規則(P17/P21/P24/P28 — Priority 0)**
>
> **A. 批次結構規則:**
> 1. **分批寫入強制性。** 按 BATCH_SIZE 分批,超出 = 違規。
> 2. **每個 Batch = 獨立 file write (P19v6)。** 必須使用 `run_command` + heredoc → safe_file_writer.py 管道。B1 用 `--mode overwrite`，B2+ 用 `--mode append`。**🚫 嚴禁使用 `write_to_file` / `replace_file_content` / `multi_replace_file_content`。** 嚴禁合併 2+ batch 到同一個 tool call。
> 3. **VERDICT BATCH 獨立。** Part 3 + Part 4 + CSV 必須為獨立 tool call,唔可同馬匹分析合併。**寫入 VERDICT 前必須執行 P33 JIT Template Checkpoint(見下方)。**
> 4. **截斷恢復:** 若被 output token limit 截斷 → BATCH_SIZE 降為 2,重做該 batch。
>
> 批次示例(BS=3):7匹 → B1(3)+B2(3)+B3(1)+VERDICT | (BS=2):7匹 → B1(2)+B2(2)+B3(2)+B4(1)+VERDICT
>
> **B. 全欄位零容忍:**
> 1. **每匹馬(含 D 級)必須包含 11 個獨立段落,缺一 = 整批重做:**
>    `📌情境` → `賽績總結` → `近六場走勢`(每場各一行) → `馬匹分析` → `🔬段速法醫`(≥3行) → `⚡EEM能量`(≥3行) → `📋寬恕檔案`(≥2行) → `🔗賽績線` → `📊評級矩陣`(8維度各1行) → `14.2/14.2B/14.3`(3獨立行) → `💡結論`(核心邏輯+優勢+風險) → `⭐最終評級`
> 2. **自檢:** 寫完數 emoji(🔬⚡📋🔗📊💡⭐),少於 7 = 壓縮中 → 補全。
> 3. **D 級馬用數據解釋差在哪。** 嚴禁「(精簡)」。嚴禁 inline 矩陣。
> 4. **首出馬豁免:** 🔬⚡📋 可寫 N/A,標題必須在。
>
> **C. 品質一致性:**
> 1. **字數門檻:** S/A ≥500字 | B ≥350字 | C/D ≥300字
> 2. **品質基線鎖定:** Race 1 B1 = 基線,後續 ≥ 基線 × 70%。
> 3. **禁止預判評級 → 減少深度。** 先完成全部欄位再得出評級。
> 4. **禁用詞語:** `efficiently`/`quickly`/`精簡`/`壓縮`。評級係結果,唔係減少分析嘅原因。
> 5. **Race 2+ 必須傳遞基線字數提醒:** `⚠️ 品質基線提醒:Race 1 平均 [X] 字。維持同深度。完整 11 欄位。`

**📊 CSV_BLOCK_MANDATORY:** VERDICT BATCH 必須包含 CSV Top 4 數據區塊。自檢:搜索 ` ```csv `,缺 → 補上。

> [!CAUTION]
> **🛡️ P33 — VERDICT JIT TEMPLATE CHECKPOINT(2026-04-04 新增 — Priority 0)**
>
> **歷史教訓(根本原因確認):** 2026-04-04 Sha Tin Race 1 Verdict 出現嚴重格式漂移 — 使用咗 numbered list (`1. [首選]`) 取代強制 `🥇🥈🥉🏅` 格式,遺漏 9 個必要組件(跑道形勢/信心指數、Top 2 信心度、步速逆轉保險、緊急煞車、整個第四部分分析盲區、冷門馬總計)。根因:VERDICT BATCH 寫入時冇重讀 template,導致 LLM 從記憶中生成咗錯誤嘅壓縮格式。
>
> **強制規定:**
>
> 1. **寫入 VERDICT BATCH 之前,必須 `view_file` 讀取 `08_templates_rules.md`。** 冇讀 = 禁止寫入 VERDICT。（注意：Python `compute_rating_matrix_hkjc.py` 嘅 `generate_verdict()` 已預填 Part 3+4 骨架，但格式規則以 `08_templates_rules.md` 為準。）
> 2. **VERDICT BATCH 結構自檢清單(寫入後逐項驗證,缺一 = 重做):**
>    - [ ] `#### [第三部分] 最終預測 (The Verdict)` — 正確標題
>    - [ ] 跑道形勢 / 信心指數 / 關鍵變數 — 3 項 header
>    - [ ] `🏆 Top 4 位置精選` — 使用 `🥇🥈🥉🏅` 清單格式(非 numbered list / 非 table)
>    - [ ] 每個選項有 4 個 sub-bullets: 馬號及馬名 / 評級與✅數量 / 核心理據 / 最大風險
>    - [ ] `🎯 Top 2 入三甲信心度` — 含 🟢/🟡/🔴 信心標記
>    - [ ] `🔄 步速逆轉保險` — 含快/慢兩個情境
>    - [ ] `🚨 緊急煞車檢查` — 含 3 個條件判斷
>    - [ ] `#### [第四部分] 分析盲區` — 6 個 sub-sections
>    - [ ] `🐴⚡ 冷門馬總計` — 觸發或「無冷門馬訊號」
>    - [ ] CSV Block — ` ```csv ` 存在
> 3. **呢個 checkpoint 適用於所有場次、所有引擎、即使係 Session Recovery。**

---

**🔍 骨架模板注入(每 Batch 必須 — 學自 AU Wong Choi):**
每個 Batch 開始前,Wong Choi 必須使用 `view_file` 讀取 `resources/horse_analysis_skeleton.md`，將骨架 × BATCH_SIZE 注入到 Analyst prompt 中。LLM 嘅任務從「生成分析」變為「填充骨架」,保證 100% 結構完整性。**核心邏輯/結論部分為 LLM 自由發揮區域。**

> **🗺️ Batch 1 特別規則:** Batch 1 **必須先寫入 [第一部分] 🗺️ 戰場全景**（從 `resources/session_start_checklist.md` 讀取戰場全景骨架模板）。⚠️ 嚴禁跳過 Part 1 直接寫馬匹分析！
>
> **🏆 VERDICT BATCH 特別規則:** 所有馬匹 Batch 完成後，準備寫入 Verdict 前，**必須** `view_file` 重新讀取 `resources/session_start_checklist.md` 嘅 `🏆 Top 4 Verdict 骨架模板`。在未重讀該模板前,嚴禁直接吐出任何 Top 4 結果。

> [!CAUTION]
> **⛔ P36 — ZERO-TOLERANCE ANTI-DRIFT PROTOCOL（學自 AU Wong Choi — Priority 0）**
>
> **歷史教訓:** 喺長時間連續運作時，LLM 會因為 Context Window 衰退而偷懶跳過讀取，憑模糊記憶生成結構不全、字數極度不足嘅 Bullet points。
>
> **強制對策 (三連擊):**
> 1. **JIT 零容忍宣讀 (Zero-Tolerance Template Refresh):** 每次準備生成 Batch 寫檔腳本之前，**無論自認記憶多麼清晰，都必須強制 `view_file` 讀取 `resources/horse_analysis_skeleton.md`。** 無宣讀 = 違規。
> 2. **強制落實「預建骨幹法」 (Skeleton Copy-Paste Enforcement):** 生成 Python Markdown 變量時，**不准逐行寫**。必須先由 Template 完美 Copy 出整個馬匹的骨幹（全套 emoji 標題），死板地貼齊後，才開始將分析內容填入相應位置，保證結構 100% 不丟失。
> 3. **落實 Session 切割 (Hard Session Splits for Context Relief):** 到達 Race 4 結束必須強制截斷並輸出交接指令 (Handoff Prompt)，嚴格執行「換 Chat 重新連線」，避免記憶體超載而出現妥協式偷懶。

> **🐴 馬匹剖析格式嚴規 (P35 — 2026-04-06 新增 — Priority 0):**
> - 馬匹剖析（或同等欄位如「馬匹分析」）**僅為簡潔分類標籤**，每項以 `[標籤]` 格式撰寫，禁止寫成段落或散文。
> - ✅ 正確示範: `- **步態場地:** [未有 Soft 地數據，但血統顯示應能應付]`
> - ✅ 正確示範: `- **引擎距離:** [Type A 短途爆發]`
> - ❌ 錯誤示範: `- **步態場地:** [無]` （禁止用「無」一字帶過）
> - ❌ 錯誤示範: 在馬匹剖析/馬匹分析下寫整段 200+ 字分析文章
> - **深度法醫分析（戰術推演、歷史比較、風險評估、綜合判定）必須全部歸入 `💡 結論 > 核心邏輯` 區域。**
> - **自檢觸發器:** 若你嘅馬匹剖析任何一項超過 30 字 → 你已違規 → 將多餘內容搬去核心邏輯。

---

**📋 Batch 執行循環(每 Batch 必須遵守 — P23):**

```
FOR EACH batch:
  1. 📝 WRITE — 獨立 tool call 寫入(≤ BATCH_SIZE 匹馬)
  2. 🔍 SCAN — view_file 驗證 7 headers(🔬⚡📋🔗📊💡⭐)
  3. 🐍 VALIDATE — 執行 Python 驗證:
     python3 .agents/scripts/completion_gate_v2.py "[ANALYSIS_PATH]" --domain hkjc
     ❌ FAILED → 重做該 batch | ✅ PASSED → 繼續
  4. ✅ QA — 調用 HKJC Batch QA Agent
  5. 🔒 TOKEN — 寫入 BATCH_QA_RECEIPT
  6. 📋 REPORT — 回覆用戶 QA 結果
  7. ☑️ TASK — task.md 標記 [x]
  8. ➡️ NEXT — 推進(唔好問用戶「是否繼續」)
END FOR
```

**Batch QA 回覆格式(必須回覆用戶):**
```
📋 Batch [N] QA | Race [X]
- ✅/❌ | 馬匹:[列表] | 字數:[min]-[max] ([ratio]%)
- validate_analysis.py: ✅/❌
```

**🔒 QA Receipt Token:** `🔒 BATCH_QA_RECEIPT: PASSED | Batch [N] | Race [X] | SCAN: [N]/[N]`
推進前:`view_file` 確認上一批 Receipt 存在。否則 → 停止回退。

---

### Step 4b: 🚨 強制合規檢查

> [!IMPORTANT]
> **不可跳過。** 全場完畢 → 調用 `HKJC Compliance Agent` + 執行 `validate_analysis.py`。

```
🔍 合規指令:
- REPORT_PATH: [Analysis.md 路徑]
- RACE_NUMBER: [N] | TOTAL_HORSES: [M]
- BATCH_BASELINE: [Race 1 B1 平均字數]
```

**Python 驗證(強制):**
```bash
python3 .agents/scripts/completion_gate_v2.py "[ANALYSIS_PATH]" --domain hkjc
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/verify_math.py "[ANALYSIS_PATH]"
```
`❌ FAILED` → 修正再驗證。`✅ PASSED` → 合規通過。

**合規硬性指標(任一不合格 = FAILED):**
- (a) 每匹馬 ≥250 字 | (b) 所有欄位標題存在 | (c) 字數 min÷max ≥0.35 | (d) CSV 存在

**合規結果回覆(不可省略):**
```
🔒 Race [X] 合規
- ✅/❌ | 馬匹 [N]/[N] | 批次 [N]/[N]
- 字數 [min]-[max] | 比值 [X]%
- validate_analysis.py: ✅/❌
- 問題:[NONE / 列表]
```

**失敗處理:** 修正 → 重提 → 最多 1 次重試(熔斷)。

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

**🔒 Compliance Receipt:** `🔒 COMPLIANCE_RECEIPT: PASSED | Race [X] | [timestamp]`
下一場前:`view_file` 確認 Receipt 存在。

---

> [!CAUTION]
> **🚨 TOP4_FORMAT_ENFORCEMENT(P25):**
> 1. **Top 4 必須用 `🥇🥈🥉🏅` + bullet list 格式。** 嚴禁 Markdown 表格。
> 2. **每個選項 4 必填欄位:** 馬號馬名 / 評級✅數 / 核心理據(LLM 自由發揮)/ 最大風險
> 3. **完整結構(見 `session_start_checklist.md` 骨架):** Part 3 Verdict → Part 4 盲區 → CSV
> 4. **排名 = Absolute Ranking Mandate。** 評級高排前,同級比 ✅ 數。
## Step 4.5: 自檢總結 (Self-Improvement Review)

> **注意:** 大部分自我改善機制已集中到 `HKJC Compliance Agent` 嘅自我改善引擎(Step 4)。
> Wong Choi 單繼續執行以下簡化版總結。

當所有場次分析完畢(或用戶決定停止),喺生成 Excel 之前,讀取 `_session_issues.md` 全部內容。

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
當所有指定場次分析完畢(或用戶決定停止),透過 Python 腳本生成一份 Excel 總結表,匯總所有已完成場次嘅 Top 4 精選。

```bash
python ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/generate_hkjc_reports.py" --target_dir "[TARGET_DIR 絕對路徑]" --weather "[場地狀態/天氣]"
```
> 注意:必須從 Antigravity 根目錄執行,或使用腳本嘅絕對路徑。

此腳本會讀取所有 Analysis.md(及 Analysis.txt)中嘅 CSV 數據,寫入 `[Date]_[Racecourse]_總結表.xlsx`。

> ⚠️ **失敗處理**:見底部「統一失敗處理協議」。觸發條件:腳本執行失敗。

## Step 6: 最終匯報 (Final Briefing)
向用戶匯報所有場次的 Top 4 精選總覽(簡表形式),並提供所有輸出檔案的絕對路徑。

**輸出檔案清單**:
1. 📄 [MM-DD] Race 1-N 排位表.md (由 HKJC Race Extractor 提取並合併)
2. 📄 [MM-DD] Race 1-N 賽績.md (由 HKJC Race Extractor 提取並合併)
3. 📄 [MM-DD] 全日出賽馬匹資料 (PDF).md
4. 🗒 每場獨立嘅 Analysis.md
5. 📊 `[Date]_[Racecourse]_總結表.xlsx`(所有場次 Top 4 匯總)

## Step 7: 任務完成 (Task Completion)
將 `_session_issues.md` 嘅 Status 更新為 `COMPLETED`。
通知用戶一切已準備就緒。

## Step 7b: Session Cost Report（可選 — P35 新增）

> **設計理念:** 受 ECC `cost-aware-llm-pipeline` 啟發。追蹤每次分析 session 嘅 token 消耗同成本估算。

完成 Step 7 後，執行 session 成本追蹤：
```bash
python3 .agents/scripts/session_cost_tracker.py "{TARGET_DIR}" --domain hkjc --batch-size {BATCH_SIZE}
```
喺聊天中簡要匯報成本摘要（3 行以內）。此步驟失敗唔影響任何結果。

## Step 8: 數據庫歸檔 (Database Archival — P32 新增)

完成 Step 7 後,使用 MCP 工具將本次分析結果持久化(此步驟為可選但強烈建議):

**8a. SQLite 歸檔(結構化數據 — 用於命中率追蹤):**
使用 SQLite MCP 嘅 `write_query` tool 將每場嘅 Top 4 Verdict 寫入資料庫:
```sql
INSERT INTO hkjc_ratings (date, venue, race_number, horse_number, horse_name, final_grade, verdict_rank)
VALUES ('{DATE}', '{VENUE}', {RACE_NUM}, {HORSE_NUM}, '{HORSE_NAME}', '{GRADE}', {RANK});
```
每場 Race 嘅 Top 4 各寫一行(共 4 行 × N 場)。同時寫入 `verdicts` table 作為跨引擎追蹤。

**8b. Knowledge Graph 記憶(語義知識 — 用於跨 Session 學習):**
使用 Memory MCP 嘅 `create_entities` + `create_relations` 將以下關鍵發現寫入長期記憶:
- 場地偏差觀察(例:「2026-04-01 Sha Tin 草地 — 內欄偏差明顯」)
- 騎練組合新發現(例:「Zac Purton × John Size 本季 Win% 下降」)
- Decision Diary 中嘅 DISCOVERY 類目

**8c. 可選 — CSV 匯出至 Google Drive:**
若需要喺其他設備查看歷史數據,使用 `read_query` 匯出為 CSV 後存檔到 TARGET_DIR。

> ⚠️ **失敗處理**:若 MCP 工具不可用(例如首次使用未安裝),跳過此步驟不影響分析結果。記錄到 `_session_issues.md`。

# Recommended Tools & Assets
- **Tools**: `search_web`, `run_command`, `view_file`, `grep_search` (⚠️ `write_to_file`/`replace_file_content`/`multi_replace_file_content` 已被 P19v6 完全封殺 — 只用 `run_command` + heredoc pipeline)
- **MCP Tools (P32 新增)**:
  - `playwright_navigate` / `playwright_screenshot` — 網頁即時數據抓取(Python 腳本失敗時嘅後備)
  - `read_graph` / `create_entities` / `create_relations` — Knowledge Graph 記憶(場地偏差、跨 session 筆記)
  - `read_query` / `write_query` / `list_tables` — SQLite 數據庫查詢(歷史評級、命中率追蹤)
- **Assets**:
  - `scripts/generate_hkjc_reports.py`:自動讀取分析結果並產出 Excel 格式。

---

# 操作協議(Read-Once — 啟動時載入)
你必須喺 session 開始時讀取 `resources/01_protocols.md`,內含:
- **統一失敗處理協議** — 所有失敗場景嘅處置方式
- **🚨 File Writing Protocol (P19v6)** — 所有分析寫入必須用 `run_command` + heredoc → safe_file_writer.py 管道。`write_to_file` / `replace_file_content` / `multi_replace_file_content` 已完全封殺。

# 🚨 終極防死機 / Safe-Writer Protocol (P19v6 — 2026-04-05 強化)

> **🚫🚫🚫 TOTAL BAN — `write_to_file` / `replace_file_content` / `multi_replace_file_content` 完全封殺 🚫🚫🚫**
>
> **歷史教訓(P19v1→v6 演進):**
> - P19v1-v3: `write_to_file` / `replace_file_content` 超過 100 行 → IDE 假死機 (`+0 -0`)
> - P19v4: `write_to_file` 寫 `/tmp/*.py` → 仍然經過 IDE JSON 管道，一樣卡死
> - P19v5: 允許 `write_to_file` 寫小檔(<20行)同 `/tmp` → 實測證明仍然卡死！
> - **P19v6 (2026-04-05): 完全封殺。任何大小、任何路徑均禁止。**
>
> **唯一合法寫入方法:**
> `run_command` + Heredoc → /tmp → Base64 → safe_file_writer.py (WLTM)
>
> **⛔ 自檢觸發器:** 若你正在準備使用 `write_to_file` → ⛔ STOP → 你已違規 → 改用下方管道。
>
> **🚨 FALLBACK 硬性規定（2026-04-05 新增 — 歷史教訓: Gemini 用錯路徑後 fallback 到 write_to_file 再次死鎖）:**
> - 若 `safe_file_writer.py` 路徑搵唔到 → **絕對唔可以 fallback 到 `write_to_file`**
> - 正確嘅 fallback 係: `cp /tmp/batch_N.md "{TARGET}"` (overwrite) 或 `cat /tmp/batch_N.md >> "{TARGET}"` (append)
> - **任何情況下 `write_to_file` / `replace_file_content` / `multi_replace_file_content` 都係死路一條 — 唔好用！**

**🔧 SAFE_WRITER 路徑常量（所有引擎必須使用）:**
```
# macOS 絕對路徑:
SAFE_WRITER="/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/safe_file_writer.py"

# 相對路徑(從 Antigravity 根目錄):
SAFE_WRITER_REL=".agents/scripts/safe_file_writer.py"

# ⚠️ Step 0 — 每個 session 開始時必須先驗證路徑:
ls -la "$SAFE_WRITER" 2>/dev/null && echo "SAFE_WRITER_OK" || echo "SAFE_WRITER_MISSING"
# 若 MISSING → 用 find 搵: find "$(pwd)" -name safe_file_writer.py -type f
```

**三步管道 — Heredoc → /tmp → Base64 → safe_file_writer.py (WLTM)**

**Step 1: 用 `run_command` + heredoc 寫入 /tmp 暫存檔**
```bash
cat > /tmp/batch_N.md << 'ENDOFCONTENT'
[你的分析內容]
ENDOFCONTENT
echo "HEREDOC_OK: $(wc -l < /tmp/batch_N.md) lines"
```

**Step 2: Base64 編碼 + pipe 到 safe_file_writer.py**
```bash
SAFE_WRITER="/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/safe_file_writer.py"
base64 < /tmp/batch_N.md | python3 "$SAFE_WRITER" \
  --target "{TARGET_DIR}/{ANALYSIS_FILE}" \
  --mode append \
  --stdin
```

**⚠️ Step 2 失敗時嘅 Fallback（唔用 safe_file_writer 嘅 cp/cat 直寫）:**
```bash
# Fallback A — overwrite:
cp /tmp/batch_N.md "{TARGET_DIR}/{ANALYSIS_FILE}"
# Fallback B — append:
cat /tmp/batch_N.md >> "{TARGET_DIR}/{ANALYSIS_FILE}"
# ⛔ 絕對唔可以 fallback 到 write_to_file / replace_file_content！
```

**Step 3: 驗證（每個 Batch 必做）**
```bash
tail -3 "{TARGET_DIR}/{ANALYSIS_FILE}"
echo "---LINE_COUNT---"
wc -l "{TARGET_DIR}/{ANALYSIS_FILE}"
```

**📋 模式選擇:**
- **第一個 Batch (B1):** `--mode overwrite`（建立新檔）
- **後續 Batch (B2+):** `--mode append`（追加內容）
- safe_file_writer.py **絕對路徑:** `/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/safe_file_writer.py`



# 🛑 Pipeline Testing & Agent Execution Boundaries
**CRITICAL PROTOCOL: How to Avoid Automation Shortcuts in the Future**

1. **停止測試捷徑 (No Automated Shortcuts for LLM Analysis):** 
   身為 LLM 分析引擎，你嘅職責就是根據 `extract_formguide_data.py` (或其他抽取器) 抽出嚟嘅客觀數據，做「深度法醫分析」同判定 Grade。在日後執行任何 Pipeline 測試或端到端執行時，**絕對不能用 Python script 去模擬生成內容或塞字過關**。必須老老實實當自己做緊真飛分析一樣，用 Markdown 直接把高質素、具深度的優質內容完整寫出嚟。
2. **遵守系統角色 (Respect System Roles):** 
   分工極為明確。Python 腳本負責「砌骨架」同做「算術題」（例如抽數、排版、計算 Matrix 分數），而你 (LLM) 負責「入血肉」（撰寫戰術節點、寬恕檔案、段速法醫及風險評估）。**任何企圖繞過血肉生成嘅舉動都係嚴重違反 Protocol 嘅行為。**

