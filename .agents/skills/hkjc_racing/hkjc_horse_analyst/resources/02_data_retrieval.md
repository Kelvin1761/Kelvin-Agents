## 外部數據搜索指引

> [!WARNING]
> **故障轉移:** 搜索不到數據 → `N/A (數據不足)`,**嚴禁猜測**。

### 必須搜索的 6 類輔助數據

> [!WARNING]
> **賽季鎖定 (Season Lock):** 所有外部搜索必須附帶 `[Current Season]` 或 `[Today's Date]`,以確保回傳的是本季最新數據。嚴禁使用上賽季的跑道偏差或過期傷患報告。

| # | 類別 | 搜索目標 |
|:---|:---|:---|
| 1 | **跑道偏差** | 當日賽道配置歷史偏差(利領放或利後追)— 搜索須含 `[Today's Date]` |
| 2 | **傷患與配備變動** | 獸醫報告、傷患紀錄、重大配備更改 — 搜索須含 `[Today's Date]` |
| 3 | **新馬血統 (Sire AWD)** | 父系 AWD (氣量指標)、子嗣在港適應力(早熟短途 vs 遲熟長途) |
| 4 | **試閘陷阱 (Trial Illusion)**| 搜索是否曾在從化草地閘或沙田泥地閘大勝,若本場跑其他場地,需警惕水分。 |
| 5 | **騎練合作數據** | 騎練組合近 30 天勝出率與上名率 — 若搜索無果 → `N/A`,維度默認 ➖ Neutral |
| 6 | **場地狀態 (Going)** | 今日場地狀態 (Good/Good-to-Yielding/Yielding/Soft) + 是否有降雨預報。搜索字眼:`"HKJC track condition [Today's Date]"` |


---


## 分析步驟執行順序與數據流

### 執行順序表

| 執行階段 | 步驟 | 輸入依賴 | 輸出變數 |
|:---|:---|:---|:---|
| **賽事級(全場一次)** | Step 0 步速瀑布 | 全場馬匹跑法+檔位 | `PACE_TYPE`, `LEADER_COUNT`, `COLLAPSE_POINT`, `BIAS_DIRECTION` |
| **馬匹級(每匹執行)** | Step 1 數據清洗 | 用戶原始數據 | 清洗後賽績序列 |
| | Step 2 情境比對 | Step 1 | `情境標籤 (A/B/C/D)` |
| | Step 2.5 騎練分析 | 外部搜索數據 | `JOCKEY_FIT`, `COMBO_PLACE_RATE` |
| | Step 3 加權 | Step 2 情境標籤 | 路程權重、新鮮度風險 |
| | Step 4 潘頓校正 | 騎師資料 | 潘頓標記 |
| | Step 5 穩定性 | Step 3 新鮮度 | 入三甲比例等級, `STABILITY_RANK`, `VOLATILITY_TYPE` |
| | Step 6 隱藏變數 | **Step 0** `PACE_TYPE` + `BIAS_DIRECTION` | 配備變動、步速協同標記 |
| | Step 7 風險標記 | 全部前序資料 | 風險標籤列表 |
| | Step 8 級數部署 | 賽績+練馬師 | 降班標記、練馬師訊號 |
| | Step 9 負重分析 | 負磅數據 | 負重變動標記 |
| | Step 10 段速法醫 | 段速數據 | 段速修正判斷、趨勢 |
| | Step 11 EEM | **Step 10** 段速修正判斷 | EEM 累積消耗等級 |
| | Step 12 寬恕 | **Step 11** EEM 累積消耗達「中等」自動加入 | 寬恕結論 |
| | Step 13 賽績線 | 對手後續表現 | 強組/弱組/N/A |
| | Step 14 評級聚合 | Steps 2-13 全部輸出 | **最終 S/A/B/C/D** |

### 關鍵數據流規則(必須嚴格遵守)

1. Step 0 的 `PACE_TYPE` 和 `BIAS_DIRECTION` 必須注入 Step 6 和 Output Item 11。
2. Step 2 的情境標籤必須傳入 Step 3 作為權重修正(A=升為 ✅ Strong, B=降為 ❌ Weak, C=不修正)。
3. Step 10 的段速修正判斷必須作為 Step 11 EEM 的判斷基準。
4. Step 11 EEM 累積消耗達「中等」或以上時,自動加入 Step 12 寬恕因素清單。
5. Step 12 結論若為「上仗不可作準」,必須回溯 Step 2 以最近可作準賽事重新錨定。
6. Step 14 聚合所有前序步驟輸出,透過定性矩陣法生成最終評級。
