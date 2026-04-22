
## 數據擷取優先級鏈 (Data Extraction Priority Chain)

> [!IMPORTANT]
> **所有外部數據擷取必須按以下優先級執行,以減少延遲及避免瀏覽器干擾用戶:**

| 優先級 | 方法 | 適用場景 | 速度 |
|:---|:---|:---|:---|
| **1 (Racenet 專用)** | `python3 .agents/skills/au_racing/claw_racenet_results.py --url "<URL>" --output_dir "<DIR>" --json`（Windows 或已配置環境可用 `python`）/ `au_race_extractor` | **Racenet 賽果、賽卡、Formguide** — 必須由 Python/curl_cffi/本地 Playwright 腳本處理 | ⚡ 快 |
| **2** | `read_url_content` | 非 Racenet 靜態頁面、公開公告、Racing.com 場地狀態等 server-rendered 頁面 | ⚡ 極快 |
| **3** | `search_web` | 動態查詢(騎練組合勝率、場地偏差、Stewards Report 等需搜索引擎彙整的數據) | ⚡ 快 |
| **4 (最後手段)** | 人手提供數據 / 停止並報告缺口 | 若 Python/curl_cffi/Claw Code 仍失敗，停止自動抽取並要求用戶提供數據或稍後重試。**嚴禁使用 `browser_subagent`、MCP Playwright、`read_browser_page` 作為 pipeline 數據來源。** | — |

**故障轉移規則:** Racenet Racecard/Formguide/Results 一律先用 Python extractor / Claw Code。若失敗,停止自動抽取並通知 Wong Choi 或用戶補資料；不可降級至瀏覽器工具。非 Racenet 輔助資料才可由 `read_url_content` 降級至 `search_web`。

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



## 分析步驟執行順序與數據流

### 執行順序表

| 執行階段 | 步驟 | 輸入依賴 | 輸出變數 |
|:---|:---|:---|:---|
| **賽事級(全場一次)** | Step 0 賽事日期鎖定 | 用戶原始數據 | `RACE_DATE` |
| | Step 0.1 賽事類型分類 | 用戶原始數據 + Step 0 | `RACE_TYPE` (`STRAIGHT SPRINT` / `STANDARD RACE`) |
| | Step 0.5 情境分類 | 用戶原始數據 + Step 0 + Step 0.1 | `情境標籤 (A/B/C/D)` |
| | Step 10 步速瀑布 | 全場馬匹跑法+檔位 + `RACE_TYPE` | `PACE_TYPE`, `LEADER_COUNT`, `COLLAPSE_POINT`, `RACE_SHAPE` |
| **馬匹級(每匹執行)** | Step 1 狀態週期 | 用戶原始數據 + `RACE_DATE` | 狀態週期標記 |
| | Step 2 引擎與距離 | Step 1 + `<sire_reference>` | 引擎類型、距離適性 |
| | Step 3 評分與班次 | Step 1, 2 | Rating Trajectory、級數標記 |
| | Step 4 步態與場地 | 外部搜索 + Step 0 | 場地適性 |
| | Step 5 裝備解碼 | 用戶原始數據 | 配備變動標記 |
| | Step 6 競賽報告法醫 | 外部搜索 + Step 1 | 寬恕檔案結論 |
| | Step 7 形勢與走位 | **Step 10** `PACE_TYPE` + Step 8 段速 | 走位形勢判定 |
| | Step 8 段速真偽 | `<class_par_reference>` + `<sectional_benchmarks>` | 段速修正判斷 |
| | Step 9 賽績交叉驗證 | 對手後續表現 | 強組/弱組 |
| | Step 11 騎師情報 | 外部搜索 | 騎師適配度 |
| | Step 12 風險與練馬師 | Steps 1-11 | 風險標記、訓練師訊號 |
| | Step 13 首次出賽馬 | 試閘+血統 | 首出評估 |
| | **綜合合成** | Steps 0.5, 1-13 | **最終 S/A/B/C/D 評級** |

### 關鍵數據流規則（必須嚴格遵守）

1. Step 0 的 `RACE_DATE` 必須注入 Step 1 作為間距日數計算基準。
2. **Step 0.1 的 `RACE_TYPE` 必須注入 Step 7、Step 10 及綜合合成框架,控制直線衝刺專用邏輯分支。**
3. Step 0.5 的情境標籤必須傳入綜合合成框架,影響「無條件/條件式」優勢判定。
4. Step 10 的 `PACE_TYPE` 必須注入 Step 7 的步速緩衝判定。
5. Step 8 的段速修正判斷必須作為 Step 7 的判斷基準。
6. Step 6 結論若為「上仗不可作準 (Forgive Run)」,必須回溯 Step 1 以最近可作準賽事重新錨定。
7. Step 6 若觸發 V 型反彈,必須強制升級 Step 0.5 情境標籤為 `[情境A-升級]`。
8. Step 10 若 `LEADER_COUNT = 2`,必須執行領放主導階梯判斷 `DOMINANCE_GAP`。
9. Step 10 若賽前退出導致場地 < 6 匹,必須執行小場覆寫協議。
10. **若 `RACE_TYPE = STRAIGHT SPRINT`,Step 7 必須啟用風向能量模型,Step 10 必須啟用直線步速模型,綜合合成必須檢查直線專用覆蓋規則。**
11. 綜合合成框架聚合所有前序步驟輸出,透過定性矩陣法生成最終評級。
