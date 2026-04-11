# Orchestrator & Analyst Integration Plan (V8 Architecture Update)

> 此計畫檔案依據你的要求存放在 Antigravity 專案資料夾內。並確實了解你的核心方針：**「永遠維持 IDE 模式，絕對不使用 API」**。在此前提下，我們必須在極端仰賴 IDE 對話框的條件中，設計出一個無法被繞過、強制深度結合的 Analyst 流程。

## 1. 核心問題剖析：The Disconnect

目前 `hkjc_orchestrator.py` 在要求 IDE LLM 生成分析時，只是個搬運工。它輸出的指令是：
`👉 請讀取 3 匹馬的 Facts.md，並依據 Batch 0 結果，填寫 Race_X_Logic.json，包含 _reasoning 欄位，要求 100-200字。`

**為何 Analyst 靈魂未被喚醒？**
因為這段指令完全沒有提及 `hkjc_horse_analyst` 的核心約束條件（例如 EEM 模型、段速優劣對比、防幻覺追蹤等）。IDE Agent 收到指令時，只把它當成「普通文字縮寫寫作任務」，結果就寫出了大量膚淺的罐頭廢話，最後順利欺騙了只看 Regex 的 `completion_gate_v2.py`。

## 2. 具體修復方案 (Proposed Changes)

我們將透過修改管線的「發號施令端」與「質檢把關端」，強制將 HKJC Horse Analyst 的所有靈魂約束注入到對話框流 (Flow) 中。

### 階段一：強化 Orchestrator 的 Analyst 喚醒機制 (The Orchestrator Fix)
#### [MODIFY] `.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py`
我們將徹底改寫 Orchestrator 中負責拋出 `sys.exit(0)` 打斷並要求 LLM 工作的 `stdout` 報錯流。
- **優化 State 2 到 State 3 的無縫推進 (Seamless Cascading)**:
  - 解除 Python 在生成最後一場 `Facts.md` 後強制停止 (`sys.exit(0)`) 的瓶頸。未來，只要 Python 把所有的 Facts 準備好，將會一氣呵成自動墜入 `State 3` 的判斷，直接拋出針對 Race 1 的分析要求指令，省卻一次不必要的人工重新啟動。
- **Batch 0 (戰場全景) 喚醒**:
  - Python 將印出這段指令：`🚨【HKJC HORSE ANALYST 啟動要求】請分析 Race X 戰場全景。你必須在思考標籤 <thought> 內執行 [Step 0 步速瀑布] 推理，引用數據判定 Pace Type，才可填寫 JSON 的 speed_map。`
- **Batch 1~N (馬匹獨立分析) 喚醒**:
  - Python 將印出這段硬性指令：`🚨【HKJC HORSE ANALYST 啟動要求】請分析 Race X Batch Y。⚠️ 絕對強制約束：你必須完全依照 hkjc_horse_analyst 設計的流程進行以下五步分析：`
    `1. 分析「完整賽績檔案」，評估哪一場賽事符合「寬恕認定」條件，或判斷哪一場賽績可作為指標「基準」。`
    `2. 嚴格執行 hkjc_analyst 規範的「馬匹分析」演算邏輯 (包含 Step 0-14 的 Evidence Anchors)。`
    `3. 執行 hkjc_analyst 設計的「評級矩陣」打分與理據論述。`
    `4. 依據上述分析與我們要求的標準格式，填寫法醫級「核心邏輯」。`
    `5. 運用 analyst 深度思維，針對每匹馬提取並總結出：「- **最大競爭優勢:」與「- **最大失敗風險:」。`
  - 加上這 5 點無法敷衍的操作指示後，IDE Agent 的運算權重會被徹底鎖定在 Analyst 的法醫級思維上，且由於我們承諾永遠採用「IDE 模式 對話指導」，這個解法是唯一能把 Analyst 鎖死在流程裡的途徑。

### 階段二：強化 QA 拒絕淺層廢話與程式化防跳步 (The Gate & Schema Fix)
如果 IDE Agent 試圖敷衍跳步，Python 不僅要靠提示詞，還要靠**物理結構**與**演算法把關**來徹底阻絕。

