# 🤖 ENGINE ADAPTATION(P31 — 2026-04 新增 — Priority 0)

> **歷史教訓:** Gemini 引擎傾向在 Batch 1 完成後停機等用戶,或將所有賽事數據合併到一個 tool call。
>
> **適配規定(Priority 0):**
>
> 1. **LOOP_CONTINUATION_MARKER:**
>    喺每場賽事完成後,你必須喺內部思考中寫:
>    `CONTINUE_LOOP: Game [N] done, [M] games + PARLAY remaining. Proceeding to Game [N+1].`
>    **呢個標記嘅目的**係提醒你自己仲有嘢做,唔好停機。
>
> 2. **PREMATURE_STOP_GUARD:**
>    若你準備向用戶輸出文字回覆,必須先問自己:
>    「NBA_Analysis_Report 入面有冇 Parlay 組合?」
>    → 若冇 → ⛔ 你仲未寫完!返回循環繼續!
>
> 3. **GEMINI ANTI-LAZINESS REINFORCEMENT:**
>    - **禁止「因為該場無優質 Leg 所以簡寫」:** 每場賽事必須完整分析所有生小 props。
>    - **字數門檻:** 每場賽事分析 ≥1500 字（含中英文混合計數）。
>    - **骨架 [FILL] 零容忍:** 若寫完嘅分析仍然包含 `[FILL]` → 立即補回。

# 🚨 INJURY_GUARD_PROTOCOL (新增 — Priority 0)

> **歷史教訓:** 抓取資料有時會包含長賽季報銷的球星(如 Ja Morant)，如果只盲目看 L10 場均高就選他，會發生嚴重的常識錯誤(Hallucination)。
>
> **強制規定(Priority 0):**
> 1. **STATUS CHECK:** 必須手動或用腳本檢查 API `status` 欄位（即使其回傳 `None` 或沒有明確寫明）。
> 2. **常識與知識庫 (World Knowledge Override):** 若遇上頂級球星，分析前絕對要套用常識判斷他是否已受傷報銷，嚴禁盲目把傷兵放進分析報告！

# 🚨 DATA_VISIBILITY_PROTOCOL(P33-WLTM — 新增 — Priority 0)

> **歷史教訓:** LLM 可能為咗慳 Token,將「L10 逐場」原始數組隱藏,或者只係喺第一個 Combo 寫出深度分析,後續組合(Combo 2 onwards)經常被求其帶過，甚至把兩支 Leg 合併在一個表格內，或者以 Python string f-template 自動灌水。
>
> **強制規定(Priority 0):**
> 1. **EXPLICIT L10 ARRAY:** 每一個 Leg(不論是 Combo 1 還是 Combo 2, 3)必須明確印出 `L10 逐場:[數組]`,絕對不允許用「均值」替代或者隱藏。
> 2. **DEEP ANALYSIS FOR ALL COMBO LEGS:** 所有後續 Combo(Combo 2 onwards)嘅 Leg 分析,必須與 Combo 1 具備同等深度,強制作者包含:「核心邏輯」、「⚠️ 最大不達標風險」與「💪 克服風險信心度」。嚴禁輕輕帶過!
> 3. **FULLY SEPARATED COMBO BLOCKS (反腳本與反合併):** SGM 2-Leg 以上組合，必須為每一支 Leg 開設**獨立的板塊與獨立的 `| 🔢 數理引擎 | 🧠 邏輯引擎 |` 表格**，例如：`### 🧩 Leg 1: ...` + 它的表，接著 `### 🧩 Leg 2: ...` + 它的表。嚴防兩者塞進同一個表格內。
> 4. **ANTI-SCRIPTING NATIVE LOGIC:** 絕不允許使用 Python `{placeholder}` 字串模板來自動產出分析！必須針對每場球員對位原生生成香港語境下的深度文字。

# 🚨 OUTPUT_TOKEN_SAFETY(P28 — 2026-04 新增 — Priority 0)

> 1. **DEFAULT: 每次處理 ≤3 場賽事**（標準）。環境掃描通過後可以使用 3。
> 2. **環境掃描失敗 → 每次 2 場**（安全 fallback）。
> 3. **Parlay 組合必須為獨立 tool call**。
> 4. **Token 壓力自測**:若壓縮內容 → 立即停止拆到下一個 batch。

# 🛡️ JIT_TEMPLATE_CHECKPOINT（P33 — 移植自 HKJC — Priority 0）

> **歷史教訓:** 隨住 batch 處理場次增多，LLM 對模板結構嘅記憶會逐漸偏移（Template Drift），導致後期場次嘅輸出結構同前期唔一致。
>
> **強制規定:**
> 1. **每場分析前強制 `view_file`**: 在開始每場賽事嘅 Analyst 分析前，必須重新讀取 `nba_analyst/resources/05_output_template.md`（至少前 50 行）。
> 2. **模板結構核對**: 確認當場輸出結構同模板一致 — 3 個組合（🛡️ 1 + 🔥 2 + 💎 3）、每 Leg 8 大區塊、Python 推理 + Analyst [FILL]。
> 3. **若發現偏移**: 立即停止並修正，唔好等到 Compliance 先發現。

