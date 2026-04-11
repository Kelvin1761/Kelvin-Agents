# AU Orchestrator V8 升級計畫 (與 HKJC V8 同步)

這個升級計畫旨在將 `au_orchestrator.py` 與我們剛剛為 `hkjc_orchestrator.py` 開發的終極 V8 狀態機架構完全對齊，解決目前 AU 殘留的舊有邏輯缺陷。

## 🔍 現有架構落差分析 (Gap Analysis)

對比 `hkjc_orchestrator.py`，目前的 `au_orchestrator.py` 缺乏以下 4 項核心的 V8 特性：

1. **缺乏 Attention 分流機制 (No Batching):** AU 目前要求 Agent 一次過分析全場所有馬匹並寫入單一 `Logic.json`。這會導致在 14 匹馬出賽時，Agent 的專注力被嚴重攤薄，引發後半段馬匹分析質素下降。
2. **缺乏防失憶清單 (No Persistent Dashboard):** AU 只會在 Terminal 畫面印出 `[ ]` 工作進度，但不會產生實體的 `_session_tasks.md`。若對話重啟，Agent 無法自行找回進度。
3. **無 3-Strike 熔斷機制 (No Fallback Loop):** AU 只要遇到 QA 失敗就會 `sys.exit(1)` 並無限重複。缺乏 `strikes` 計數器來防止「無限修復失敗迴圈」。
4. **Stdout 指令太薄弱 (Weak Prompting):** AU 在指派 Agent 寫 JSON 時，只印出「`請生成精簡版推演檔案`」，並沒有像 HKJC 一樣強制提醒 `100-200字` 以及 `Matrix 必須寫 _reasoning` 的嚴格規定。

## 👨‍💻 擬議之工程改動 (Proposed Upgrades)

### 1. 拆入 `get_batches()` 與遞進式分析邏輯
- **改動 `au_orchestrator.py`**:
  - 引入 `get_horse_numbers` 與 `get_batches(horses, size=3)` 函數。
  - 修改 `State 3` 的邏輯：不再檢查整個 json 是否齊全，而是檢查 `logic_data['horses']` 內是否已經包含 Batch n 的那 3 匹馬。如果未涵蓋，則 stdout 指示只分析特定 3 匹馬。

### 2. 生成 `_session_tasks.md`
- **改動 `au_orchestrator.py`**:
  - 加入 `update_session_tasks()` 函數。每次啟動時，除了 `print`，強制寫入或覆蓋 `${TARGET_DIR}/_session_tasks.md`，內容具備所有賽事與 Batch 的勾選框。

### 3. 實作 `.qa_strikes.json` 保護機制
- **改動 `au_orchestrator.py`**:
  - 在執行 `completion_gate_v2.py` 的上下文中，加入 `.qa_strikes.json` 的讀寫。
  - 當失敗累積 3 次，拋出 `🚨 [CRITICAL ALERT]` 強迫放棄並交由人類處理，而不是卡死 AI。

### 4. 強化 Stdout 提示與編譯器 `compile_analysis_template.py` 檢查
- **改動 `au_orchestrator.py`**: 將 `print("👉 請生成...")` 改為與 HKJC 相同之嚴格提示：
  `"⚠️ 強制規定: 評級矩陣必須包含 _reasoning 欄位, 核心邏輯介於 100-200字。"`
- **改動 `compile_analysis_template.py` (AU 編譯器)**:
  - 確保它像 `compile_analysis_template_hkjc.py` 一樣，會將 `_reasoning` 欄位抽出並寫入 Markdown，讓 QA 腳本可以成功讀取與驗證。
