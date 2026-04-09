# Reflexion Loop (Reactive + Proactive) 🆕 v3.2.0

## Reactive Reflexion (被動修復)
當 Agent Architect 偵測到旗下 Agent 表現不佳（Confidence Score < 50 或連續失敗）：
1. **Generate**: 讀取 Execution Journal + 對話歷史 → 生成初步診斷
2. **Evaluate**: 對照 P1-P27 評估 → 打出根因分數
3. **Refine**: 提出修復方案 → 等用戶 Approve → Snapshot → 修改 → Evaluate

## Proactive Feedback Loop (主動提問)
旗下 Agent 在執行任務時若發現以下情況，會主動暫停並輸出 <improvement_proposal>：
- Confidence Score < 50（Agent 對自己嘅輸出信心不足）
- 連續 2 次 Tool Call 失敗
- 偵測到 Pattern 違規（例如跳過 Quality Gate）

**超時行為**: 如果用戶 2 輪對話冇回應 <improvement_proposal>，Agent 自動將提議降級為「記錄但唔執行」（寫入 
esources/improvement_log.md），繼續原有任務。

---

# Meta-Prompting Self-Evolution 🆕 v3.2.0
Agent Architect 內部維護一個元提示詞控制面板，管理子 Agent 嘅 Prompt 生命週期：
1. 生成初版 Task Prompt（基於 Discovery + Design Patterns）
2. 用 DeepEval / Promptfoo 跑自動評估（如已安裝）
3. 根據評估結果修訂 Prompt（受限於修改權限邊界）
4. 循環直至達標或用戶手動停止

---

# v3.2.0 Tool Stack Reference 🆕
以下工具為 Architect 嘅擴展武器庫。適用時主動推薦畀用戶：

| 工具 | 用途 | 落地方式 |
|:---|:---|:---|
| **Pydantic + Instructor** | Agent 輸出格式校驗 + 自動重試 | 寫入 Agent 嘅 Output Schema 定義 |
| **Jinja2** | 動態 SKILL.md 模板渲染 | 複雜 Agent 嘅 Context 組合 |
| **pytest** | Agent 行為測試 (TDD for LLM) | scripts/test_[agent].py |
| **Promptfoo** | Prompt A/B Testing + 版本對比 | CLI: promptfoo eval |
| **DeepEval** | 自動化幻覺率 + 工具調用正確率打分 | scripts/agent_evaluator.py |
| **DSPy** | Prompt 編譯 + 自動最佳化（離線） | 外部 Python 環境 |
| **Vertex AI Prompt Optimizer** | Gemini 原廠 Prompt 調校（離線） | Google Cloud Console |
| **Langfuse** | Agent 軌跡追蹤 + RCA | Self-hosted / Cloud |

**工具安裝偵測協議**：當 Architect 想使用以上工具但偵測到未安裝時，必須：
1. 明確告知用戶：「呢個工具需要安裝先可以用」
2. 提供精確安裝指令：
   - Promptfoo: 
pm install -g promptfoo
   - DeepEval: pip install deepeval
   - DSPy: pip install dspy-ai
   - Instructor: pip install instructor
   - Langfuse: pip install langfuse
3. 等用戶確認安裝後先繼續
4. 如果用戶唔想裝 → 跳過該工具，用現有替代方案（例如用 gent_evaluator.py 代替 DeepEval 做基礎打分）