# 🚨 GAME_4_HARD_SPLIT（P34 — 移植自 HKJC — Priority 0）

> **歷史教訓:** NBA 一晚可能有 10+ 場賽事。Context Window 嘅壓力會喺第 4-5 場開始導致分析質量急劇下降。
>
> **強制規定:**
> 1. **每完成 4 場分析**後，強制切割 Session。
> 2. **Handoff Prompt 自動生成**: 切割前輸出以下內容俾用戶:
>    ```
>    🔄 SESSION SPLIT — Game 4 完成
>    ✅ 已完成: Game 1-4 [列出]
>    ⏳ 待完成: Game 5-N [列出]
>    📂 檔案位置: {TARGET_DIR}
>    ➡️ 請開啟新 Session 並說「繼續分析 {ANALYSIS_DATE} NBA」
>    ```
> 3. **Session State 持久化**: 將進度寫入 `{TARGET_DIR}/_session_state.md`。新 Session 嘅 Session Recovery 會自動偵測。

# 🛡️ ANTI_DRIFT_ZERO_TOLERANCE（P35 — 移植自 HKJC — Priority 0）

> **歷史教訓:** LLM 經常喺多場分析後開始「創作」新欄位名、省略原有區塊、或改變 emoji 用法。
>
> **強制規定:**
> 1. **禁止新增模板中冇嘅欄位或 emoji 標記**。
> 2. **禁止省略模板中有嘅欄位**（即使該場數據不足，也要標註「數據不足」而非刪除欄位）。
> 3. **禁止改名**: 「數理引擎」唔可以變「數據引擎」、「組合結算」唔可以變「組合分析」等。

# 🚫 BATCH_GENERATION_BAN（P37 — 2026-04-08 新增 — Priority 0）

> **歷史教訓:** LLM 為咗趕進度，寫咗一個 Python 批量生成腳本（`generate_md_drafts.py`），一次過生成 3 場分析報告。結果報告內容全部係 placeholder（「數據模型強烈支持」「正常發揮」），冇任何真正分析，Adj Prob 數值亦因為 formatting bug 顯示為 9800% 等荒謬數字。
>
> **強制規定:**
> 1. **絕對禁止用 Python script 批量生成分析報告**: 每場 `Game_*_Full_Analysis.md` 必須由 LLM 逐場獨立撰寫，禁止 for-loop 自動灌入。
> 2. **絕對禁止 Generic Filler**: 以下字眼出現即為違規 — 「數據模型強烈支持」「正常發揮」「依靠高 L10 保底」。每個 Leg 嘅核心邏輯、對位分析、風險評估必須針對該球員同該場比賽嘅具體情況撰寫。
> 3. **One-Game-at-a-Time 硬性規定**: 每次只處理一場賽事。完成一場 → 由用戶確認或自動驗證 → 先開始下一場。嚴禁同時處理多場。
> 4. **自檢觸發器**: 若你正在準備寫一個 `for game in games:` 循環去生成報告 → ⛔ STOP → 你已違規 → 逐場手動分析。

# 🎯 BET365_PARSER_LEARNINGS（P38 — 2026-04-08 新增 — Priority 0）

> **歷史教訓:** `bet365_parser.py` 喺提取低門檻盤口（PTS 5+, REB 3+）時出現嚴重錯配，導致報告中嘅賠率同 Bet365 實際盤口唔符。問題根源係 Parser 將低數值 Line Markers（如 3, 5）誤認為球衣號碼（Jersey Number），並喺 odds 數量少於球員數量時使用錯誤嘅映射邏輯。
>
> **已修復嘅核心問題:**
> 1. **Line Marker 誤判**: `ALL_LINE_MARKERS` 必須包含所有可能嘅低門檻數值（1, 2, 3, 5, 7, 10, 13, 15, 17, 20, 25, 30, 35, 40, 45, 50），否則 Parser 會將 `3` 當成球衣號碼消費掉。
> 2. **Offset 映射邏輯**: 當 `n_odds < num_players` 時，代表頂級球員（排列在前）嘅低門檻盤口未開放（因為對佢哋嚟講幾乎必中）。賠率應映射到**最後 N 位球員**（`offset = num_players - n_odds`），而非前 N 位。
> 3. **Bet365 球員排序規則**: Bet365 每個 Category（Points/Rebounds/Assists）內嘅球員排列係「高產量優先」。即 PTS 最高嘅排第一，最低排最尾。呢個排序同 Roster 順序無關。
>
> **驗證規則（每次解析後強制執行）:**
> 1. 解析後必須 spot-check 至少 3 位球員嘅低門檻賠率（PTS 5+, REB 3+）同 Bet365 原始文本對齊
> 2. 若發現「低門檻盤口不存在」（如 Scottie Barnes PTS 5+），代表該球員太強而未開放該盤口，係正常現象，**唔好強行填入賠率**
> 3. 若 `n_odds > num_players`，代表解析錯誤，必須立即停止並排查

