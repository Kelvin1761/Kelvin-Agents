# Market Lens — 盤口分析模組 V1.0

> **Version**: 1.0.0
> **Status**: ✅ ACTIVE (Phase Β)
> **Created**: 2026-04-10

---

## 觸發時機

Step 1 (Implied Edge Verification) 完成後，**自動執行** Market Lens Scan。
掃描結果記錄在 Ledger 末尾，供 Override Decision 參考。

---

## 1. CLV (Closing Line Value) 追蹤

> **CLV 係 Pro Bettor 最可靠嘅 edge 驗證指標。**
> 你持續 beat closing line = 你有真正 edge。
> 你持續 lose to closing line = 你被市場收割。

### 計算公式
```
CLV% = (Closing_Odds / Bet_Odds - 1) × 100

例：買入 @3.20，收盤 @2.85
CLV% = (2.85 / 3.20 - 1) × 100 = -10.9% (負 CLV — 收盤比你買嘅平)

例：買入 @2.50，收盤 @2.80
CLV% = (2.80 / 2.50 - 1) × 100 = +12.0% (正 CLV — 你搵到真正價值)
```

### CLV 診斷矩陣
| CLV | 結果 | 診斷 | 行動 |
|-----|------|------|------|
| ✅ 正CLV | ✅ WIN | **完美決策** — 真 edge + 執行正確 | 繼續相同策略 |
| ✅ 正CLV | ❌ LOSE | **正確決策但 variance** — 長期會贏返 | 繼續，唔好改 |
| ❌ 負CLV | ✅ WIN | **幸運** — 可能唔係真 edge | 審視此市場嘅選擇邏輯 |
| ❌ 負CLV | ❌ LOSE | **被誘盤** — 需要預防 | 標記此類盤口，未來增加警惕 |

### betting_record.md CLV 格式
```
| # | 日期 | 賽區 | 推介 | Type | Grade | 下注賠率 | 收盤賠率 | CLV% | 注碼 | 結果 | 盈虧 |
```
- **下注賠率**: 投注時嘅賠率
- **收盤賠率**: 比賽開始前最後嘅賠率（由 postmortem 回填）
- **CLV%**: 由 postmortem 計算並回填

---

## 2. 5Q 盤口異常掃描框架

### Q1: 方向衝突 [📊 逆莊方向]

```
IF 模型方向 ≠ 莊家暗示方向:
  - 計算偏差 = |model_P - market_P|
  - 偏差 10-20% → [📊 逆莊方向]
  - 偏差 > 20% → [📊⚠️ 嚴重逆莊]
```

> **覆盤證據**：Session 12 NIP 獨贏 (model 57% vs 莊家 31.5%) = 嚴重逆莊 → 輸
> **覆盤證據**：Session 8 DNS 獨贏 (model 52% vs 莊家 50%) = 輕微逆莊 → 輸

### Q2: 盤口壓縮 [🔍 Spread 異常]

```
Spread = 獨贏賠率 - (+1.5)賠率

正常 Spread ≈ 0.80-1.20
Spread < 0.60 → [🔍 盤口壓縮] — 莊家認為 2-1 概率極高
Spread > 1.50 → [🔍 盤口拉闊] — 莊家認為 2-0 或 0-2 居多
```

### Q3: 歷史 CLV 模式 [📉 市場漂移]

```
讀取 betting_record.md 中此隊/此盤口過去 5 注的 CLV 數據：
  平均 CLV < -5% → [📉 負CLV模式] — 你一直買到嘅「edge」可能係假嘅
  平均 CLV > +5% → [📈 正CLV模式] — 你喺呢個市場確實有 edge
  數據不足 (<5 注) → [ℹ️ CLV數據不足] — 暫無參考
```

### Q4: 操盤手逆向工程 [🧠 莊家邏輯]

