# Agent Architect v3.2.0 — 終極升級大綱（經審計修訂版）

> **版本**：v3.2.0-reviewed | **審計日期**：2026-04-09
> **審計者**：Agent Architect (v3.1.0) + Claude Opus 交叉審核
> **狀態**：✅ 已清除環境衝突項 | ✅ 已補齊遺漏基建 | ✅ 已加入最終工具搜索結果

呢份計劃書匯總咗所有經過**實戰可行性驗證**嘅 2026 頂尖 Agent 框架、監控測試工具，以及專門針對 **Google Gemini 3.1 Pro 壓制幻覺**嘅核心技術。所有同 Antigravity 生態系（Google Drive 環境、零成本原則、Prompt-based Agent 架構）有衝突嘅項目已經被移除或降級至 Parking Lot。

---

## 決策與推薦

1. **修改權限邊界：Agent Architect 的 Reflexion (自動修復) 權限**
   - **Recommendation (Hybrid 混合模式)**：**禁止** Agent Architect 覆寫 `<system_role>` 及 `<context_data>`。自動修改權限僅限於向 `<critical_constraints>` 追加紅線規則，以及修改/增加 Few-shot examples。

2. **XML 語法轉換：人類閱讀困難的解決方案**
   - **Recommendation (Modular Isolation 模塊隔離)**：主檔案 `SKILL.md` 只保留人類閱讀嘅大綱。將 `<xml>` 標籤全部放入 `resources/engine_directives.md`。

3. **Thinking_Level 的彈性設定**
   - **Recommendation (Frontmatter 參數化)**：喺每個 Agent 嘅 YAML Frontmatter 加入 `gemini_thinking_level: MEDIUM`。用戶可以隨時因應任務難度改做 `HIGH`。

4. **MCP 整合與跨設備存儲方案 (Cross-Device ⚠️)**
   - **Recommendation (嚴禁 SQLite，堅守 Markdown + 安全寫入)**：因應 Google Drive 同步環境，全面放棄 SQLite MCP。堅持使用純文本（Markdown / JSON）作為存儲載體，並強制透過 `safe_file_writer.py` 原子級寫入。

5. **Implementation Plan 產出嚴格規範 (極致工程詳盡版)**
   - **Recommendation (Surgical Precision Specification)**：Architect 未來所有草擬的 Implementation Plan 必須直接達到「極致工程詳盡版 」。
   - **強制標準**：絕對禁止「過度簡化」或抽象的步驟描述。必須寫明：(1) 具體的腳路徑及 Python script 檔名；(2) 精確的資料流與 API 調用方式（如 JSON bridging）；(3) LLM 與 Python 的嚴格分工邊界（Python 計算/排版，LLM 專注推理）；(4) Batch Execution 分組邏輯及自動 QA (Self-Correction) 的除錯重試迴圈。

---

## 核心模塊（已驗證，準備落地）

### 模塊 1：Gemini 3.1 Pro 專屬防幻覺協議 ⭐ P0
新增 **Pattern 23: 4-Block XML 嚴格約束協議**
- 將 Prompt 模塊隔離：主檔放 `SKILL.md`，機讀 XML 規則放 `resources/engine_directives.md`。
- **Chain of Verification (CoVe)**：強制 Agent 在輸出前生成 `<self_correction>` 自查。
- **指令後置法則**：永遠將核心指令放喺 Prompt 最尾（先 `<context>` → `<data>` → 最後 `<instructions>`）。Gemini 3.1 Pro 對最後處理嘅指令注意力最高。
- **工程師口吻優先**：使用 **Goal + Constraints Pattern**，避免冗長 Persona 描述。直接寫 `【目標】` + `【限制條件】`。

