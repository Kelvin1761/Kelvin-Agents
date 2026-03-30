# NBA 覆盤報告格式 (Reflection Report Template)

保存為 `{ANALYSIS_DATE}_NBA_覆盤報告.txt` 於 `TARGET_DIR` 內。

---

## 報告格式

```
🔍 NBA 賽後覆盤報告
日期: [澳洲日期] (美國 [美國日期]) | 場次: [總場次]

📊 整體命中率

| 組合類型 | Leg 命中率 | 組合全中 | 備註 |
|:---|:---|:---|:---|
| 🛡️ 穩膽組合 | X/Y (Z%) | ✅/❌ | [一句話] |
| 💎 價值組合 | X/Y (Z%) | ✅/❌ | [一句話] |
| 🔥 高賠組合 | X/Y (Z%) | ✅/❌ | [一句話] |
| 整體 | X/Y (Z%) | X/3 全中 | |

📋 逐場覆盤摘要

🏀 Game X: [Team A] vs [Team B] — [最終比分]

--- 穩膽組合 ---
Leg 1: [球員] [盤口] — [✅ 命中 / ❌ 未中]
  預測: [盤口線] | 實際: [實際數據] | 差距: [+X / -X]
  [若未中] 失誤根因: [一句話分析]
Leg 2: ...
Leg 3: ...

--- 價值組合 ---
(同上格式)

--- 高賠組合 ---
(同上格式)

🔴 False Positives (高信心但大敗)
| 場次 | 球員 | 盤口 | 預測命中率 | 實際數據 | 失誤根因 |
|:---|:---|:---|:---|:---|:---|

🟢 False Negatives (被排除/低信心但達標)
| 場次 | 球員 | 盤口 | 預測評估 | 實際數據 | 遺漏因素 |
|:---|:---|:---|:---|:---|:---|

📰 被忽略的關鍵場外因素
- [列出預測時未納入但影響結果嘅重要新聞/事件]

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
- [不建議修改模型的個別事件，如球員受傷離場、被驅逐、Blowout 垃圾時間等]
```

---

## SIP Changelog 更新格式

每次覆盤後，若有新 SIP 提出，必須更新 `{TARGET_DIR}/_sip_changelog.md`：

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

若 `_sip_changelog.md` 不存在，以以下格式建立：
```
# NBA SIP Changelog
> 追蹤所有 Systemic Improvement Proposals 嘅提出、審批同驗證。

---
```
