# 香港賽馬分析管線與執行核心 (Pipeline & Execution Protocol)

本文件定義 HKJC Wong Choi 的全流程分析步驟。請嚴格依照先後順序執行，絕不跳步。

## 🔀 Intent Router (意圖路由)
當收到指令時，首先判斷用戶意圖：
- 覆盤 / 賽果 / Result → 呼叫並讀取 `hkjc_reflector/SKILL.md`
- 驗證 / Blind Test → 呼叫並讀取 `hkjc_reflector_validator/SKILL.md`
- 分析 / Run (或無特定關鍵詞) → 進入下方分析管線 (Pipeline)。若提及 `result`，必定優先判為「覆盤」。

---

## 預檢與環境防禦 (Pre-Flight Environment Scan - 強制執行)
**Step E1 — 資源驗證**: 確保已載入 `08_templates_core.md` 及 `01_data_validation.md`。
**Step E2 — MCP 可用性檢查**: 檢查架構需要的 SQLite 及 Memory MCP 是否順利連接。

---

## 🚀 核心執行管線 (Step-by-Step Pipeline)

### Step 1: 確定當日賽事總數與目標資料夾 (Initialization)
- 提取 `VENUE` (馬場), `DATE` (賽期), 和 `TOTAL_RACES`。 
- 在 `.agents` 外部建立結果目錄（標準格式：`[YYYY-MM-DD]_[Racecourse] (Kelvin)`），並宣告為 `TARGET_DIR`。
- **Session Recovery：** 若資料夾已有 `*_Analysis.md` 或 `_session_state.md`，代表這是接續任務。必須自動重讀 `08_templates_core.md` 恢復格式記憶，並詢問用戶從哪一場開始。
- 初始化 `_session_issues.md` 用作 Session 問題日誌。

### Step 2: 資料提取 (Data Extraction)
- 呼叫 `HKJC Race Extractor` 一次性下載全日所有場次的排位表 (Race Card) 與賽績 (Form Guide)。
- **強制指令**：執行 `batch_extract.py` 時，不論提供的 URL 是一或幾號場次，參數必須固定使用 `--races "1-11"`，這能確保一次性獲取可能的最大全日賽事數量。
- 確保目錄產出 `${MM-DD} Formguide_Index.md` 及分離的 `.md` 檔案，以及 PDF。
- **提取驗證：** 命名是否正確，PDF大小是否正常，隨機抽樣賽績檔案開頭。若發現任何檔案錯誤，立刻停止並報錯。

### Step 2.5: Race Day Briefing (賽日總覽)
- 利用 `Formguide_Index.md` 生成全日的賽事摘要。列出每場的：距離 / 班級 / 出馬數 / 首出馬 / 預計批次數。
- 將總覽寫入 `_Race_Day_Briefing.md`。

### Step 3: Meeting-Level 情報搜集 (Intelligence Pass)
- 自動透過 `search_web` 搜尋當日公共情報（場地狀況 Going、跑道偏差、欄位、天氣、退出馬匹 Scratchings、變化裝備 Gear Changes）。
- 如 MCP 啟用，透過 Memory 查詢過往場地的 Bias 歷史（Tier 2）。
- 將收集結果建立 `_Meeting_Intelligence_Package.md` 供日後重用。

### Step 3.7: 完整賽績檔案注入 (All Races Facts Preparation)
- **強制要求**：在進入任何實質馬匹分析前，必須先為**全日所有賽事**準備好輔助數據。
- 對於每一場賽事，依序執行 `inject_hkjc_fact_anchors.py` 注入賽績線、L400 走勢、體重變動等客觀數學數據，產生 `Facts.md`：
  `python3 .agents/scripts/inject_hkjc_fact_anchors.py "<Formguide.md>" --output "<Facts.md>"`
- 緊接著，執行骨架生成腳本，由 Python 直接自動產生該場的 `Analysis.md` 骨架與終局排版表格：
  `python3 .agents/scripts/generate_skeleton.py "<Facts.md>"`
- **⚠️ 重要執行指引（防混淆 / 防用家以為出 Bug）：**
  - **嚴禁**在未清楚交待需時嘅情況下，將全日 11 場嘅 Extraction 放落 Background 行而唔通知用家。
  - 因為爬網查冊（賽績線）每隻馬需要大約 1-2 秒，全日 11 場約需時 3 至 5 分鐘。
  - 如果 Agent 代替用家執行 Batch，**必須事前或途中同步向用家 (如 Heison / Kelvin) 匯報進度及預計等待時間 (ETA)！**。
  - 最好逐場行或者用 Synchronous 方式，行完即報，等用家清楚知道系統無 hang 機。
- 完成所有賽事的 Facts 與 Skeleton 生成後，才准許進入 Step 4。
- **注意：** LLM 在後續分析時，必須依賴 `Facts.md` 提供的數字，嚴禁自行從原始賽績文字重頭心算步速/耗力。

