## Step 2-3: 逐場賽事循環 (Per-Game Pipeline Loop)

> [!CAUTION]
> 🔒 **單場沙盒鎖 (Single-Game Sandbox Lock)**
> 嚴禁合併賽事分析。必須做到「一場賽事 = 一次獨立 Extractor 提取 = 一次獨立 Analyst 呼叫 = 一個獨立輸出檔案」。
> 即使你收到用戶匯總版的 `NBA_Data_Package_Auto.md`,該檔案通常只包含盤口與傷缺。**你必須強制呼叫 `nba_data_extractor` 補齊每場賽事的球員 14 項 L10 數據卡**,否則嚴禁進入 Analyst 分析階段 (數據包防騙協議)。
> 嚴禁一次過將所有賽事嘅數據 dump 畀 Analyst。逐場獨立執行「提取 → 驗證 → 分析 → 自檢 → 存檔」。

**進度控制**:
- 每場賽事完成後,執行 Sub-Step 3D 賽事間自檢,通知用戶結果。
- **每完成 3 場**後,額外強制停頓問用戶:「已完成 Game 1-3,是否繼續分析 Game 4-6?」
- ≤3 場 → 逐場自檢後直接完成,進入 Step 4。

**Context Window 提醒**:若 context window 接近上限,主動建議用戶開啟新 session。Session Recovery 會偵測已完成場次。

**📖 Smart Slice Protocol(Per-Game Data Loading):**
分析每場賽事時,**只傳遞當場嘅數據卡給 Analyst**:
```
分析 Game N 前:
  1. 只提取本場 Meeting Intelligence + Player-Level 數據卡
  2. 唔好包含上一場/下一場嘅數據
  3. 每場完成後,該場數據應從 context 中自然淡出

⛔ 嚴禁:一次過將所有賽事嘅數據 dump 畢 Analyst
✅ 逐場獨立執行「提取 → 驗證 → 分析 → 自檢 → 存檔」
```

**🔒 COMPLETION_GATE(分析完成門與驗證攔截閘):**
每場賽事完成(Agent 返回結果)後,存檔前必須強制執行以下 Python 驗證:
🚨 **你必須強制自己 run `python3 .agents/scripts/completion_gate_v2.py <你的檔案> --domain nba` 進行檢驗。不過關不准推進到下一場！**
如果檢驗失敗 (出現 `❌ [FAILED]`)，你已違規 → 立即根據報告內容自行修正，並重新執行 validator 直到 `✅ [PASSED]` 為止！只有通過測試才可以推進到下一場。

### Sub-Step 2A-Pre: 歷史交叉驗證（本場 — P35 新增）

> **設計理念:** 受 ECC `search-first` 啟發。每場賽事提取前，先查詢歷史對位數據。
> 完整 checklist 見 `shared_instincts/intelligence_checklist.md`。
> **此步驟依賴 MCP。若 MCP 不可用 → 自動跳過。**

**若 MCP Servers 可用，對本場球員執行 Tier 2 歷史驗證：**
1. `read_query`: 球員 vs 對手歷史 Props 命中率
2. `read_graph`: 球員傷病 Timeline + 復出 usage 變化
3. `read_query`: B2B 歷史達標率（若為 B2B 場次）
4. `search_nodes`: 防守大閘效應

**將結果加入本場數據包頭部：**
```markdown
## 歷史對位 Pattern（Tier 2 — MCP）
- {PLAYER_1} vs {OPPONENT}: [Props 命中率 X%]
- {PLAYER_2} B2B: [達標率 X%]
- 防守大閘: [{DEFENDER} 限制 -X% usage]
- **Intelligence Confidence: [🟢/🟡/🔴]**
```
MCP 不可用 → 跳過，標記 `Intelligence Confidence: 🟡 MEDIUM`。

### Sub-Step 2A: 呼叫 NBA Data Extractor（本場）
指示 Extractor 只提取當前一場賽事嘅數據,等待輸出結構化數據包。

**🎯 Bet365 盤口整合（Sub-Step 2A 強制附加 — Claw V8 Zero-Navigation ONLY）：**
> Extractor 會執行 `claw_bet365_odds.py`（Claw V8）透過 Comet CDP **純讀取** Player Props。
> **V8 架構：USER 手動 click tab → CDP 純讀取 DOM → 零 navigation。**
>
> **執行指令** (必須使用絕對路徑):
> ```bash
> python3 "./.agents/skills/nba/nba_data_extractor/scripts/claw_bet365_odds.py" \
>   --output "{TARGET_DIR}/bet365_all_raw_data.json"
> ```
>
> **🚨 Zero-Navigation 規則（Opus 實測驗證）：**
> - ❌ **嚴禁** `page.goto()` / `el.click()` / `page.mouse.click()` / `location.href`
> - ✅ **只准** `page.evaluate(() => document.body.innerText)` 純讀取
> - ✅ 由 USER 手動 click 4 個 Tab（`Points` / `Rebounds` / `Assists` / `Threes Made`）
>
> **🎯 Tab 選擇（P40 — Milestones Source-First）：**
> - ✅ `Points` = Milestones (10+, 15+, 20+) — 呢個先係正確嘅！
> - ❌ `Points O/U` = 主盤口 (12.5, 15.5) — **嚴禁使用**
>
> 若提取成功，JSON 會被保存至 `{TARGET_DIR}/bet365_all_raw_data.json`。
> **若提取失敗** → 報告 `odds_not_found` → 通知用戶協助解決，**不得繼續分析**。
> 嚴禁使用估算盤口或 Extractor Only Mode 作為 fallback。

