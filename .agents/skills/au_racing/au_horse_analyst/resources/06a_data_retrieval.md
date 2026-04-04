
## 數據擷取優先級鏈 (Data Extraction Priority Chain)

> [!IMPORTANT]
> **所有外部數據擷取必須按以下優先級執行,以減少延遲及避免瀏覽器干擾用戶:**

| 優先級 | 方法 | 適用場景 | 速度 |
|:---|:---|:---|:---|
| **1 (首選)** | `read_url_content` | 靜態頁面(Racenet 賽果/賽卡、Racing.com 場地狀態等 server-rendered 頁面) | ⚡ 極快 |
| **2** | `search_web` | 動態查詢(騎練組合勝率、場地偏差、Stewards Report 等需搜索引擎彙整的數據) | ⚡ 快 |
| **3 (最後手段)** | `browser_subagent` | 僅當以上兩種方法均失敗**且**目標頁面需要 JavaScript 互動時使用。**必須使用 Lightpanda 無頭瀏覽器**,嚴禁 Chromium/Playwright。Lightpanda 實例必須保持持久化。 | 🐌 慢 |

**故障轉移規則:** 每層方法失敗時,自動嘗試下一層。若 `read_url_content` 返回內容不完整(如關鍵表格缺失),視為失敗並降級至下一層。

## 外部數據搜索指引

> [!WARNING]
> **故障轉移:** 搜索不到數據 → `N/A (數據不足)`,**嚴禁猜測**。

### 必須搜索的 7 類輔助數據

> **注意:** 第 7 類(風向數據)僅在 Step 0.1 = `[STRAIGHT SPRINT]` 時為強制搜索項目,其餘賽事類型下為可選。

> [!WARNING]
> **賽季鎖定 (Season Lock):** 所有外部搜索必須附帶 `[Today's Date]` 或 `[Current Season]`,以確保回傳的是本季最新數據。嚴禁使用上賽季的跑道偏差或過期傷患報告。

| # | 類別 | 搜索目標 |
|:---|:---|:---|
| 1 | **場地狀態 (Going)** | 今日場地狀態 (Good/Soft/Heavy) + 欄位 (Rail Position) + 降雨預報。搜索字眼:`"[Track Name] track condition [Today's Date]"` 或 Racing.com / TAB.com.au |
| 2 | **跑道偏差 (Track Bias)** | 當日賽道配置歷史偏差(利領放或利後追)— 搜索須含 `[Today's Date]` |
| 3 | **競賽報告與傷患** | Stewards reports、獸醫報告、傷患紀錄、退賽 (Scratchings)。搜索字眼:`"Racing.com [Track] stewards reports [Today's Date]"` |
| 4 | **試閘結果 (Trial Results)** | 近期試閘名次+段速+催策程度。特別注意膠沙地 (Synthetic) 試閘 vs 本場草地之差異 |
| 5 | **血統投射 (Sire AWD)** | 父系 AWD (氣量指標)、子嗣場地/距離適應力。參照 `<sire_reference>` |
| 6 | **騎練合作數據** | 騎練組合近 30 天勝出率與上名率。搜索字眼:`"[Jockey] [Trainer] stats [Current Season]"`。若搜索無果 → `N/A`,維度默認 ➖ Neutral |
| 7 | **風向數據 [直線衝刺專用]** | **僅當 Step 0.1 = `[STRAIGHT SPRINT]` 時強制搜索。** 搜索字眼:`"Flemington wind direction [Today's Date]"` 或 BOM (Bureau of Meteorology) 即時數據。記錄風向(逆風/順風/側風)+ 風速 (km/h)。此數據直接注入 Step 7 風向能量模型及 `<straight_sprint_module>` 的覆蓋規則。 |

### [SIP-CH18-3] 退出馬名單最終核實 (Scratching Verification Protocol)

> [!IMPORTANT]
> **在開始任何馬匹分析之前,必須核實最終出賽名單。** 若使用非最終版本嘅 Racecard 數據,可能導致退出馬被遺漏分析或出賽馬匹數錯誤,進而影響 Speed Map、步速預測、小場覆寫協議等全局判斷。

**強制執行步驟:**
1. **出賽名單鎖定:** 從 Racecard 中提取所有馬匹及其退出 (SCR) 狀態。計算最終出賽馬匹數。
2. **早期數據警告:** 若分析開始時距離開賽 > 2 小時,在分析開頭標注 `⚠️ 退出名單待最終確認 — 出賽馬匹數及 Speed Map 可能因晚期退出而改變`
3. **出賽數量與 Speed Map 連動:** 若最終出賽馬匹數與分析時嘅假設不符(例如分析假設 6 匹但實際 7 匹),必須重新執行 Step 10 Speed Map 及 Step 7 EEM 評估
4. **邏輯基礎:** 2026-03-18 Caulfield Heath R8 覆盤中,Excess (#2) 被錯誤標記為退出(「Excess退出。6匹出賽」),但實際參賽並跑第 3。此錯誤導致整場分析基於錯誤嘅出賽馬匹數(6→7),Speed Map 缺少一匹跟前馬(Excess 2nd@800m)。

