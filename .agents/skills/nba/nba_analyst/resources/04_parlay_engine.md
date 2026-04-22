# 過關組合引擎 (Parlay Combination Engine) — Step 5

> **V1 穩健 +EV 策略:** NBA Wong Choi 只推薦 Sportsbet Player Milestone `X+`（Over）選項。Team market（ML / Spread / Total）只可作背景參考，不可混入 Python Auto-Selection 嘅 player milestone SGM 組合。Under / Total U 不作投注推介。

---

## Step 1: 判斷成局條件

若安全通過 Step 4 嘅所有 Legs 過少:
- 穩膽合格 Legs < 2 → 無法構建穩膽組合
- 價值合格 Legs < 2 → 無法構建價值組合
- 總合格 Legs < 3 → 直接輸出「⛔ 今場建議觀望」並說明理由

寧缺勿濫。

---

## Step 2: 構建三層級組合 (1 + 2 + 3 + X 條件觸發)

> [!IMPORTANT]
> 所有賞率來自 **Sportsbet 直接提取**。組合賞率以 Sportsbet SGM 實際顯示為準。
> Python Generator 會從 Sportsbet 提取嘅 per-leg odds 相乘計算參考組合賞率，但實際投注時以 Sportsbet SGM 頁面顯示嘅組合賞率為準。

### 🛡️ 穩膽型 (Banker Tier — 組合 1)
- **組合賞率（Sportsbet Legs 相乘）≥ 2.0 倍**
- 要求每腿 L10 命中率 **≥70%**
- 要求每腿 Edge **≥0%**（禁止負 EV）
- 優先選用 CoV < 0.25 嘅極度穩定球員
- **建議關數: 2-4 Leg（彈性關數策略）**
  - 3-4 Leg 穩膽組合允許每腿選用更低風險盤口 (Alt Lines 降級),更符合「穩健收米」嘅宗旨
  - 2-Leg 穩膽需要每腿賠率 ≥ 1.5+
  - 3-Leg 穩膽只需每腿賠率 ≥ 1.3+

### 🔥 均衡 +EV 價值膽 (Value Tier — 組合 2)
- **組合賞率（Sportsbet Legs 相乘）≥ 3.0 倍，目標 5x**
- 要求每腿 L10 命中率 **≥40%** + Edge **≥3%**
- 主力正盤與對位弱點針對
- 可混搭穩膽線 + 價值線 Legs
- **建議關數: 2-4 Leg（彈性關數策略）**

### 💎 價值型小博大 (High Odds Tier — 組合 3)
- **組合賞率（Sportsbet Legs 相乘）≥ 8.0 倍**
- 容忍更高風險,但個別腿保持 **≥40% 命中率**
- 每腿 Edge **≥0%**；高波動球員只可喺有正 Edge 及合理 MC 支持時使用
- 只可使用 Sportsbet milestone `X+` Over legs
- **建議關數: 3 Leg**

### 💣 Value Bomb (莊家低估 — 組合 X) — 條件觸發
- **只有當 Python 偵測到 Edge ≥10%+ 嘅顯著低估時先會出現**
- 需同時通過 MC Edge ≥5% 或 L5/L10 命中率一致性檢查
- 每腿 L10 命中率 ≥ 55%
- 最多 3 Legs

---

## SGP 劇本語境防撞擊檢查 (必做)

構建組合時,必須逐一檢查以下防撞擊規則:

### ✅ 允許嘅組合模式
| 模式 | 說明 |
|------|------|
| 🥇 完美跨場互補 | 控衛 Over 助攻 + 另一場頂級單打手 Over 得分 |
| 🥉 垃圾時間劇本 | 避開大熱方主力高門檻得分 Over，僅保留低門檻 milestone 或替補 Over（僅限高賠型） |

### 🚫 禁止嘅組合模式
| 模式 | 說明 |
|------|------|
| 互相蠶食 | 嚴禁同隊三名先發全買得分 Over (球權不夠) |
| 天花板衝突 | 同隊兩名球員都買高分 Over,總分有天花板限制 |
| 劇本矛盾 | 嚴禁重注某球員超級大分,卻買該場比賽總分 Under |
| 防守敗局 | 雙方防守皆 Top 10 且總分盤 ≤ 215 → 全場得分 Over 需警戒 |
| 同隊得分擠壓 | 同隊 PTS Over 最多 2 腿；嚴禁同隊 3 名得分 Over |
| Market 污染 | Team market 不可與 player milestone legs 混入同一自動 SGM |