### Sub-Step 2B: 數據品質驗證(本場)
按照 `resources/01_data_validation.md` 執行所有驗證。將本場數據追加至 `TARGET_DIR/NBA_Data_Package.txt`。

### Sub-Step 2C: Python 數據包生成 (V5 — Data Brief)

> [!IMPORTANT]
> **V5 架構核心改變**: Python 只負責「數據供應」，唔負責「分析決策」。
> 輸出格式從 `Skeleton.md`（含 [FILL] 佔位符）改為 `Data_Brief_{TAG}.json`（純數據 + 建議池）。

執行 `generate_nba_auto.py` 生成所有場次嘅數據包：
```bash
python3 generate_nba_auto.py
```
此命令會：
1. 抓取 nba_api 真實 L10 gamelog + 球隊進階數據
2. 計算所有球員 × 所有 Bet365 盤口嘅完整 8-Factor Adjusted Win Prob
3. 為每場賽事生成獨立嘅 `Data_Brief_{TAG}.json`

**Data Brief JSON 包含：**
- `players` — 所有球員 × 所有盤口嘅完整數學計算（L10 數組、CoV、命中率、8-Factor breakdown）
- `python_suggestions` — Python 基於數學排序嘅 Combo 建議（Must-Respond，見 P36）
- `team_stats` — 球隊進階數據（PACE、OFF/DEF RTG）
- `game_lines` — Bet365 讓分/總分/獨贏
- `injuries` / `b2b` — 傷病同 Back-to-Back 資訊

**Data Brief 唔包含：**
- ❌ 核心邏輯敘事（由 LLM 原生撰寫）
- ❌ Combo 選擇決定（由 LLM 自主判斷）
- ❌ `[FILL]` 佔位符（V5 已完全廢除）
- ❌ Markdown 格式報告（LLM 自行輸出）

### Sub-Step 3A: LLM Analyst 獨立分析（本場 — 逐場執行）

> [!CAUTION]
> **Game-by-Game 強制執行**: 每次只處理一場賽事嘅 Data Brief JSON。
> 嚴禁一次過處理多場賽事。完成一場 → 驗證通過 → 先進入下一場。

**LLM Analyst 工作流程（每場賽事）：**
1. 讀取 `{TARGET_DIR}/Data_Brief_{GAME_TAG}.json`
2. 執行 **Must-Respond Protocol（P36）**：回應 `python_suggestions.top_legs_by_edge` 前 5 名
3. 獨立審視所有球員盤口數據，運用籃球知識分析
4. **自主構建 3+1 個 SGM 組合**（唔受 Python 建議綁定）
5. 為每個 Leg 撰寫**原生核心邏輯**（唔可照抄 Python 嘅 eight_factor breakdown）
6. 輸出完整 `Game_{GAME_TAG}_Full_Analysis.md`

**Analyst 必須完成嘅分析（每場）：**
- 賽事背景分析（讓分/總分/節奏/B2B 推演）
- 傷病影響評估
- 每位有盤口球員嘅角色定位同盤口價值判斷
- SGM 組合（≥2 組：穩膽/價值/進取）+ 條件觸發 Value Bomb
- 每個 Leg 嘅獨立核心邏輯 + 風險評估 + 注碼建議
- 同 Python 建議嘅分歧標註（如有）

**Analyst 可引用嘅 Python 數據：**
- ✅ L10 數組、均值、SD、CoV（事實性數據）
- ✅ 8-Factor adjustment breakdown（作為參考輸入）
- ✅ Edge 計算結果（數學事實）
- ❌ 但唔可以直接複製 Python 嘅數學描述作為「核心邏輯」

### Sub-Step 3B: 合併輸出與歸一化
按照 `resources/03_output_format.md` 合併數據包與分析結果,存檔至 `TARGET_DIR`。

### Sub-Step 3C: 品質掃描(本場)
按照 `resources/02_quality_scan.md` **Section A + B** 執行逐場結構驗證 + 語義掃描。
(Section C + D 嘅全日品質檢查留到 Step 4 執行。)

**🔴 品質掃描連續 FAILED 2 次 — AG Kit Systematic Debugging 啟動:**
讀取 `.agent/skills/systematic-debugging/SKILL.md` → 4-Phase 除錯(Reproduce → Isolate → Understand → Fix)→ 根因記錄到 `_session_issues.md`

### Sub-Step 3D: 賽事間自檢報告(本場完成後)
讀取 `_session_issues.md` 中本場問題,按 `resources/02_quality_scan.md` 嘅 issue codes 匯報:
- **CRITICAL** → 顯示簡述 + 問用戶修正或跳過(**最多重試 1 次**)
- **MINOR** → 一行匯報 → 全部完成後統一處理
- **無問題** → 通知完成

通知後自動推進下一場。**每完成 3 場**後強制停頓等用戶確認。

### 循環完成後
1. 從所有 `Game_*_Full_Analysis.txt` 讀取候選 Legs,匯總為**全日候選池**
2. 執行 **[NBA-DA01] Parlay 多角度審計協議**:
   **Step A — Statistical Selection:** 列出最穩嘅 2-3 隻 Legs (低 CoV + 高 L10 命中率)
   **Step B — Injury & Matchup Challenge:** 對位球員、傷缺、B2B?
   **Step C — Props Line Audit:** 剔除 outlier 後仲 pass 嗎？更低 CoV 嘅替代 Line?
   **Step D — Final Parlay:** 指示 Analyst 構建跨場次 SGM 組合（≥2 組：🛡️ 1 + 🔥 2，可選 💎 3）+ 並列出被踢走嘅 Legs 同原因
3. 執行 SGP 防撞擊檢查

> ⚠️ **失敗處理**:若某場失敗,記錄錯誤並跳過,繼續下一場。