**Gemini 原生防幻覺工具鏈** 🆕：
- **`responseSchema` 強制結構化輸出**：所有需要 JSON 輸出嘅 Agent，必須喺 API 調用時設定 `response_mime_type: "application/json"` + `response_json_schema`。Gemini 會進行 Constrained Decoding，確保輸出 100% 符合 Schema 語法。
- **`Instructor` 庫 (Pydantic 驅動嘅結構化提取器)**：開源 Python 庫，原生支援 Gemini API。用 Pydantic Model 定義 Output Schema，Instructor 自動處理 Validation、Retry、同格式修正。Agent Architect 教導所有 Agent 以 `instructor.from_gemini()` 取代原始 API 調用。
- **Temperature 參數規範**：事實性任務（分析/數據提取）強制 `temperature: 0.1-0.3`；創意性任務（取名/文案）允許 `temperature: 0.7-1.0`。寫入每個 Agent 嘅 YAML Frontmatter。
- **Self-Correction Loop（自動修正迴圈）**：如果 Agent 輸出唔通過 Pydantic 校驗，自動用 JSON Patch (RFC 6902) 修正失敗欄位，避免重跑整個 API Request（節省 Token + 延遲）。

---

### 模塊 2：Agent 編排架構（設計哲學層，非 Runtime 依賴）⭐ P1
新增 **Pattern 24: 狀態機思維 (State Machine Thinking)**
- 吸收 LangGraph 嘅設計哲學，但以 **純 Prompt 嵌入** 落地：教導 Agent 將任務分解為明確嘅狀態轉換（`INIT → EXTRACT → ANALYZE → VERDICT → DONE`），每個狀態有明確嘅進入條件同退出條件。
- **唔引入 LangGraph 作為 Runtime 依賴**（保持零成本原則），而係將狀態機概念嵌入 `SKILL.md` 嘅 Interaction Logic 區塊。

新增 **Pattern 25: 協商與共識協議**
- 延續 Pattern 18 (Zero-Cost Multi-Perspective)，模擬多視角內部辯論，得出共識後才輸出結果。純 Prompt 實現，零外部依賴。

---

### 模塊 3：元智能體進化 (Proactive & Reactive Reflexion) ⭐ P0
修改 **Agent Architect SKILL.md**，並將能力下放到所有 Agent：
- **Reactive Reflexion (被動修復)**：Generate → Evaluate → Refine 三步循環。
- **Proactive Feedback Loop (主動提問機制)**：Agent 在執行任務時，若發現架構缺陷或更好的捷徑，會暫停並主動輸出 `<improvement_proposal>` 詢問用戶是否啟動永久修訂。
- **觸發條件精確化** 🆕：主動提問**只在以下情況觸發**，避免無故打斷用戶工作流：
  1. Confidence Score < 50（Agent 對自己嘅輸出信心不足）
  2. 連續兩次 Tool Call 失敗
  3. 偵測到 Pattern 違規（例如跳過 Quality Gate）
- **超時行為** 🆕：如果用戶 2 輪對話冇回應 `<improvement_proposal>`，Agent 自動將提議降級為「記錄但唔執行」（寫入 `resources/improvement_log.md`），繼續原有任務。

---

### 模塊 4：評估、監控與防禦 (Eval & Testing) ⭐ P1
開發 **Python-First 工具箱**：
- `scripts/agent_evaluator.py`：LLM-as-a-Judge 引擎，基於 **DeepEval** 框架，客觀打分。每次 Architect 改完一個 Agent 嘅 `SKILL.md`，自動行 50 條 Test Case，畀出「幻覺率 (Hallucination Rate)」同「工具調用正確率」分數。高分先准 Release。
- `scripts/red_team_tester.py`：壓力測試工具。**重點對準**「格式漂移 (Format Drift)」同「步驟省略 (Step Skipping)」（而非傳統 Injection 防禦，因為用戶自己就係唯一操作者）。
- **`Promptfoo` CLI 整合** 🆕：開源 CLI 工具，專門做 Prompt 嘅版本對比同 A/B Testing。當 Architect 想比較兩個版本嘅 `SKILL.md` 邊個更好，可以用 `promptfoo eval` 一次過跑 100 個 Test Case，自動出 Win Rate 報告。

---

### 模塊 5：跨設備安全 MCP 架構 ✅ 已落地
> 呢個模塊嘅核心（禁 SQLite、堅守 `safe_file_writer.py`）已經喺 Pattern 8/14/17/19 完全實現。確認同現有 Pattern 一致，無需額外工作。

---

