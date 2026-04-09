
---

### 角度 4 — 泛化性審計 (Generalizability Audit)

> **確保覆盤洞見唔會太單一，要對未來分析有用。**

- 呢場暴露出嘅問題係**普遍性**嘅（會喺其他重覆出現）定**一次性**嘅（極端意外）？
- 分類:
  - 🔵 **系統性問題** (影響所有未來): e.g. 「長期高估某類型情況」
  - 🟡 **條件性問題** (特定條件下出現): e.g. 「特定場地時預測偏誤」
  - ⚪ **孤立事件** (唔需要改 Protocol): e.g. 「意外事件」
- 只有 🔵 同 🟡 嘅洞見先值得升級為 Design Pattern / SIP 修訂

---

### 角度 5 — Design Pattern Proposal (向 Agent Architect 提交)

基於以上 4 個角度嘅分析，向 Agent Architect 提交以下格式嘅改善建議：

---

### 角度 6 — 結構性事後審計 (Structural Retroactive Audit)

> **檢查原始分析有冇違反結構規則（Batch QA 會涵蓋嘅嘢）。**

**V5+ 新格式檢查:**
- `odds_source` header 係咪存在且標明 BET365_LIVE ✅？
- 引擎版本標記係咪存在？
- 若 Blowout 風險場次 → 有冇相應嘅 `[!CAUTION]` 風險標記？
- 原始分析有冇完整輸出 ≥2 個 SGM 組合？（V5+ 唔再強制 3 組，但 ≥2 係底線）
- 後續組合嘅分析深度有冇同組合 1 一致？
- 每個 Leg 嘅 `📊 數據:` 行係咪包含完整嘅 L10 數組、AVG、MED、SD？
- 每個 Leg 有冇 `✍️ Analyst 深度補充` 區塊（唔係 copy-paste Python 建議）？
- 組合結算有冇同時包含 `🛡️ 組合核心邏輯 (Python)` 同 `✍️ Analyst 組合補充`？
- 有冇使用省略語（`[同上]`、`[參見組合X]`、`...`）？

**通用檢查 (新舊格式都適用):**
- L10 逐場數組長度係咪全部 = 10？
- 防守大閘名單有冇過期球員？若有 → 標記 `[STALE_DEFENDER: 球員名 — 原因]`
- 呢啲結構性問題有冇影響分析品質同預測準確度？


```
## Design Pattern Proposal
- **Issue ID:** REF-[日期]-[編號]
- **分類:** 🔵系統性 / 🟡條件性
- **問題描述:** [一句話總結]
- **受影響嘅 Protocol:** 基礎邏輯 / SIP-DA01 / 其他
- **建議修改:** [具體改動]
- **預期效果:** [預計命中率/盲點改善幅度]
- **SIP-DA01 評價:** 有效/部分有效/無效 — [原因]
```
→ Agent Architect 審閱後決定是否納入 `design_patterns.md`


## Step 4: 深度比對(在 `<thought>` 中進行)

**數據來源優先級:**
1. 📊 `Props_Verification_{US_DATE}.json` — 自動生成嘅命中/未中判定（Ground Truth）
2. 📋 `Results_Brief_{US_DATE}.json` — 完整 Box Score
3. 📋 `PBP_Brief_{US_DATE}.json` — Play-by-Play 深度數據（若已擷取）
4. 🔍 `search_web` — 僅用於補充以上 JSON 缺失嘅資訊

按照 `resources/02_search_protocol.md` §4 嘅深度比對框架執行 4a/4b/4c 分析。

**🆕 Play-by-Play 深度覆盤（若有 PBP Brief）:**
- 若 `PBP_Brief` 存在,為每個未命中 Leg 檢查:
  - 球員逐節得分分布 → 係早段累積定係後段爆發？
  - Blowout 時間點 → 主力幾時被換落場？
  - 教練換人模式 → 有冇非常規換人影響上場時間？
- 將 PBP 發現寫入覆盤報告嘅對應 Leg 分析中

## Step 5: 輸出覆盤報告
按照 `resources/01_report_template.md` 嘅格式生成報告。

**🧠 SIP 修正方案探索(AG Kit Brainstorming — 自動觸發):**
生成 SIP 時自動讀取 `.agent/skills/brainstorming/SKILL.md`,對每個 SIP 生成 ≥2 個結構化修正方案:

| 方案 | 修改內容 | ✅ Pros | ❌ Cons | 📊 Effort |
|:---|:---|:---|:---|:---|
| A | [具體修改] | [好處] | [風險] | Low/Med/High |
| B | [替代修改] | [好處] | [風險] | Low/Med/High |

**💡 Recommendation:** [推薦方案 + 理據]

## Step 5.5: 更新 SIP Changelog
若本次覆盤提出咗 SIP 建議:
1. 檢查 `{TARGET_DIR}/_sip_changelog.md` 是否存在
2. 若不存在 → 按照 `resources/01_report_template.md` 嘅格式建立
3. 將新 SIP 追加到 changelog,狀態設為「待審批」
4. 交叉檢查歷史 SIP:若過去覆盤已提出類似建議但未被採納 → 標記為「重複出現」,提升優先級