每場比賽 Ledger 加入 1-2 句分析，回答以下問題：
```
「莊家點解要咁開？散戶傾向買邊？呢個 edge 係咪莊家故意留嘅？」

常見操盤邏輯：
- 大熱門壓低獨贏 → 冷門 +1.5 被推高 → 可能有真 edge
- 小聯賽/早期賽事 → 莊家唔花資源精準定價 → edge 更可能真實
- 明星隊伍剛輸 → 散戶追買對手 → 明星隊反彈值被忽略
- 上一場 2-0 橫掃 → 散戶追買 -1.5 → +1.5 被高估
```

### Q5: 陷阱盤偵測 [⚠️ Trap Line]

```
TRIGGER CONDITIONS (需要同時滿足 ≥2 個)：
1. 校準 EV% > 18% 且為主流賽事 (LCK/LPL Tier 1 對決)
2. 賠率方向與此隊過去 3 場趨勢完全矛盾
3. 無明確新聞/傷病/陣容變動解釋賠率異常
4. 開盤後賠率無顯著移動 (line frozen = 莊家滿意散戶站位)

→ [⚠️ Trap Line 疑似]
→ 行動：Kelly × 0.5 或建議 PASS
→ 備注：需要覆盤確認（Reflector/Postmortem 追蹤此注 CLV）
```

---

## 3. Pro Bettor Review Cadence

| Checkpoint | 觸發條件 | 動作 |
|-----------|---------|------|
| **Session 級** | 每次 Session 結束 | Quick P&L + CLV 記錄（由 postmortem 執行）|
| **25 注門** | 累積達 25/50/75/100 注 | 統計 review：按 League / Bet Type / Edge Tier 分拆 CLV |
| **50 注門** | 累積達 50 注 | **策略調整窗口**：評估 Phase Γ 啟動條件 |
| **100 注門** | 累積達 100 注 | **全面系統審計**：回測所有 CLV 數據，重新校準模型 |

---

## 4. Ledger 輸出格式

在 Accountant Ledger Step 5 (Override Decision) 之後加入：

```
📊 Market Lens Scan:
   Q1 方向: [📊 逆莊方向 — 偏差 15%] / [✅ 同向]
   Q2 盤口: [🔍 盤口壓縮 — Spread 0.45] / [✅ 正常]
   Q3 CLV歷史: [📈 正CLV模式 — 近5注平均 +7.2%] / [ℹ️ 數據不足]
   Q4 莊家邏輯: 「KT 上場 2-1 輸，散戶追買對手 T1 -1.5，+1.5 被推高，此 edge 有操盤邏輯支持。」
   Q5 陷阱盤: [✅ 無觸發] / [⚠️ Trap Line — EV 22% + 主流賽事 + 無新聞解釋]
   
   綜合: [X 個標記] → 建議 [降注 X% / 維持 / PASS]
```

---

## 5. Phase Γ Market Modifier（預留 — 50注+ROI<-15% 觸發）

> 以下 Modifier 在 Phase Γ 啟動前**不生效**。Phase Β 期間只做觀察和記錄。

| Market Lens 標記 | Kelly 修正 | 條件 |
|-----------------|-----------|------|
| [📊⚠️ 嚴重逆莊] | × 0.70 | 偏差 > 20% |
| [📊 逆莊方向] | × 0.85 | 偏差 10-20% |
| [🔍 盤口壓縮/拉闊] | × 0.90 | Spread 異常 |
| [📉 負CLV模式] | × 0.75 | 近5注 CLV < -5% |
| [⚠️ Trap Line 疑似] | × 0.50 或 PASS | ≥2 觸發條件 |
| [📈 正CLV模式] | × 1.0 (唔改) | 近5注 CLV > +5% |
| 無標記 | × 1.0 | 正常 |

### Phase Γ 啟動條件
```
IF cumulative_bets >= 50 
AND rolling_30day_ROI < -15%
AND Phase Β CLV 數據 >= 30 注:
  → 建議用戶啟動 Phase Γ
  → 需要用戶手動確認（唔會自動啟動）
```