### 模塊 6：自主 Debug 與 RCA 自癒機制 ⭐ P2
增加 **Debug Mode (Mode D)**：
- **Traceability (軌跡重播)**：引入自動化收集 Agent 執行 Log，還原 Critical Failure Step。
- **Agentic Post-Mortem (事後驗屍報告)**：Bug 分類及 Knowledge Transfer (自動補丁)。
- **⚠️ 前置需求**：依賴模塊 12 (Execution Journal 基建) 先行完成。

---

### 模塊 7：Wong Choi 量化分析專屬工具箱 (Sports & Racing Analytics) 🏇 ⭐ P2

**7.1 賽馬/賠率量化回測與風險管理 (Horse Racing Quantitative Engine)**
不再只限於表面賽果分析，Architect 會教導 Agent 實作以下數學與統計模型：
- **預期值 (Expected Value, EV) 發掘模型**：
  - 教導 Agent 使用 `sklearn.linear_model.LogisticRegression` 或 `xgboost` 構建 True Probability (真實勝率) 模型。
  - **核心公式寫入規則**：強制 Agent 在最終分析中計算 $EV = (True\_Prob \times Decimal\_Odds) - 1$。只有 $EV > 0$ 的馬匹才會被標記為 Value Bet。
- **凱利公式 (Kelly Criterion) 注碼分配**：
  - 引入 Fractional Kelly (小數凱利) 的 Python 實作庫 (例如 `sports-betting` 包)。
  - **公式實作**：$f^* = p - (q / b)$，其中 $p$ 為真實勝率，$q$ 為敗率， $b$ 為淨賠率。
- **防前瞻偏誤回測 (Time-Series Backtesting)**：
  - 教導 Agent 使用 `sklearn.model_selection.TimeSeriesSplit` 處理歷史數據，嚴禁 Look-ahead bias。
- **降噪與特徵工程 (Feature Engineering Priority)**：
  - 優先提取高信號特徵（L400、體重變化、步速指標、場地誤差 EEM），利用 `StandardScaler` 解決 Scaling 問題。
- **1D 分段速度建模（空間分析替代方案）**：
  - 利用分段時間 (Sectionals) 重建速度曲線 (Velocity Profile)，計算加速度衰竭點 (Deceleration Point)。
  - 基於走位代碼 + 勝負距離估算額外跑動距離 (Extra Ground Loss)。

**7.2 NBA 官方數據挖掘與預測引擎**
- **`nba_api` & `pandas`**：直接對接 `stats.nba.com` 嘅隱藏 endpoints。
- **高階影響力數據分析**：PIE + Tracking Data → 構建「球員缺陣影響 (Injury Impact)」迴歸模型。
- **`pbpstats` 陣容化學反應**：爬取 Play-by-play 數據，計算 On/Off splits 嘅高階陣容化學反應。
- **`balldontlie API`**：完全免費、無需 API Key 嘅 JSON API。基礎 Box Score 回測首選。

