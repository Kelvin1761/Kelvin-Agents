
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
| | Step 8.2 走位-段速複合 | Step 7 形勢等級 + Step 8 段速Δ | 複合判讀（逆境段速/消耗抵消/實力見底） |
| | Step 8.3 賽事短評交叉驗證 | Racenet Race Comments + Step 2 引擎 | Engine Type 矛盾標記、受阻模式 |
| | Step 8.4 完成時間偏差 | `au_class_par_reference.json` + Step 4 場地 | 時間偏差趨勢 |
| | Step 9 賽績交叉驗證 | 對手後續表現 | 強組/弱組 |
| | Step 11 騎師情報 | 外部搜索 | 騎師適配度 |
| | Step 12 風險與練馬師 | Steps 1-11 | 風險標記、訓練師訊號 |
| | Step 13 首次出賽馬 | 試閘+血統 | 首出評估 |
| | **綜合合成** | Steps 0.5, 1-13 + `au_factor_interaction.md` | **最終 S/A/B/C/D 評級** |

### 關鍵數據流規則(必須嚴格遵守)

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
12. Step 8.2 的走位-段速複合判讀必須傳入綜合合成的 `形勢與走位` 半核心維度，作為 SYN-AU1/CON-AU1 觸發依據。
13. Step 8.3 的賽事短評矛盾標記若偵測到 Engine Type 矛盾,必須回溯 Step 2 重新審視引擎分類。
14. Step 8.4 的完成時間偏差趨勢若連續 3 場收窄,傳入 Step 1 狀態維度作為上升趨勢證據。
15. 綜合合成中的因素互動矩陣 (`au_factor_interaction.md`) 作為 Channel B 微調,與現有微調 (Channel A) 合計淨調整 ±2 級。
