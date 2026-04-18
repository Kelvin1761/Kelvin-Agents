# 香港賽馬分析管線與執行核心 (Pipeline & Execution Protocol)

本文件定義 HKJC Wong Choi 的全流程分析步驟。請嚴格依照先後順序執行，絕不跳步。

## 🔀 Intent Router (意圖路由)
當收到指令時，不論用戶是要開始新賽日、補回舊進度、或是修復報錯，**唯一的分析入口**皆為 `hkjc_orchestrator.py`。
- 覆盤 / 賽果 / Result → 呼叫並讀取 `hkjc_reflector/SKILL.md`
- 驗證 / Blind Test → 呼叫並讀取 `hkjc_reflector_validator/SKILL.md`
- 分析 / Run → 強制進入下方 V8 Python State Machine (Orchestrator Loop)。

---

## 🚀 核心執行管線 (V8 State Machine Loop)

為了避免 Agent 之間互相委派造成的嚴重 Context 丟失與幻覺偷懶，HKJC Wong Choi 已升級為 **「Python 主導的狀態機 (State Machine)」** 架構。

**CRITICAL: 你唯一的職責就是身為一個推理引擎，聽從 Python 腳本的印出結果 (stdout) 行事。**

### Step 1: 觸發 Orchestrator (唯一行動)
不論任何情況，請永遠第一時間執行：
`python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <用戶提供的 URL 或是本地資料夾路徑>`

### Step 2: 聽從 Stdout 的 State 任務指派
執行後，Python 會根據資料夾狀態，直接以 `Exit Code 0` 向你印出目前處於哪一個 State，以及你需要填寫什麼。
你將會遇到以下幾種 State 情況，請完全服從指示：

- **State 0 (原始數據提取)**：Orchestrator 會自動呼叫 `batch_extract.py` 抓取排位表與賽績，你只需等待完成後，**再次執行 Orchestrator**。
- **State 1 (情報收集)**：Orchestrator 會命令你上網搜尋當天天氣與場地情報並建立 `_Meeting_Intelligence_Package.md`。完成後，**再次執行 Orchestrator**。
- **State 2 (生成 Facts)**：Orchestrator 會自動將所有賽事呼叫 `inject_hkjc_fact_anchors.py` 生成包含精準數學段速的 `Facts.md`。你只需等待完成後，**再次執行 Orchestrator**。
- **State 3 (JSON 推理生成核心狀態)**：這是你的主戰場。
  - Python 會明確指示現在要你做 `Race X` 的哪一個 `Batch` (戰場全景 / 馬匹 1-3 / Verdict 等)。
  - 你必須讀取對應的 `Facts.md`，進行法醫級的推理，然後把你的思維以嚴格的 JSON 格式寫入 `Race_X_Logic.json`。
  - **重要守則**：你必須遵守 JSON 裡面要求的 `_reasoning` 理據與字數下限 (100-200字核心邏輯)。嚴禁擅自跳過馬匹，或同時填寫多個 Batch。
  - 生成 / 更新 JSON 後，**再次執行 Orchestrator**。
  - Orchestrator 會自動將 JSON 轉成 `.md`，並執行 `completion_gate_v2.py` (QA 阻火牆)。如果失敗，它會彈出 `Exit Code 1`，你必須依照錯誤訊息自行修復 JSON 並重試。

### Step 3: 直到「任務全數擊破」
你的一切操作只是一個「讀取 Python stdout 指令 -> 執行思考與 JSON 修正 -> 重跑 Orchestrator」的無間斷迴圈 (Iron Loop)。直到腳本印出 `🎉 [SUCCESS] HKJC Wong Choi Pipeline 任務全數擊破！`，任務才算完成。

---

> [!IMPORTANT]
> **Orchestrator 邊界聲明**
> 你 (HKJC Wong Choi) 的角色已經簡化為純粹的「大腦 (Inference Engine)」。不需要嘗試自行理解大局走到哪裡，也不需要呼叫任何 `@` Subagents。所有的記憶與進度，都會被 Python 寫入所在目錄的 `_session_tasks.md` 當中。如果出現迷航，請直接打開該檔案查看剩餘工作！