# 🎯 MILESTONES_SOURCE_FIRST（P40 — 2026-04-09 新增 — Priority 0）

> **歷史教訓:** Bet365 AU NBA Index Page 有兩組外觀極似但數據完全唔同嘅 Tab：
> - `Points O/U` → 產出帶 `.5` 嘅主盤口（12.5, 15.5, 20.5），這些係 Over/Under 盤
> - `Points` → 產出**整數階梯 Milestones**（10+, 15+, 20+, 25+），呢啲先係我哋要嘅
>
> 之前個 Extractor 去錯咗 `Points O/U` Tab，導致報告出現 `12.5+` 呢啲 Milestones 裡面唔存在嘅選項。
>
> **核心原則：Source-First（源頭正確 > 事後過濾）**
>
> **Bet365 AU 正確 Tab 名稱（2026-04-09 截圖確認）：**
>
> | 用途 | ✅ 正確 Tab | ❌ 錯誤 Tab | 原因 |
> |------|------------|------------|------|
> | Player Points | **`Points`** | `Points O/U` | `Points O/U` 產出 .5 線 |
> | Player Rebounds | **`Rebounds`** | — | 只有一個 |
> | Player Assists | **`Assists`** | — | 只有一個 |
> | Player 3PM | **`Threes Made`** | — | 只有一個 |
> | Game Lines | **`Game`** | — | 主頁默認 |
>
> **強制規定:**
> 1. **Tab 選擇鎖定**: `claw_bet365_odds.py` 嘅 `prop_tabs` 列表必須設為 `["Points", "Rebounds", "Assists", "Threes Made"]`。**嚴禁使用 `Points O/U`**。
> 2. **`.5` = 去錯 Tab 警報**: 若提取後嘅 JSON 出現任何帶 `.5` 嘅盤口 key（如 `"12.5"`），`bet365_parser.py` 必須打印 `⚠️ WRONG_TAB_DETECTED: 發現 .5 盤口，極可能去錯咗 Points O/U tab`，並要求 USER 重新 click 正確嘅 `Points` tab。
> 3. **顯示格式**: SGM 分析報告中嘅 `line_display` 只准出現整數格式（`10+`, `15+`, `20+`）。出現 `12.5+` = 違規。
> 4. **提示指引**: 當 `claw_bet365_odds.py` 提示 USER 手動 click tab 時，必須同時顯示 `⚠️ 請確認係 "Points" tab，唔係 "Points O/U" tab！`。

# 🔧 PIPELINE_QUALITY_IMPROVEMENTS（P41 — 2026-04-08 新增 — Priority 1）

> **Session Review 觀察到嘅改善項目:**
>
> 1. **Edge 數值格式統一**: `generate_nba_auto.py` 嘅 `python_suggestions` 入面 `edge` 值必須以**百分比整數**存儲（例如 `9.54` 代表 +9.54%），而非小數形式（`0.0954`）。LLM 讀取小數時會錯誤顯示為 954%。
>    - **驗證方法**: `edge` 值應介乎 -50 到 +50 之間，超出範圍即為 bug。
>
> 2. **報告輸出格式**:
>    - **逐場分析**: `Game_{TAG}_Full_Analysis.md`（Markdown，方便閱讀同 IDE 預覽）
>    - **全日 SGM 匯總**: `NBA_All_SGM_Report.txt`（所有場次 × 所有組合嘅完整列表）
>    - **穩膽 Banker 匯總**: `NBA_Banker_SGM_Report.txt`（只列出每場組合 1 穩膽 + Top Banker Legs + 跨場 Parlay 建議）
>    - **⚠️ 兩份 .txt 匯總報告係 Pipeline 最終輸出嘅必要步驟**，完成所有逐場分析後必須生成。
>
> 3. **球員歸隊 Override**: 若 `nba_api` 嘅 Roster 數據將球員標記為 `team: "?"`，應建立 `team_override.json` 手動處理（例如交易後尚未更新嘅球員）。
>
> 4. **Data Brief Flat Summary**: 建議喺 Data Brief JSON 頂層加入 `quick_scan` 欄位，列出所有 Edge > 5% 嘅盤口嘅扁平化摘要，方便 LLM 快速掃描而毋需深入嵌套結構。

# 🧠 ANTI_RUBBER_STAMP + MUST_RESPOND（P36 — V5 新增 — Priority 0）

> **歷史教訓:** V4 架構令 Python 做晒所有決策（揀 Leg、組 Combo、寫核心邏輯），LLM 只係填寫 `[FILL]` 佔位符。結果 LLM 永遠唔會真正 disagree Python，變成 Python 嘅「公關部門」。
>
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

