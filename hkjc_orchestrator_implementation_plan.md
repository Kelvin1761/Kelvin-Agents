# HKJC Wong Choi Orchestrator 核心技術與實作計畫 (極致工程詳盡全集版)

**Executive Summary (執行摘要):**
本計畫書定義了 Antigravity V8 賽馬管線 (HKJC 聯動 AU Wong Choi 同步升級) 的全自動化技術藍圖。核心理念是「Python 掌握絕對控制流程，IDE 端的 HKJC Wong Choi (Agent) 負責純粹推理」。我們 **絕對不使用任何外部 Gemini API** 寫死在代碼中。取而代之，Orchestrator 會透過 `stdout` 放出指令並暫停 (`sys.exit`)，引導你 (HKJC Wong Choi Agent) 生成資料，達成「Python 發號施令 → Agent 填寫 JSON → Agent 重跑 Python 檢查」的無縫輪迴。
由 Python 全權負責排版 (`generate_skeleton.py`)、數學矩陣算分及 Top 4 排序 (`compute_rating_matrix.py`)，徹底剝奪 LLM 的算術與排版能力以杜絕格式崩潰。引入兩大防護機制：其一是每一批次強制在背景執行 QA (Self-Correction Loop) 與「三失效暫停極限機制 (3-Strike Limit)」；其二是重構 Prompt 為「綜合思維 (Chain of Synthesis)」，糾正孤立放大的通病。

這個計畫彙整了我們所有的技術共識，將詳細說明 `hkjc_orchestrator.py` 的絕對架構。本藍圖將作為終極施工圖檔，展示 Python 如何透過與 IDE Agent 交互，將零散的 Python 外掛程式（擷取、Skeleton 生成、矩陣計算、合規 QA）無縫串接為防幻覺、防降級的全自動流水線。

> [!IMPORTANT]
> 這是包含所有技術細節、毫無刪減的終極建置藍圖。確認後，我將會按此計畫立刻編寫及部署。

---

## 🏗️ 核心管線：Python-Driven IDE Agent State Machine

整個 Orchestrator 採用純本地 Python 腳本 (`hkjc_orchestrator.py`) 作為主控端，並**不包含任何外部 API 調用**。它是利用「退出並印出提示詞 (stdout Delegation)」的方式，指揮現身於對話框的你 (Agent) 作出行動。這徹底杜絕了人工介入時的手誤，並根除了 LLM 自由發揮所造成的 Markdown 排版錯亂。

### 📌 階段一：事實擷取與骨架建設 (State 0, 1, 2)
這是純 Python 執行層段，LLM 零介入。目的是為分析準備最剛硬的資料地基。

1. **State 0 (原始數據擷取):** 
   - 接收 `--url` 與 `--races`，自動建立對應的 `YYYY-MM-DD_[Venue]_Race_X` 目錄。
   - 檢查目標資料庫中的 `[排位表.md]`、`[賽績.md]` 及出賽馬匹 PDF。
   - 缺失時，Python 於背景自動調用：`subprocess.run(["python3", ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts/batch_extract.py", ...])` 爬取資料。
2. **State 1 (情報判讀):** 
   - 查找根目錄是否存在 `_Meeting_Intelligence_Package.md`。若無，暫停提示人類或透過 API 要求總體場地/天氣分析。這是後續決策的定錨點。
3. **State 2 (Facts 事實生成與 Skeleton 骨架強制排版):**
   - **生成 Facts:** 自動呼叫 `.agents/scripts/inject_hkjc_fact_anchors.py`，把原始排位表及歷史賽績洗練成高密度的 `Race X Facts.md`。
   - **骨架搭建 (Template Control):** 隨即調用 `.agents/scripts/generate_skeleton.py --mode hkjc <Facts.md>`。此腳本將自動產出一個帶有所有表格、Emojis，及精確 `[FILL]` 佔位符的純淨 `Analysis.md` 檔案 (含有完整的 第一、二、三部分)。
   - **優勢:** LLM 往後不再需要輸出 Markdown。排版完全由 Python 保障。

---

