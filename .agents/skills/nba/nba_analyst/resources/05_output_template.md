# NBA Analyst 最終輸出模板 (V9.0 — Sportsbet 直取 + Python 預填 + Analyst 深度審閱)

> [!CAUTION]
> 🚨 **骨架注入零容忍協議 (Skeleton Injection Zero-Tolerance Protocol)**
> - 本模板中所有 `[FILL]` 佔位符都**必須**被替換為真實分析文字
> - Python 預填嘅數學數據（賠率、命中率、Edge、組合結算）**嚴禁修改**
> - **嚴格禁止使用**：`...`、`[數據略]`、`[同上]`、`[邏輯同前]`、`[參見組合X]`
> - 賠率來自 **Sportsbet 直接提取**，組合賠率以 Sportsbet SGM 顯示為準

---

## 📝 單場分析檔案格式 (`Game_{GAME_TAG}_Skeleton.md`)

> 由 `generate_nba_reports.py V3` 自動生成。
> 所有數學欄位由 Python 8-Factor Adjusted Win Prob 引擎精確計算。
> LLM 負責填寫 `[FILL]` 邏輯欄位 + 審閱 Python 自動核心邏輯。

---

# 🏀 NBA Wong Choi — [Python 預填: 隊A] @ [Python 預填: 隊B]
**日期**: [Python 預填] | **Sportsbet 提取時間**: [Python 預填]
**odds_source**: BET365_LIVE ✅ | **引擎版本**: Adjusted Win Prob V3 (8-Factor)

---

### 🏀 賽事背景
| 項目 | 數據 |
|------|------|
| **讓分盤** | [Python 預填] |
| **總分盤** | [Python 預填] |
| **獨贏** | [Python 預填] |
| **節奏** | [Python 預填: PACE 數據] |
| **B2B** | [Python 預填: 由 fatigue model 偵測] |

> [!WARNING] (條件觸發 — Blowout / Tank Risk)
> 🚨 **BLOWOUT 風險** — 讓分盤 [X]，垃圾時間風險顯著。
> 🏳️ **擺爛/戰意警告** — [X] 戰績極差，存在擺爛可能。

### 📋 傷病報告
- [Python 預填: 逐條列出]

### 📰 新聞摘要 (NEWS_DIGEST)
- [Python 預填: 逐條列出]

---

## 🎯 全部球員 Sportsbet 盤口分析

> Python 會為每位有 Sportsbet 盤口嘅球員生成以下結構：

#### [Python 預填: 球員名] (#[球衣], [球隊]) — [PTS/3PM/REB/AST]

| 🔢 數理引擎 | 🧠 邏輯引擎 |
|:---|:---|
| **L5**: `[Python 預填]` | **角色**: [FILL] |
| **L10 均值**: [預填] \| **中位**: [預填] | **USG%**: [預填] |
| **SD**: [預填] \| **CoV**: [預填] [分級] | **趨勢**: [預填] |

**🎯 Sportsbet 盤口對照表:**
| Line | Odds | 隱含勝率 | L10 命中 | L5 命中 | 預期勝率 | Edge | 判定 |
|------|------|----------|----------|---------|----------|------|------|
| [預填: 10+] | [預填: @X.XX] | [預填]% | [預填]% (X/Y) | [預填]% (X/Y) | **[預填]%** | [預填]% [評級] | [預填] |

> **Sportsbet 線格式**: `10+` = 10 分或以上 (≥10)。命中判定: `value >= 10`。
> **預期勝率**: 由 8-Factor Adjusted Win Prob 引擎計算（Base Rate ± PACE/DEF/B2B/USG/Defender/CoV/Matchup/Trend）

---

## 🎰 SGM Parlay 組合 (Python Auto-Selection)

> [!IMPORTANT]
> 以下組合由 Python 自動從球員數據篩選並計算。
> - Python 預填：Legs 表格、賠率、命中率、Edge、組合結算、自動核心邏輯
> - LLM 填寫：獨立關卡剖析 (`[FILL]`)、補充/審閱組合核心邏輯
> - **球員分散規則**：每位球員只會出現喺一個組合中
> - **賠率來源**: 所有賠率來自 Sportsbet 直接提取，組合賠率以 Sportsbet SGM 顯示為準