> **P32 — Knowledge Graph 整合:** 生成覆盤報告後,使用 Memory MCP 將以下關鍵發現寫入 Knowledge Graph:
> - 傷兵狀態更新(Entity: `{PLAYER}_{DATE}_injury`,Observations: 傷兵影響上場時間/表現)
> - 防守大閘效果驗證(Entity: `defender_{PLAYER}_vs_{OPPONENT}`,記錄預測 vs 實際影響)
> - Props 命中/未命中模式(Entity: `prop_pattern_{PLAYER}_{PROP_TYPE}`)
> - 這樣下次分析時,NBA Analyst 可以先查詢 `read_graph` 發現過往傷兵狀態和防守對位效果。

## Step 5.8: Execution Journal (P26)
每次覆盤完成後,追加一行到 `{TARGET_DIR}/_execution_log.md`:
```
> 📝 LOG: Reflector 覆盤 | Date: {ANALYSIS_DATE} | Games: {N} | Props Hit Rate: {X%} | SIPs: {M} | Data Source: API/FALLBACK
```

## Step 6: 等待用戶審批
向用戶提交覆盤報告路徑同摘要,並**強制停止所有行動**。

若用戶批准 SIP 建議:
1. 讀取目標 resource 檔案
2. 按照 SIP 建議進行精確修改
3. 每個 SIP 修改後,向用戶確認
4. 更新 `_sip_changelog.md` 狀態為「已採納」

## Step 7: Reflector → Architect 回饋(Pattern 15)
若本次覆盤發現咗**新嘅設計模式或反模式**(而非僅僅係參數調整):
1. 將發現整理為標準 Design Pattern 格式:Problem / Solution / Anti-pattern
2. 通知用戶:「本次覆盤發現咗一個潛在嘅新 Design Pattern,建議提交畀 Agent Architect 入庫。」
3. 若用戶同意 → 輸出 Pattern 草稿,供 Agent Architect 審核並 append 到 `design_patterns.md`

# Recommended Tools & Assets
- **Tools**: `run_command`（執行 Python scripts + Safe-Writer Pipeline 寫檔）、`view_file`、`grep_search`、`search_web`（僅 API Fallback）
- ⚠️ `write_to_file`：**P33-WLTM 完全禁止**
- **MCP Tools (P32 新增)**:
  - `read_graph` / `search_nodes` — Knowledge Graph 查詢(檢查過往傷兵狀態、防守大閘觀察、球員 Props 命中規律)
  - `read_query` / `list_tables` — SQLite 歷史數據查詢(查等過往 Parlay 命中率、球員 Props 歷史表現)
  - `create_entities` / `create_relations` — 將覆盤發現寫入 Knowledge Graph(傷兵更新、防守效果、SIP 觸發模式)
- **Scripts (v2.2.0 — P22 Python-First)**:
  - `scripts/fetch_nba_results.py` — **主引擎** Box Score 擷取 (nba_api ScoreboardV3 + BoxScoreTraditionalV3)
  - `scripts/fetch_nba_pbp.py` — Play-by-Play 擷取 (nba_api PlayByPlayV3)（條件觸發）
  - `scripts/verify_props_hits.py` — Props 命中自動驗證器（每次覆盤強制執行）
- **Resources**:
  - `resources/01_report_template.md` — 覆盤報告格式 + SIP Changelog
  - `resources/02_search_protocol.md` — 數據搜索協議 + 比對框架（API Fallback）
- **Upstream Data**:
  - `NBA Wong Choi` 輸出嘅分析報告（新格式: `{MM-DD}_NBA_*_Analysis.md`；舊格式: `Game_*_Full_Analysis.md`）
  - `NBA Wong Choi` 輸出嘅匯總報告: `NBA_Banker_Report.txt` / `NBA_All_SGM_Report.txt`
  - `NBA Analyst` 嘅 `resources/` 引擎定義檔
  - **API 生成嘅 JSON (v2.2.0 新增)**:
    - `Results_Brief_{DATE}.json` — Box Score（由 `fetch_nba_results.py` 生成）
    - `PBP_Brief_{DATE}.json` — Play-by-Play（由 `fetch_nba_pbp.py` 生成）
    - `Props_Verification_{DATE}.json` — 命中比對結果（由 `verify_props_hits.py` 生成）

# Test Case
**User Input:** `「幫我覆盤今日 NBA:2026-03-16」`
**Expected Agent Action:**
1. 讀取 `resources/01_report_template.md` + `resources/02_search_protocol.md`。
2. 記錄 `ANALYSIS_DATE` = 2026-03-16,`US_DATE` = 2026-03-15。
3. Session Recovery 檢查:掃描 TARGET_DIR 是否已有覆盤報告。
4. 搜尋每場賽事 Box Score,逐 Leg 比對。
5. 生成覆盤報告 + 更新 SIP Changelog。
6. 向用戶提交報告摘要,等待審批。