## 🧠 階段二：LLM 智庫串接、批次剖析與 QA 阻火牆 (State 3)
這是架構的核心所在。Python 會透過終端機輸出 (stdout)，嚴格控制提供給大腦 Agent 的上下文 (Context)，強逼 Agent 寫入純 JSON，並藉由 QA 機制建立對話框內的自我修正迴圈 (Self-Correction Loop)。

### 🏁 步驟 A: Batch 0 戰場全景 (Battlefield Panorama)
- **行動要求:** 當找不到天氣與偏差檔案時，Python 腳本會中止 (`sys.exit(0)`) 並印出：`🚨 State 1 要求：請大腦 Agent 判定步速預測與軌道偏差。`
- **注入:** Agent 將其寫入特定暫存檔後，重跑 Python，Python 便會將其覆寫入 Skeleton 首個區塊 `[第一部分] 🗺️ 戰場全景` 內的 `[FILL]`。

### 🔪 步驟 B: Batch 1 至 Batch X (逐批馬匹法醫級剖析)
為消除大腦常見的「記憶衰退與偷懶效應」，Python 會將 14 匹馬切割成「每次最多 3 匹馬」要求 Agent 處理。

1. **Agent Prompt 指派 (stdout):** 
   - 當發現缺少某批次（例：第 1 至 3 號）馬匹的 JSON 分析檔時，Python 發射中斷要求：
     `🚨 LLM Agent 請注意：請讀取這 3 匹馬的 Facts.md，並依據 Batch 0 結果，生成 JSON 檔案！`
   - **Prompt 指令優化 (Chain of Synthesis - 解決孤立邏輯過度放大):** 這項重大優化亦將同步套用於 AU Wong Choi 管線，確保全球賽事分析品質一致。
     - 過去，LLM 會把「核心邏輯」當成一篇獨立散文來寫，導致若逢莫雷拉被指派為方嘉柏主帥等單一因素，LLM 就會將其寫得像驚天大發現。
     - **「核心邏輯」重新定義為最終戰力摘要結語 (Summary over Isolation):** 在新架構下，我們會在要求 Agent 生成 JSON 前強制作出先後順序：要求 Agent 先客觀填寫「評級矩陣 (Matrix)」、「賽績解讀」、「賽績線分析」。在回答的最後一個 JSON Key 才保留給「核心邏輯」，並且明確指示指令為：*『你的【核心邏輯】不能是一兩點普通騎練訊號的延伸，它必須是"上方你所填寫的馬匹分析、歷史賽績包裝、以及評級矩陣結果的最終戰力摘要結語"』*。
     - 這會將「核心邏輯」變成一個大局 Summary。如此一來，如果該駒僅有莫雷拉做主帥（訊號好），但在 Matrix 或前速數據極差，LLM 的核心邏輯就會客觀地寫作：「雖然有強烈騎練訊號，但綜合前速與過往表現，此駒劣勢過大」，而非盲目推崇。
     - **字數下限要求:** 為了保證「核心邏輯」具備足夠的深度與論證過程，我們明確規定其長度必須介乎 **100 至 200 字** 之間，配合大局觀作充分伸延。
   - **強制 JSON 鍵值對鎖定 (Strict Schema Enforcement 防跳步斷層):** 為了確保 Analyst (分析師) 過去所設計的每一套精闢邏輯（如：步速適應、寬恕因素、同程往績）都不會被 Wong Choi 偷懶省略，Python 印出的指令會**硬性規定一個不可改變的 JSON 結構**。
     - **分析子項:** JSON 內必須強制包含 `["pace_adaptation", "forgiveness_factors", "formline_strength", "gear_changes"]` 等獨立的文字欄位。
     - **評級矩陣理據 (Matrix Reasoning):** 對於 8 大評分維度，Agent 除了給出 ✅ 或 ❌，在 JSON 中還必須強制填寫對應的 `"_reasoning"` 鍵值（例如 `"pace_reasoning"`, `"form_reasoning"`, `"class_reasoning"`, `"draw_reasoning"`, `"jockey_reasoning"`, `"trainer_reasoning"`, `"gear_reasoning"`, `"stability_reasoning"` 等）。這強迫大腦解釋為何給出該符號，絕不允許無根據打分。
     - 當 Agent 填妥 JSON 時，若 Python 解析時發現**任何一個邏輯 Key 缺失或內容為空**，Python 將會直接報錯並要求重寫。這從結構上 100% 杜絕了跳步或是「只分析不看數據」的問題。
