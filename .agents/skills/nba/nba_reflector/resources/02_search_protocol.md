# NBA Reflector — 數據搜索與比對協議

---

## 0. API-First Protocol (v2.2.0 — P22 Python-First Compliance)

> [!IMPORTANT]
> **本文件嘅 search_web 規則僅喺 API 擷取失敗時啟用。**
>
> 正常覆盤流程應使用 Step 2 定義嘅 Python script 管道：
> 1. `fetch_nba_results.py` → Box Score（主引擎）
> 2. `fetch_nba_pbp.py` → Play-by-Play（條件觸發）
> 3. `verify_props_hits.py` → Props 命中驗證（自動）
>
> 只有以上 3 步全部失敗時，才退回以下 search_web 手動搜索。
> 若使用 Fallback，覆盤報告必須標記 `DATA_SOURCE: SEARCH_WEB (FALLBACK)`。

---

## 1. Box Score 搜索規則（Fallback Only）

### 搜索格式
```
「[Team A] vs [Team B] box score [US_DATE]」
```

### 搜索優先級
| 優先級 | 來源 | 備註 |
|:---|:---|:---|
| 🥇 | ESPN | 最可靠 |
| 🥈 | Basketball Reference | 最詳細 |
| 🥉 | CBS Sports | 交叉比對 |
| 4 | NBA.com | 官方 |

### 每場賽事提取
- 最終比分
- 每位**被預測涉及嘅球員**嘅實際數據:PTS / REB / AST / MIN(上場時間)
- 重大賽中事件(球員受傷離場、被驅逐、犯規麻煩等)

---

## 2. 失敗處理

| 失敗情境 | 處理方式 |
|:---|:---|
| 單場搜索連續失敗 3 次 | 停止,標記 `N/A (賽果數據不足)`,繼續下一場 |
| 數據不完整 | 標記缺失項,不猜測 |
| 搜唔到特定球員 Box Score | 標記 `N/A (數據不足)`,嚴禁自行猜測 |

---

## 3. 數據隔離

> [!CAUTION]
> 每場賽事嘅 Box Score 搜索必須獨立執行,嚴禁將前一場嘅球員數據帶入下一場。

---

## 4. 深度比對框架

### 4a. Leg 命中率統計
- 穩膽組合 Leg 命中率(預測盤口 vs 實際數據)
- 價值組合 Leg 命中率
- 高賠組合 Leg 命中率
- 整體組合命中率(3 組之中幾組全中)

### 4b. 逐 Leg 斷層分析
對每個未命中嘅 Leg,在 `<thought>` 中檢查:
- **Adj Prob vs 隱含勝率 (Edge) 偏差驗證** — Edge 計算是否準確？實際命中率與 Adj Prob 差距大喺地方？
- **賠率準確度** — 分析時嘅 @賠率與最終 Bet365 開盤賠率是否一致？
- **CoV 波動率判斷是否正確?** — 實際波動是否與預測分級吻合
- **情境調整是否足夠?** — B2B / 疲勞 / 節奏 / 傷病復出嘅調整是否恰當
- **防守對位判斷是否正確?** — 預測嘅防守大閘是否真正限制了目標球員
- **DvP 防守排名是否過度依賴?** — 團隊防守數據有冇因個別球員缺陣而失真
- **盤口線設定是否過進取?** — 穩膽線 / 價值線嘅計算是否留足安全邊際
- **傷病 / 上場時間判斷** — 球員是否因傷提早離場或上場時間被限制
- **比賽劇本判斷** — 大比分拋離 / Blowout 導致主力提早打卡
- **SGP 相關性** — 同場 Leg 之間是否存在未被偵測嘅互斥 / 天花板衝突
- **新聞情境** — 是否錯過重要嘅場外因素（交易傳聞、球隊內部不和、教練變陣）)

### 4c. 系統性模式識別
跨全日所有場次,尋找反複出現的判斷偏差:
- 某類型因素是否被系統性忽略?（例如:B2B 客場嘅 PTS 下跌幅度被低估）
- 某條規則是否觸發過頻/過少?（例如:Safety Gate 攔截過多實際可中嘅 Leg）
- CoV 分級嘅某個閾值是否需要調整?
- Bet365 盤口 Milestone 嘅選擇邏輯是否有系統性偏差?
- 防守大閘資料庫（`nba_data_extractor/resources/03_defensive_profiles.md`）是否需要更新?
- **Blowout 風險預判準確度** — 分析中標記了 Blowout 風雛嘅場次，實際有幾多係真的 Blowout？讓分、總分盤口判斷與實際結果之差？
- **odds_source 影響** — 使用 BET365_LIVE odds 嘅場次 vs ESPN/其他來源嘅場次，命中率有冇顯著差異？

### 4d. V5 Data Brief → LLM 分析品質審計 (P36 Anti-Rubber-Stamp)

> **審視 LLM 係咪真正做到獨立分析，定係只係 copy-paste Python 建議。**

- **Must-Respond Protocol 遵守度** — LLM 有冇逐一回應 `top_legs_by_edge` 前 5 名？有冇明確標記 ✅/⚡/❌？
- **獨立見解** — LLM 有冇提出至少 1 個 Python 未標記嘅潛在機會或風雛？
- **核心邏輯原创性** — `✍️ Analyst 深度補充` 內容係咪真正基於籃球知識，定係只係重新包裝 Python 嘅 8-Factor breakdown？
- **組合自主性** — LLM 揀嘅 Combo 與 Python `suggested_combo` 嘅差異度幾高？100% 一致 = Rubber Stamp 嫌疑
- **賠率修正** — LLM 有冇主動修正 Python 建議中嘅賠率錯誤（若存在）？
