# NBA 覆盤報告格式 (Reflection Report Template)

保存為 `{ANALYSIS_DATE}_NBA_覆盤報告.md` 於 `TARGET_DIR` 內。

---

## 報告格式

```
🔍 NBA 賽後覆盤報告
日期: [澳洲日期] (美國 [美國日期]) | 場次: [總場次]
數據來源: API (fetch_nba_results.py) / SEARCH_WEB (FALLBACK)

📊 整體命中率

| 組合類型 | Leg 命中率 | 組合全中 | 備註 |
|:---|:---|:---|:---|
| 🛡️ 穩膽組合 | X/Y (Z%) | ✅/❌ | [一句話] |
| 🔥 價值組合 | X/Y (Z%) | ✅/❌ | [一句話] |
| 💎 進取組合 | X/Y (Z%) | ✅/❌ | [一句話，若存在] |
| 整體 | X/Y (Z%) | X/N 全中 | |

> ℹ️ V5+ 格式可能只有 2 組 SGM，請依實際組合數呈現。

📋 逐場覆盤摘要

🏀 Game X: [Team A] vs [Team B] — [最終比分]
盤口來源: [odds_source] | 分析引擎: [引擎版本] | 數據來源: [API/FALLBACK]

--- 穩膽組合 ---
Leg 1: [球員] [盤口] @[賠率] — [✅ 命中 / ❌ 未中]
  預測: [盤口線] | Adj Prob: [X%] | Edge: [+X%]
  實際: [實際數據] | 差距: [+X / -X]
  [若未中] 失誤根因: [一句話分析]
Leg 2: ...

--- 價值組合 ---
(同上格式)

--- 進取組合 (若存在) ---
(同上格式)

🔴 False Positives (高信心但大敗)
| 場次 | 球員 | 盤口 | 預測命中率 | 實際數據 | 失誤根因 |
|:---|:---|:---|:---|:---|:---|

🟢 False Negatives (被排除/低信心但達標)
| 場次 | 球員 | 盤口 | 預測評估 | 實際數據 | 遺漏因素 |
|:---|:---|:---|:---|:---|:---|

📈 Play-by-Play 深度覆盤 (v2.2.0 新增 — 條件觸發)
[僅喺 Blowout / 低 MIN / 穩膽大幅未中場次呈現]

🏀 PBP Game X: [Team A] vs [Team B]
觸發原因: [Blowout / 球員 MIN < 25 / 穩膽 Margin ≤ -5]

每節得分分布:
| 節次 | 主隊 | 客隊 | 節差 |
|:---|:---|:---|:---|
| Q1 | [X] | [Y] | [+/-Z] |
| Q2 | [X] | [Y] | [+/-Z] |
| Q3 | [X] | [Y] | [+/-Z] |
| Q4 | [X] | [Y] | [+/-Z] |

關鍵球員上場分布:
| 球員 | Q1 MIN | Q2 MIN | Q3 MIN | Q4 MIN | Total |
|:---|:---|:---|:---|:---|:---|
| [球員名] | [X] | [Y] | [Z] | [W] | [Total] |

Blowout 分析:
- 首次 20 分領先: [時間]
- 領先隊: [隊伍]
- 主力最後上場時間: [Q?/XX:XX]
- 影響嘅 Props: [列出受影響嘅 Legs]
⌨️ 被忽略的關鍵場外因素
- [列出預測時未納入但影響結果嘅重要新聞/事件]

📊 數據管道可靠性審計 (v2.2.0 新增)
- 數據來源: API / SEARCH_WEB (FALLBACK)？若 Fallback → 原因為何？
- `fetch_nba_results.py` 執行結果: 成功/失敗？擷取幾多場？
- `verify_props_hits.py` 自動命中判定 vs LLM 覆核: 有冇差異？
- `fetch_nba_pbp.py` 觸發場次: [列出] / 未觸發 (原因)

📊 odds_source 可靠性審計
- odds_source 是否為 SPORTSBET_LIVE？若否 → 盤口準確度可能有偏差
- Blowout 風險標記是否準確？（最終分差 vs 預測分差）
- Python vs Analyst 分工是否有效？（Analyst 有冇真正提出獨立見解）

🧠 系統性改善建議 (Systemic Improvement Proposals)

SIP-1: [建議標題]
- 問題: [描述反覆出現的判斷偏差]
- 證據: [列舉支持此結論的多場實例]
- 建議修改: [針對 NBA Analyst 的哪個 Resource / Engine / Rule 進行什麼調整]
  - 目標檔案: [resources/02_volatility_engine.md / 03_safety_gate.md / 04_parlay_engine.md / 03_defensive_profiles.md]
- 影響範圍: [此修改會影響哪些場景]

SIP-2: [建議標題]
...

⚠️ 單場特殊因素 (Non-Systemic, 僅供記錄)
- [不建議修改模型的個別事件,如球員受傷離場、被驅逐、Blowout 垃圾時間等]
```

---

## SIP Changelog 更新格式

每次覆盤後,若有新 SIP 提出,必須更新 `{TARGET_DIR}/_sip_changelog.md`:

```
## SIP-[YYYY-MM-DD]-[序號]: [標題]
- **提出日期**: [YYYY-MM-DD]
- **狀態**: 待審批 / 已採納 / 已拒絕 / 已驗證
- **問題摘要**: [一句話]
- **目標檔案**: [路徑]
- **修改內容**: [概要]
- **採納日期**: [若已採納]
- **驗證結果**: [若已驗證 — 效果如何]
```

若 `_sip_changelog.md` 不存在,以以下格式建立:
```
# NBA SIP Changelog
> 追蹤所有 Systemic Improvement Proposals 嘅提出、審批同驗證。

---
```