#### 1. JSON Schema 強制填充 (防止 skipping steps)
- **變動**：修改 `hkjc_orchestrator.py` 對 JSON 格式的要求。
- Python 會強制要求 `Race_X_Logic.json` 在每匹馬的資料中，除了 `core_logic` 與 `rating_matrix` 外，還必須具備額外的證據鍵值，例如：
  - `"evidence_step_0_14": "..."` (強制記錄 Step 0-14 擷取的物理起點)
  - `"forgiveness_target": "..."` (強制認定寬恕場次)
- 如果 LLM Agent 偷懶跳過了這些分析，這個 JSON 鍵值就會是空的。Python 會在第一道防線直接拋出 `Schema Error`，不准推進。

#### 2. 定量事實比對演算法 (Quantitative Fact Checking)
- **變動**：增強 `completion_gate_v2.py`，加入「評級矩陣與理據的錨點比對」。
- 當 Agent 在 JSON 中填寫 `rating_matrix` 的 `reasoning`，Python 會執行正則掃描 (Regex Scan)，尋找這個理據是否有引用 `Facts.md` 中的數字 (例如 "22.50", "1400m", "+15lb", "Type B")。
- 如果 Python 發現你的「評級理據」全都是文字形容 (例如 "狀態很好", "有機會")，而缺乏任何量化基準，會立刻拋出 `QA Error: 評級矩陣理據缺乏量化數據支撐`。這確保了「打分與理據論述」絕不是空口說白話。

#### 3. 新增相似度檢測 (Cross-Horse Similarity Enforcement)
- 在驗證 `Analysis.md` 內容時，寫一個檢測器比對同場賽事所有馬匹的 `核心邏輯`。
- 計算 N-Gram 相交率 (例如 Jaccard Similarity)。如果同場有馬匹的文字與其他馬匹相似度高於 50% (例如：每一匹馬都出現「近期表現一般，後上走勢尚可」)，立即亮起紅色警報：`Exit Code 1 -> LAZY-003: 發現高度重複性罐頭字眼，Analyst 介入失敗！`

### 階段三：完美映射到輸出模板 (Template Reflection)
#### [MODIFY] `.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/compile_analysis_template_hkjc.py`
為了讓 LLM 收心寫出的 Step 0-14 證據與「競爭優勢/失敗風險」不被白費，Python 負責完美搬運：
- **變動**：更新編譯腳本，當它讀取 JSON 時，會將 `"advantages"` 與 `"disadvantages"` 直接生成為 Markdown 中的顯眼特徵列。
- 將 `"evidence_step_0_14"` 封裝成一個 `<details><summary>🔬 法醫級推演錨點 (Step 0-14 Evidence)</summary>...</details>` 的折疊區塊，接在核心邏輯的下方。
- 這樣既不會干擾主視覺的閱讀節奏，又能保留證據鏈供未來覆盤使用。這確保了 Analyst 所做的每一個步驟都「有圖有真相」地反映到最終報表。

### 階段三：真實示範 V8 完整生命週期 (Execution Proof)
#### [MODIFY] 刪除 `Race_4_Logic.json` & 重建 `Race 4 Analysis`
為了證明這個 Flow 能正確 Engage Analyst，我將：
1. 清除之前為了跳步而生成的虛假 Race 4 JSON。
2. 啟動已加入最新引導提示的 `hkjc_orchestrator.py`。
3. 嚴格扮演 Analyst，根據真實的 `Race 4 Facts.md`，撰寫出包含了真正起步位置、降班優勢、外檔風險的法醫級針對性評論。
4. 提供最終的 `04-12_ShaTin Race 4 Analysis.md` 讓你親自審閱 Analyst 的深度。

---

## 3. 執行路線與驗證方法 (Verification Plan)

如果你同意上述深度整合的計畫：
1. **立即動工**：我會馬上修改 `hkjc_orchestrator.py` 的 stdout 區塊，以及 `completion_gate_v2.py` 的相似度比對模組。
2. **自動觸發防呆**：如果你試著自己用腳本再次塞入罐頭字眼，全新版的 QA 將拒絕讓你推進。
3. **成果展示**：我會向你展示一次原汁原味的 Race 4 完整迴圈，從 Terminal 拋出「啟動 Analyst」到我給出完美推理的過程。