### 📈 正相關加成組合 (Positive Correlation Matrix)
以下組合模式有統計正相關性,可以增強 SGM 命中率:

| 模式 | 說明 | 適用組合 |
|:---|:---|:---|
| 控衛 AST Over + 隊友得分 Over | 助攻轉化為得分,正相關 | 穩膽/價值 |
| 控衛 AST Over + 射手 3PM Over | 助攻餵射手,強正相關 | 穩膽 |
| 大前鋒/中鋒 REB Over + 對手得分 Over | 對手攻擊型球隊 = 更多籃板機會 | 價值 |
| 後衛得分 Over + 對手禁區守護者缺陣 | 切入機會增加,正相關 | 穩膽/價值 |
| 球員 PTS Over + 球隊 Total Over | 節奏快 = 更多得分機會 | 價值/高賠 |

> 構建 SGM 時,優先選擇有正相關性嘅 Leg 搭配,可以降低「一死全死」嘅風險。

---

## Sportsbet 嚴格選項規則 (Strict Built-in Matrix)

**CRITICAL CONSTRAINT**: 你**只能**推薦以下 Sportsbet 預先設定好嘅 Milestone 選項(對應 Over N-0.5)。絕對**嚴禁**自己發明任何中間數字(例如 22.5, 6.5 PTS),否則為嚴重違規。

### 得分 (Points / Scoring)
- 只能選擇以下目標:5, 10, 15, 20, 25, 30, 35, 40, 45, 50 
- 即盤口必須寫為:PTS Over 4.5, PTS Over 9.5, PTS Over 14.5, PTS Over 19.5, PTS Over 24.5, PTS Over 29.5, PTS Over 34.5, PTS Over 39.5, PTS Over 44.5, PTS Over 49.5 (UNDER 同理)

### 三分球 (Threes Made / 3PM)
- 只能選擇以下目標:1, 2, 3, 4, 5, 6, 7, 8
- 即盤口必須寫為:3PM Over 0.5, Over 1.5, Over 2.5, Over 3.5, Over 4.5, Over 5.5, Over 6.5, Over 7.5

### 籃板 (Rebounds)
- 只能選擇以下目標:3, 5, 7, 10, 13, 15, 17, 20
- 即盤口必須寫為:REB Over 2.5, Over 4.5, Over 6.5, Over 9.5, Over 12.5, Over 14.5, Over 16.5, Over 19.5

### 助攻 (Assists)
- 只能選擇以下目標:3, 5, 7, 10, 13, 15
- 即盤口必須寫為:AST Over 2.5, Over 4.5, Over 6.5, Over 9.5, Over 12.5, Over 14.5

### 其他數據 (Blocks, Steals, 組合數據)
- 若選擇其他盤口,必須參考球員常規選項,否則強烈建議僅推薦上述 4 種核心選項,避免造出 Sportsbet 無法投注嘅虛假盤口。

### L10 順序規則
- 全系統 L10 順序固定為 `newest_first`（最新一場 → 最舊一場）。
- L3 = L10 前 3 項；L5 = L10 前 5 項。
- 報告必須顯示 `L10_ORDER: newest_first`。

---

## 賠率來源規則

### 有 Sportsbet 即時賞率（標準流程）
直接使用 `claw_sportsbet_odds.py` 提取嘅 Sportsbet 賞率。
組合賞率 = Leg 賞率相乘（參考值），實際以 Sportsbet SGM 顯示為準。

### 無即時賞率（Fallback）
使用美式基準估算:
- 標準 milestone Over:**1.90**
- Alt Lines (降低 1 級):約 **1.50-1.65**
- Alt Lines (升高 1 級):約 **2.20-2.50**
- Alt Lines (升高 2 級):約 **3.00-3.50**

### 組合賞率計算
```
參考組合賞率 = Leg1 賞率 × Leg2 賞率 × ... × LegN 賞率
```
> ⚠️ 以上為數學參考值。實際 Sportsbet SGM 價格可能因關聯性調整而不同，落注前請以 Sportsbet 顯示為準。

---

## 組合輸出要求

每個組合必須包含:
1. 組合類型標記 (🛡️ 1 / 🔥 2 / 💎 3 / 💣 X)
2. 關數 (N-Leg)
3. 每個 Leg 嘅完整分析（數據 + 核心邏輯 + Analyst 深度補充）
4. 📊 組合結算區塊（賠率相乘 + 回報 + 命中率 + Edge + 核心邏輯 + 風險 + 注碼）
5. 完成自檢確認
6. 必須輸出 **3 個組合**（組合 1 + 2 + 3），組合 X 為條件觸發