2. **Python 計算機接管 (The Calculator Pattern):**
   - Agent 寫妥 JSON 並二次執行 Orchestrator 後。Orchestrator 自動呼叫 `.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/compute_rating_matrix_hkjc.py` (演算模組)。
   - Python 將統計該匹馬的 ✅/❌ 數量，套用核心防護牆，自動計算出基礎評級 (e.g. `S` 或 `B-`)。這完全剝奪了 Agent 的算術能力，確保零運算幻覺。
3. **注入與每批強制 QA (Per-Batch Immediate QA & Self-Correction):**
   - Python 把算好的值對位注回 `Analysis.md` 該 3 匹馬的 `[FILL]` 空白處。
   - **Self-Correction (Agent 自動重試迴圈):** 若未能通過 QA，Python 會抓住 `Exit Code 1` 並且 `sys.exit(1)`，直接在對話框對 Agent 大叫出錯（列明出錯原因如字數不足）。Agent 收到錯誤信號，自然會啟動自我修復重寫 JSON，並循環觸發。
   - **【終極防偷懶：數據逼迫法 (Quantitative Evidence Lock)】:** 為了防止 Agent 寫出「字數很長，但全無內容」的廢話（例如只寫「這匹馬狀態大勇，前速極佳，值得留意」），Python QA 會加入 **Regex 數字與賽績校驗**。
     - **目標精準化：** 這項檢測**只會套用於特定的大局欄位**（例如「賽績線探討」與最終的「核心邏輯」）。至於像「寬恕因素」這類可能只需要定性描述的欄位則不受限制。
     - 它會掃描該些 JSON Key 的文字內容，若沒看見小數點（代表無引用 L400 段速如 22.14）、沒有連字號（代表無引用走位如 1-2-1），Python 將判定其為「空泛吹捧 (Fluff)」，強行退回要求 Agent 補上實質數據。這迫使 Agent 必須雙眼盯著 Facts.md 寫作。
   - **【終極防偷懶：違禁詞封殺機制 (Banned Words Regex)】:** Python QA 會自動過濾大腦最喜歡用來偷懶的字眼。一旦偵測到 `["同上", "如上所述", "參考上文", "不再贅述", "略"]` 等敷衍詞彙，直接視作 QA 失敗，連字數都不去量了，立刻發還重作。
   - **【新增】3-Strike Manual Fallback Protocol (三失效暫停求援機制):** 若同一個 Batch 連續 **3次** 都未能通過 QA，為防機器人在如「新馬賽 (無過往賽績)」的情況下陷入無解死循環，Python 將強行終止重試並印出中斷警告：`🚨 [CRITICAL ALERT] 連續 3 次 QA 失敗，恐為極端賽事狀況！請人類或 Agent 介入調查`，待手動接手排除障礙。

---

## 🏆 階段三：程式裁定與最終決策 (State 4)
當全數 14 匹馬完成 Batch 剖析與嚴格的 QA 檢測後，進入收尾階段。

1. **Python 自動裁定 Top 4 排位 (Math Sorting):**
   - Agent 不能再憑主觀感覺選馬。Orchestrator 會直接對這 14 匹馬在 `compute_rating_matrix` 所得到的分數與 ✅ 數量進行**數學排序算法 (Sort)**。
   - Python 自動選出榜首的 4 匹馬，並直接將其名字與評級打進 `Analysis.md` 的 `[第三部分] 最終決策` 的對應行。
2. **最終判定呼叫 (The Final Verdict Justification):**
   - 若缺失最終判定，Python 印出提示中止程序：「系統已客觀鎖定這 4 匹馬為 Top 4。LLM Agent 請為他們寫出 50字的『核心理據』」。
   - 此舉極大限度地確保了名單完全符合戰力公式，同時又具備極高質素的人性化解說。