**7.3 電競 LoL 解析 (Leaguepedia API & Oracle's Elixir)**
- **Leaguepedia Cargo Database 連接**：透過 `mwclient` 免 API 費調用 Cargo SQL 接口。
- **Oracle's Elixir 歷史分析**：計算 Early Game Rating (EGR) 及 Mid/Late Rating (MLR)。

---

### 模塊 8：Architect 自我進化引擎 (Prompt Optimization Toolkit) ⭐ P1
> 以下工具全部定位為 **Architect 嘅離線武器**（喺優化 Agent 時外部調用），而非嵌入所有 Agent。

- **🛠 DSPy (Stanford)**：「Programming, not prompting」。Architect 利用 DSPy 去 Compile 及自動最佳化其他 Agent 嘅 Prompt，根據失敗案例自動微調用字。
- **🚀 Vertex AI Prompt Optimizer (Google 原廠)**：Gemini 專武。輸入現有 `SKILL.md`，Optimizer 利用迭代演算法自動重組 Prompt，針對 Gemini 3.1 Pro 嘅體質（Context 後置、System Instruction 分隔）產出最高勝率寫法。
- **🧬 GEPA-AI (基因演算法 Trace 分析)**：如果旗下 Agent 頻繁出錯，Architect 將 Full Execution Trace 掉入 GEPA，由 GEPA 精準定位哪一句 Prompt 導致邏輯斷裂，施行外科手術式修改。*（依賴模塊 12 嘅 Execution Journal）*
- **🔍 Langfuse (開源軌跡追蹤)**：Agent 除蟲 X 光機。調用 Trace 數據精確指出 Agent 喺邊一步諗錯、邊一步 Call 錯 Tool。可 Self-host 保障數據主權。

---

### 模塊 9：基石技術棧 (Battle-Tested Foundations) ⭐ P1

- **🛡 Pydantic + Instructor (嚴格資料格式防線)**：
  - 強制所有子 Agent 透過 Pydantic 定義 Output Schema。`Instructor` 庫作為 Pydantic 嘅 Gemini 專用伴侶，自動處理 Validation → Retry → 格式修正嘅完整循環。消除 JSON 幻覺。
- **📝 Jinja2 (動態提示詞模板引擎)**：
  - 允許 Architect 構建有邏輯分支 (if/else)、迴圈嘅深度 `SKILL.md`，精準控制複雜 Agent 嘅 Context 組合。取代危險嘅字串拼接。
- **🧪 pytest (LLM 測試框架)**：
  - 推廣 TDD 給 LLM。使用 pytest + Mocking 模擬斷線等極端情況，確保 Agent 喺壓力下唔會 Panic。
- **🎯 Promptfoo (Prompt 版本控制與 A/B Testing)**：
  - 開源 CLI 工具。將 Prompt 當做 Code 管理——版本對比、回歸測試、跨 Model 兼容性檢查。Architect 改完 Prompt 後必跑 `promptfoo eval` 驗證。

---

### 模塊 10：DAG 任務編排 ⭐ P2
- **DAG (有向無環圖) 任務切割**：教導 Agent 將極複雜任務畫成 DAG（用 Mermaid 圖 + Prompt 嵌入嘅方式落地），嚴格控制任務依賴順序，解決 AI「一舊雲直衝」導致步驟混亂嘅問題。
- **落地方式**：純 Prompt 指示 + Mermaid 視覺化。唔引入 n8n 或其他外部 Runtime。

---

### 模塊 11：Meta-Prompting 自演化架構 🆕 ⭐ P1
> 最新搜索結果發現嘅 2026 前沿概念。

- **Meta-Prompt 控制面**：Agent Architect 內部維護一個「元提示詞 (Meta-Prompt)」作為控制面板，佢負責管理所有子 Agent 嘅 Task Prompt 點樣生成、批評、同進化。
- **運作流程**：
  1. Architect 嘅 Meta-Prompt 生成初版 Task Prompt
  2. 用 DeepEval / Promptfoo 跑自動評估
  3. 根據評估結果，Meta-Prompt 自動修訂 Task Prompt（受限於模塊 3 嘅修改權限邊界）
  4. 循環直至達標
- **同 DSPy 嘅區別**：DSPy 係 Python Runtime 離線工具；Meta-Prompting 係純 Prompt 層面嘅自我進化協議，可以喺 Antigravity 環境內即時運行。

---

### 模塊 12：Execution Journal 基建（原 Plan 遺漏項）🆕 ⭐ P0
> Agent Architect 審計發現嘅最關鍵遺漏。Mode D、GEPA、Langfuse 全部依賴呢個基建。

- **所有 Agent 新增 Execution Journal 指令**：喺每個 Agent 嘅 `SKILL.md` Interaction Logic 最後加入一行，要求 Agent 喺每個 Step 完成時寫一行到 `_execution_log.md`：
  ```
  > 📝 LOG: Step [X] | Tool: [Y] | Result: [Success/Fail] | Duration: [Z]s
  ```
- **格式**：Markdown 追加 (append mode)，用 `safe_file_writer.py --mode append`。
- **用途**：為 Mode D 軌跡重播、GEPA Trace 分析、Langfuse 數據導入提供統一嘅結構化日誌源。

---

### 模塊 13：版本控制與回滾機制（原 Plan 遺漏項）🆕 ⭐ P0
> 防止自動修改 SKILL.md 時出現不可逆嘅損壞。

- **Snapshot Before Modify 協議**：Architect 每次修改任何 Agent 嘅 `SKILL.md` 前，必須先將當前版本備份到 `resources/archive/SKILL_v{YYYYMMDD}.md`。
- **Rollback 指令**：如果修改後 DeepEval 分數下降 > 10%，Architect 必須自動回滾到 snapshot 版本並通知用戶。
- **Audit Trail**：所有修改記錄寫入 `resources/audit_history.md`（已有機制，確認同新版本控制整合）。

---

## Mode B 優化流程升級：工具鏈調用順序 🆕

當 Agent Architect 以 **Mode B (優化現有 Agent)** 運行時，以下係完整嘅工具調用流程（加入新模塊後）：

```
Step 1: 讀取目標 Agent 嘅 SKILL.md + resources/
Step 2: run_command agent_health_scanner.py --target [path]     ← 現有自動掃描
Step 3: 對照 design_patterns.md (P1-P25) 逐項檢查              ← 更新至 P25
Step 4: 🆕 對照模塊 9 基石技術棧逐項檢查：
        - Pydantic Output Schema 有冇定義？
        - Jinja2 模板有冇取代字串拼接？
        - pytest Test Case 有冇覆蓋？
Step 5: 🆕 對照模塊 1 Gemini 優化法則檢查：
        - 指令係咪放喺 Prompt 最尾？
        - 有冇用 Goal + Constraints Pattern？
        - CoVe 自檢有冇啟用？
Step 6: 🆕 執行 Promptfoo A/B Testing（如果有舊版本可比較）
Step 7: 合併所有結果 → 生成診斷報告（含 Confidence Score）
Step 8: 等用戶確認修改項目
Step 9: 🆕 Snapshot 當前版本到 archive/ （模塊 13）
Step 10: 生成更新後嘅 SKILL.md（標注修改位置）
Step 11: 🆕 跑 DeepEval 驗證新版本分數 ≥ 舊版本
Step 12: 更新 audit_history.md
```

---

## Verification Plan

1. **自動化測試**：運行 `agent_evaluator.py` 確保 JSON 打分系統運作正常。
2. **Prompt A/B Testing**：用 `promptfoo eval` 比較修改前後嘅 Agent 表現。
3. **版本回滾測試**：故意製造一次「DeepEval 分數下降 > 10%」嘅情況，驗證自動回滾機制。
4. **Execution Journal 驗證**：喺 3 個 Agent 上啟用 Journal，確認日誌格式一致且 append 模式正常。
5. **系統自癒測試**：故意向 Agent 發送惡意引導，測試 Architect 能否自動生成 Post-Mortem 報告並自我修補。

---

## 🅿️ Parking Lot（暫時擱置，待日後條件成熟再啟動）

以下項目因環境衝突、數據來源未就緒、或違反零成本原則而暫時擱置：

| 項目 | 原模塊 | 擱置原因 | 重新啟動條件 |
|:---|:---|:---|:---|
| **SmolAgents (Hugging Face)** | 原 8 | 同 Pattern 22 (Python-First) 哲學重疊；SmolAgents 假設 Agent 係 Python Process，我哋係 Prompt-based | 如果日後轉向 Python Runtime Agent |
| **Composio / MCP Glue Layer** | 原 9 | 目前無具體外部 API 接駁需求；違反零成本原則 | 需要接駁 Slack/Discord/Notion 時 |
| **E2B (Code Interpreter Sandbox)** | 原 11 | Hosted 服務有成本；本地 Python `venv` 已經夠用 | 需要 100% 隔離嘅 Agent Code 執行時 |
| **ChromaDB / FAISS (向量庫)** | 原 11 | 二進制 `.bin`/`.pkl` 檔案同 Google Drive 同步會損壞 | 改用 JSON-based 向量方案或存放 Drive 外 |
| **LlamaIndex (RAG 連接器)** | 原 11 | 目前 Agent 透過 `view_file` 直接讀文件已經足夠 | 需要處理大量 PDF/非結構化文件時 |
| **Floodlight 2D XY 追蹤** | 原 7.1 | 賽馬（無 GPS）同 NBA（Second Spectrum 完全封閉，只畀球隊同官方夥伴）均無免費 XY 座標數據 | 任何體育賽事開放公共 Tracking API |