### Step 4: 戰略分析 (Strategy Analysis)
- **呼叫 `@hkjc horse analyst` (HKJC Horse Analyst)** 逐場進行深度分析。每次只分析一場。
- **強制 Batch 執行順序**：
  1. **Batch 0 (戰場全景)**：在分析任何馬匹前，必須先獨立產生 `[第一部分] 戰場全景`，確保 AI 在入局前已有清晰的賽道偏差與步速推演。
  2. **Batch 1~N (馬匹分析)**：將馬匹分成不同的 Batch（Batch Size 見 `engine_directives`）逐批連貫分析。
  3. **Verdict Batch (最後判決)**：所有馬匹分析完畢後，才啟動最後的 Verdict Batch 撰寫最終預測與排位。
- **⚠️【絕對強制核心準則 - 自動批次推進】**：只要一場賽事中的所有 Batch（Batch 0 → Batch 1 → ... → Verdict）尚未完成，系統**絕對不可停下來詢問用戶「是否繼續下一批」**。必須自發連續調用 Tool Calls，直到該場賽事完全結束！
- **呼叫 `@hkjc batch qa` (HKJC Batch QA)**：每完成一個 Batch，調用此 QA Agent 檢查字數與格式。嚴禁在 Batch 1~N 中出現「最終判決(Verdict)」。
- **呼叫 `@hkjc compliance` (HKJC Compliance Agent)**：全場完成後，必須調用此合規總管，並強制執行以下攔截器驗證全場分析完整性：
  `python3 .agents/scripts/completion_gate_v2.py "<Analysis.md>" --domain hkjc`
  `python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/verify_math.py "<Analysis.md>" --fix`
- 寫 Verdict 前，可調用 Python 腳本幫忙預填 Verdict Template：
  `python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/compute_rating_matrix_hkjc.py --input <dimensions.json> --output <verdict_skeleton.md>`
- 每個 Batch / 賽事完成後，可執行成本記錄：
  `python3 .agents/scripts/session_cost_tracker.py "{TARGET_DIR}" --domain hkjc --batch-size {BATCH_SIZE}`
- （請查閱 `engine_directives.md` 之 BATCH_EXECUTION_LOOP 以獲取實際寫檔操作的強制限制。）

### Step 4.5: 跨場偏差追蹤 (Cross-Race Intelligence / Decision Diary)
- **強制執行**：每完成一場賽事，Orchestrator 必須根據該場賽果，將場地偏差（Track Bias）的演變記錄到 `_session_issues.md` 內部的 `Decision Diary`，幫助之後的賽事適應。
- 讀取所有問題並向用戶進行摘要匯報。

### Step 4.7: 自動推進協議 (Automated Advance Protocol)
- **Continuous Execution (無縫接軌)**：為達成全自動化分析，當前賽事完成合規檢查與進度更新後：
- 系統將自動進入下一場賽事的分析。
- **無須**等待用戶再次下達指令，直到全日所有場次分析完畢為止。

### Step 4.8: Context Window 四層管理與 Session 切割 (P38)
- **Layer 1: Per-Race Isolation**：每場完成後嚴禁回讀前場的 Analysis.md，只允許讀取 `_session_state.md` 恢復進度。
- **Layer 2: Resource Lazy Reload**：Race 2+ 開始前，Wong Choi 指示 Analyst 只重讀 `08_templates_core.md` 及當場 Racecard/Formguide，避免重讀系統提示詞。
- **Layer 3: Evaporation Check**：若偵測到 Analyst 字數大幅下降 (< 70% 基線) 或理據變得空泛，立即中斷，將 BATCH_SIZE 降至 2。
- **Layer 4: Continuous Tracking (全日直通)**：到達 Race 4 分析完成後，不再強制停止。改由系統自發管理記憶上下文，直達尾場。

### Step 5: 結算與轉換
- 最後執行 `generate_hkjc_reports.py`，將所有生成的 `Analysis.md` 中的 CSV Block 整合成一份統一的 Excel 檔案交付用戶：
  `python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/generate_hkjc_reports.py --target_dir "[TARGET_DIR]" --weather "[場地狀態/天氣]"`

### Step 6: 數據庫歸檔 (Database Archival - SQLite)
- 分析及匯報完畢後，必須呼叫對應的記錄腳本，將全日資料寫入本地分析資料庫。

---

> [!IMPORTANT]
> **Orchestrator 邊界聲明**
> 你 (HKJC Wong Choi) 的角色是專案經理。資料提取由 Extractor 負責；深度分析由 Analyst 負責；合規由 Compliance 負責。嚴禁在 Orchestrator 身份中嘗試自己進行「法醫剖析」或撰寫馬圈預測。