3. **資料庫組裝與報告產出:**
   - Python 程式迴圈自動在 `Analysis.md` 的最底部生成 CSV 字串。
   - 執行 `.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/generate_hkjc_reports.py` 輸出日終 Excel 報表。
   - 執行 `session_cost_tracker.py` 總結 API 代幣消耗。
   - Process 完美落幕。

---

## 🔌 與現有 HKJC Wong Choi Agent 的無縫整合與鎖死機制 (Integration & Engagement Lock)

你問到一個非常實戰的問題：「如何確保這套 Orchestrator 必定被觸發，不會出現 Agent 跑錯路的情況？」
為此，我們將會對 Agent 本身的源代碼（`hkjc_wong_choi/SKILL.md` 與 `resources/00_pipeline_and_execution.md`）進行以下三個徹底的改寫：

1. **改寫 Intent Router (First Action Rule 鐵律):**
   - 舊架構下，Agent 收到分析指令後，會按部就班自己閱讀 `00_pipeline_and_execution.md` 逐行執行。
   - **新架構**：我們會在 `SKILL.md` 的 `Critical Instructions` 加上「首條行動鐵律」：不論用戶提供的是甚麼場地或連結，只要判斷為「分析意圖」，Agent 的**第一個也是唯一一個合法動作**，就是發送 Tool Call 執行 `python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <URL>`。
2. **State Machine 的絕對防呆 (Idempotent 狀態記憶):**
   - 萬一用戶打斷了 Agent，或者 Agent 意外斷線崩潰。當你再次召喚 HKJC Wong Choi 說「繼續跑 Race 4」，Agent 再一次執行 `hkjc_orchestrator.py` 時，該 Python 腳本內建了強大的 State Machine。
   - 它會掃描資料夾，發現「Race 3 Analysis 已經存在，Race 4 跑到 Batch 1」，Python 便會**自動接軌 (Resume)**，直接從 Race 4 Batch 2 繼續 Call API。這完美確保了不管你從哪個切入點召喚，Orchestrator 永遠能找回正確進度，不會由頭重啟覆蓋檔案。
3. **消除舊的 Agent-to-Agent 委派環節:**
   - 放棄舊有的 `@hkjc horse analyst` 及 `@hkjc batch qa` 的聊天視窗委派（這些會浪費極大量 Context 且容易脫軌）。
   - 代碼將統一呼叫 `hkjc_orchestrator.py`，Wong Choi Agent 只需作為這個 Python 腳本的「指令執行者」，不斷地執行 Python -> 收取 Python 的印出要求 -> 撰寫 JSON -> 重跑 Python 的鐵血迴圈。
4. **📊 即時進度儀表板與持久化任務清單 (Live Task List & Dashboard):**
   - 關於進度顯示與剩餘工作列出，我們雙管齊下：
   - **(a) Stdout 看板：** 每次啟動時，Python 會先印出一個華麗的進度表。例如：
     ```text
     📊 執行進度 (Task List Checklist):
       [x] Race 1 分析完畢
       [x] Race 2 分析完畢
       [ ] Race 3 (進行中 - 正在等待 Batch 2 的 JSON)
           ...
     ```
   - 這個進度表不僅是給 Agent 判斷從哪裡接軌用的，同時也會顯示在你的 IDE Tool Call Output 之中，讓你一目了然。
   - **(b) 實體檔案 `_session_tasks.md` (防失憶任務清單)：** 更重要的是，`hkjc_orchestrator.py` 會在該賽日的資料夾內（如 `2026-04-12_ShaTin (Kelvin)/_session_tasks.md`）自動產生並不斷更新一份實體的 Markdown 任務清單！這份文件中會列出所有 11 場賽事、每場的所有 Batch 狀態（`[x]` 完成或 `[ ]` 待辦）。萬一對話 Context 不小心被截斷，Agent 只需要打開這個檔案看一眼，就能立刻知道「我有甚麼剩餘的任務還沒做」。

---

## 📝 總結
這份藍圖毫無死角地結合了：
1. **`generate_skeleton.py`** 確保 100% 排版不爛。
2. **`compute_rating_matrix_hkjc.py`** 確保 100% 評分不亂。
3. **Per-Batch QA Loop** 確保 100% 絕無偷懶。
4. **Synthesis Prompt** 確保 100% 邏輯連貫宏觀。
