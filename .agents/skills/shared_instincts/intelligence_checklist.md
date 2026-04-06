# Intelligence-First Checklist（跨 Domain 通用框架）

> **設計理念:** 受 ECC `search-first` 啟發，將「分析前先 research」嘅哲學應用到 Wong Choi 賽事分析。
> 在即時情報搜集（Tier 1）之上，加入歷史數據交叉驗證（Tier 2），提升情報包嘅深度同可靠度。

---

## Tier 1 — 即時情報（必做 — 每個 Domain 已涵蓋）

> 各 Domain 嘅 SKILL.md 已定義完整嘅即時情報搜集流程。此 checklist 唔覆蓋 Tier 1，只作提醒。

### AU Racing (Step 2)
- 官方場地狀態 / 跑道偏差 / 欄位 / 天氣 / 退出報告 / 配備變動

### HKJC Racing (Step 3)
- 場地狀態 / 跑道偏差 / 欄位 / 天氣 / 傷患配備變動

### NBA (Step 2A)
- 傷兵報告 / 盤口 / L10 數據卡 / B2B 狀態

---

## Tier 2 — 歷史交叉驗證（新增 — 需要 MCP）

> [!NOTE]
> Tier 2 依賴 Memory MCP（Knowledge Graph）同 SQLite MCP（結構化歷史數據）。
> 若 MCP 不可用 → 跳過 Tier 2，維持原有流程，唔影響分析。

### AU Racing Tier 2（插入於 Step 2 之後 → Step 2.5）

| 檢查項 | MCP 工具 | 查詢 |
|--------|---------|------|
| 同場地過往 3 次 track bias | `read_graph` | Entity: `{VENUE}_*_bias` |
| 同場地過往 3 次 Top 4 命中率 | `read_query` | `SELECT * FROM au_ratings WHERE venue='{VENUE}' ORDER BY date DESC LIMIT 30` |
| 天氣 Pattern：同類天氣 → 實際掛牌偏差 | `search_nodes` | `weather_accuracy_*` |
| Reflector SIP 記錄：過往同場地嘅修正 | `read_graph` | `FP_pattern_*` / `FN_pattern_*` |

**Integration 格式（加入 `_Meeting_Intelligence_Package.md`）：**
```markdown
## 歷史場地 Pattern（Tier 2 — MCP 交叉驗證）
- 過往 3 次場地偏差: [內欄優勢 × 2 / 中立 × 1]
- 過往 3 次命中率: [🏆 45% / ✅ 60% / ⚠️ 75%]
- 天氣轉換 Pattern: [預測偏軟 → 實際偏硬 × 2/3 次]
- 活躍 SIP: [SIP-RR17 (濕地膨脹), SIP-RF01 (寬恕校準)]
- **Intelligence Confidence: [🟢/🟡/🔴]**
```

---

### HKJC Racing Tier 2（插入於 Step 3 之後 → Step 3.5）

| 檢查項 | MCP 工具 | 查詢 |
|--------|---------|------|
| 同場地(沙田/跑馬地)過往場地偏差 | `read_graph` | Entity: `{VENUE}_*_bias` |
| 同 Going 條件下嘅命中率 | `read_query` | `SELECT * FROM hkjc_ratings WHERE venue='{VENUE}' AND track_condition LIKE '%{GOING}%'` |
| 練馬師喺同場地嘅歷史表現 | `search_nodes` | `trainer_{NAME}_{VENUE}` |
| AWT 特殊檢查（若為全天候跑道） | `read_query` | `SELECT * FROM hkjc_ratings WHERE venue='ShaTin' AND surface='AWT'` |

**Integration 格式（加入 `_Meeting_Intelligence_Package.md`）：**
```markdown
## 歷史場地 Pattern（Tier 2 — MCP 交叉驗證）
- 過往 3 次場地偏差: [{VENUE} - 內欄 × 1/ 外欄 × 1 / 中立 × 1]
- 同 Going 命中率: [{GOING} 歷史命中率 X%]
- 練馬師 Spotlight: [{TRAINER} 喺 {VENUE} 近 10 場勝率 Y%]
- AWT 檢查: [適用 / 不適用]
- **Intelligence Confidence: [🟢/🟡/🔴]**
```

---

### NBA Tier 2（插入於每場 Sub-Step 2A 之前 → Sub-Step 2A-Pre）

> [!IMPORTANT]
> NBA 嘅 Tier 2 係 **Per-Game** 查詢，因為每場對手唔同。

| 檢查項 | MCP 工具 | 查詢 |
|--------|---------|------|
| 球員 vs 對手歷史 Props 命中率 | `read_query` | `SELECT * FROM predictions WHERE player='{PLAYER}' AND opponent='{OPPONENT}'` |
| 球員傷病 Timeline + 復出 usage | `read_graph` | Entity: `{PLAYER}_injury_timeline` |
| B2B 歷史達標率 | `read_query` | `SELECT * FROM predictions WHERE player='{PLAYER}' AND is_b2b=1` |
| 防守大閘效應 | `search_nodes` | `defender_{NAME}_vs_{POSITION}` |

**Integration 格式（加入每場數據包頭部）：**
```markdown
## 歷史對位 Pattern（Tier 2 — MCP 交叉驗證）
- {PLAYER_1} vs {OPPONENT}: 過往 Props 命中率 [X/Y = Z%]
- {PLAYER_2} B2B 歷史: [達標率 X%，平場降幅 -Y%]
- 防守大閘: [{DEFENDER} 對 {POSITION} 限制 -X% usage]
- **Intelligence Confidence: [🟢/🟡/🔴]**
```

---

## Tier 3 — 風險預警（條件觸發 — 全 Domain 通用）

| 條件 | 觸發 | 行動 |
|------|------|------|
| 歷史命中率 < 40% | 🔴 HIGH_RISK | 加入 Intelligence Package 嘅 ⚠️ 風險 flag |
| 冇歷史數據 | 🟡 NO_HISTORY | 降級為 Tier 1 only，標記 「首次分析此場地/對手」|
| 歷史數據顯示強烈偏差 pattern | 🟠 PATTERN_ALERT | 加入 Intelligence Package 嘅額外 section + 通知 Analyst |
| 過往 SIP 連續 2+ 次錯誤 | 🔴 SIP_DEGRADING | 標記該 SIP 為 ⚠️ 需 review |

---

## Intelligence Confidence Level（統一定義）

| Level | 條件 | 對分析嘅影響 |
|-------|------|------------|
| 🟢 **HIGH** | Tier 1 全部完成 + Tier 2 有歷史數據匹配 | 正常分析流程，歷史 pattern 會傳畀 Analyst |
| 🟡 **MEDIUM** | Tier 1 全部完成，Tier 2 冇歷史數據或 MCP 不可用 | 正常分析流程，但標記「首次分析」|
| 🔴 **LOW** | Tier 1 部分失敗 | 通知用戶缺失數據，等確認後先繼續 |

---

## MCP 不可用時嘅 Fallback

若 Memory MCP 或 SQLite MCP 未安裝/未連接：
1. 整個 Tier 2 自動跳過
2. Intelligence Confidence 設為 🟡 MEDIUM
3. 喺 Intelligence Package 加入：`⚠️ Tier 2 歷史驗證已跳過（MCP 不可用）`
4. **分析流程完全唔受影響** — Tier 2 係純粹嘅增強層