### 🛡️ 組合 1: 穩膽 SGM (Low Risk) — 組合賠率 @[Python 預填]
> 篩選條件: L10 命中 ≥70% + 組合賠率 > 2x

| Leg | 選項 | 賠率 | L10 命中 | 預期勝率 | Edge | CoV |
|-----|------|------|----------|----------|------|-----|
| 🧩 1 | [Python 預填] | @[預填] | [預填]% ([預填]) | **[預填]%** | [預填]% | [預填] |
| 🧩 2 | [Python 預填] | @[預填] | [預填]% ([預填]) | **[預填]%** | [預填]% | [預填] |

**🎯 獨立關卡剖析:**

**Leg 1 — [Python 預填選項] @[預填賠率]:**
📊 數據: [Python 預填: L10 數組 + AVG + MED + SD]
隱含勝率 [預填]% | 預期勝率 **[預填]%** | Edge: [預填]%
📐 [Python 預填: 8-Factor 調整明細]
🧠 **核心邏輯**: [Python 預填 — 自動生成嘅數據面敘述]
[FILL: Analyst 深度補充 — 對手防守匹配分析、球權分配邏輯、上場時間預測、協同效應]

**Leg 2 — [Python 預填選項] @[預填賠率]:**
📊 數據: [Python 預填]
🧠 **核心邏輯**: [Python 預填]
[FILL: Analyst 深度補充]

**📊 組合結算:**
- **賠率相乘**: [預填] = **@[預填]**
- **$100 回報**: **$[預填]**
- **組合命中率**: [預填] = **[預填]%**
- **平均 Edge**: [預填]%
- **🛡️ 組合核心邏輯**: [Python 自動生成 + FILL: Analyst 補充協同效應]
- **⚠️ 主要風險**: [Python 自動生成 + FILL: Analyst 補充]
- **建議注碼**: [Python 自動生成: 💰💰💰 / 💰💰 / 💰 / ⚠️]

> ⚠️ 以上賠率為獨立 Leg 相乘。實際 Sportsbet SGM 價格可能因關聯性調整而不同，落注前請以 Sportsbet 顯示為準。

---

### 🔥 組合 2: 均衡 +EV 價值膽 (Mid Risk) — 組合賠率 @[Python 預填]
> 跨隊 / 不同球員混搭 + 組合賠率 > 3x, 目標 5x
> *(格式同組合 1)*

---

### 💎 組合 3: 高倍率進取型 (High Risk) — 組合賠率 @[Python 預填]
> 3 Legs 高倍率組合
> *(格式同組合 1)*

---

### 💣 組合 X: Value Bomb (莊家低估) — *條件觸發*
> 只有當 Python 偵測到 Edge ≥10%+ 嘅顯著低估時先會出現
> *(格式同組合 1)*

---

## 📊 球員盤口詳細分析 (Appendix)

> Python 為每位球員生成完整 Player Card（含所有 Sportsbet 線嘅對照表）。
> 詳見上方「全部球員 Sportsbet 盤口分析」區塊。

---

## 🧠 總結與賽前必做
- **最強關**: [Python 預填: 邊個 leg Edge 最高]
- **最弱關**: [Python 預填: 邊個 leg Edge 最低]
- **賽前 60 分鐘必查**: 傷病更新 / 首發陣容確認 / Sportsbet 盤口變動 / B2B 情況

---

## ✅ 盤口數據來源驗證
> **Sportsbet Claw V6** (Comet CDP) 即時提取 | 提取時間: [Python 預填]
> 所有 Lines/Odds 來自 bet365.com.au DOM Snapshot
> Sportsbet 線格式: "10+" = 10 分或以上 (≥10)

## 📋 自檢
✅ Python 預填完成 | 組合數: [1/2/3/X] | `[FILL]` 殘留: 0 個 ✔️
