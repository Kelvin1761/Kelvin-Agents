### 4a. 命中率統計

**Python 自動化統計(強制):**
```bash
python .agents/scripts/reflector_auto_stats.py "[TARGET_DIR]" "[RESULTS_FILE]"
```
此腳本會自動提取 Top 3/4 精選、比對實際賽果、計算所有 KPI。你只需引用腳本輸出嘅數據,**嚴禁自行手動數。**

> [!IMPORTANT]
> **位置命中率 (Place Hit Rate) 是最重要的 KPI**,優先於冠軍命中率。
> - 🏆 **黃金標準**:Top 3 精選全部跑入實際前三名
> - ✅ **良好結果**:Top 1 + Top 2 精選同時跑入實際前三名
> - ⚠️ **最低門檻**:Top 3 精選中,至少 2 匹跑入實際前三名

**必須統計以下指標:**

**A. 位置命中率(最重要 🔴)**
- 🏆 黃金標準率 (🎯 目標 ≥30%)
- ✅ 良好結果率 (🎯 目標 ≥40%)
- ⚠️ 最低門檻率 (🎯 目標 ≥60%)
- Top 3 單入位率 (🎯 目標 ≥80%)

**B. 冠軍命中率(次要)**
- Top 1 精選命中率
- Top 3 含冠軍率

**C. 整體校準**
- A 級以上馬匹平均名次 vs B 級以下平均名次

**D. 排名順序分析 🔴**
- Pick 3/4 超越 Pick 1/2 率 (目標 ≤30%)
- SIP 觸發門檻: 連續 ≥3 場出現逆序 → 標記為系統性偏差

### 4b. 逐場斷層分析
對每場失誤,檢查:
- **步速判斷是否正確?**
- **場地/偏差判斷是否正確?** — 含 Weather Prediction 準確度
- **EEM 判斷是否過度/不足?**
- **騎師因素** — 臨場部署變化
- **練馬師訊號** — 配備變動、首出訊號
- **血統適性** — 場地 × 血統交互效應 (AU 專屬)
- **barrier trial 訊號** — 是否錯過復出馬嘅試閘表現 (AU 專屬)
- **寬恕檔案** — 是否錯誤寬恕/懲罰

### 4c. 系統性模式識別
跨全日所有場次,尋找反覆出現嘅判斷偏差:
- 某類型因素是否被系統性忽略?
- 某條規則是否觸發過頻/過少?
- 評級矩陣中嘅某個維度判斷是否持續偏離實際?

### 4d. 主動引擎健康掃描 (Proactive Engine Health Scan)
> [!IMPORTANT]
> **此步驟為強制性**,不得跳過。即使命中率極佳 (>80%),仍必須完成。

**你必須逐一檢查以下 6 個維度:**

#### 4d-1. 過時邏輯偵測 (Stale Logic Detection)
- 引用已退役/轉會嘅騎師或練馬師?
- 引用已不再適用嘅賽事條件?
- 騎師 Tier 分級是否仍反映當前實力?

#### 4d-2. 斷裂邏輯偵測 (Disconnected Logic Detection)
- 某 Step 輸出未被後續 Step 引用?
- SIP 之間是否存在互相矛盾?

#### 4d-3. 缺失規則偵測 (Missing Rule Detection)
- 今日出現引擎冇處理規則嘅情境?
- 是否存在邊界條件?

#### 4d-4. 數據更新需求 (Data Freshness Check)
- 騎師戰術特徵是否有新趨勢?
- 練馬師訊號是否有新模式?
- 場地偏差/跑道模組是否仍然準確?

#### 4d-5. 規則校準驗證 (Rule Calibration Verification)
- 利用今日賽果驗證現有規則校準度

#### 4d-6. 輸出品質抽查 (Output Quality Spot Check)
- 抽查 2-3 場分析報告嘅輸出品質

### 4e. 逐場賽後敘事分析 (Narrative Post-Mortem)

> [!IMPORTANT]
> 針對每匹失敗嘅精選馬必須完成以下分析。

#### 4e-1. 沿途走位解讀 (Running Position Interpretation)
**走位模式判斷:**

| 走位模式 | 含義 | 覆盤判斷 |
|:---|:---|:---|
| `1-1-1-1` | 一放到底 | 步速利前領 |
| `X-X-X-↓` (末段跌位) | 後勁不繼 | 體力不足/步速崩潰 |
| `X-X-X-↑` (末段追上) | 後段爆發 | False Negative 候選 |
| 全程外疊 | 高消耗 | 檢查 EEM 判斷 |
| 位置穩定但末段跌 | 好位但跑唔動 | 🔴 實力不足 |

#### 4e-2. 可預測性評估 (Predictability Assessment)
- **可預見嘅陷阱**: 大外檔 + 大場 + 非前領型
- **不可預見嘅意外**: 臨場起步失誤、騎師改變部署

#### 4e-2.5. 分段時間法醫 (Sectional Time Forensics)
- 識別步速類型
- 識別段速質量（衰退率 >15% = 崩潰）
- 比對分析預測

#### 4e-3. Stewards' Report 深度審查 (AU 專屬)

**關鍵詞分類與裁定影響:**

| 關鍵詞 | 分類 | 裁定影響 |
|:---|:---|:---|
| bled / lame / respiratory | 🩸 醫療 | 自動 🟢 可寬恕 |
| bumped / hampered / checked / crowded | 🏇 干擾 | 視程度 🟡/🟢 |
| slow to begin / dwelt | ⚡ 起步 | 視歷史 🟡/🟢 |
| never a factor / weakened / eased | 💀 實力 | 🔴 邏輯錯誤 |
| over-raced / hung / laid in | 🐎 行為 | 視預見性 🟡 |
| lost shoe / gear | 🔧 裝備 | 🟢 不可預見 |

> ⚠️ 若 Stewards' Report 尚未發布,標記為「待查」並繼續。

#### 4e-4. 裁定分類 (Verdict Classification)

| 裁定 | 條件 | 對 SIP 影響 |
|:---|:---|:---|
| 🟢 可寬恕 | 醫療/嚴重干擾/極冷門/不可預見 | 唔需修改 SIP |
| 🔴 邏輯錯誤 | 走位正常+無異常+跑唔動 | 必須生成 SIP |
| 🟡 可避免陷阱 | 可預見但未計入 | 必須校準規則 |

> **每個裁定必須附帶 ≥2 個證據點,來自 ≥2 個不同數據源。**

### 4d-pre. Python 自動化輔助（強制前置）

```bash
# 引擎健康掃描
python .agents/scripts/engine_health_scanner.py --domain au --resources-dir ".agents/skills/au_racing/au_horse_analyst/resources"

# SIP 衝突掃描
python .agents/scripts/sip_conflict_scanner.py --domain au --resources-dir ".agents/skills/au_racing/au_horse_analyst/resources"

# 規則觸發率統計
python .agents/scripts/rule_trigger_tracker.py --domain au --resources-dir ".agents/skills/au_racing/au_horse_analyst/resources" --analysis-dir "[TARGET_DIR]"

# 敘事覆盤數據抽取
python .agents/scripts/narrative_postmortem_extractor.py "[RESULTS_FILE]" "[TARGET_DIR]" --all --domain au
```

## Step 5: 輸出覆盤報告

### Step 5-pre: 生成報告骨架（Python 強制）
```bash
python .agents/scripts/reflector_report_skeleton.py "[TARGET_DIR]" "[RESULTS_FILE]" --domain au --output "[TARGET_DIR]/[Date]_[Venue]_覆盤報告.md"
```
> LLM 只需填入 `{{LLM_FILL}}` 標記嘅定性分析欄位。**嚴禁 LLM 手動砌報告框架。**

### Step 5-post: 報告驗證（Python 強制）
```bash
python .agents/scripts/reflector_verdict_validator.py "[TARGET_DIR]/[Date]_[Venue]_覆盤報告.md" --domain au --resources-dir ".agents/skills/au_racing/au_horse_analyst/resources"
```
> 未通過驗證嘅報告**嚴禁**提交畀用戶。

## Step 5.5: 場地去水覆核 (AU 專屬)

將 Step 2.5 嘅場地去水系數對比結果加入報告:
```markdown
## 🌤️ 場地預測覆盤
- **Weather Prediction 預測:** {{LLM_FILL}}
- **實際最終掛牌:** {{LLM_FILL}}
- **偏差分析:** {{LLM_FILL}}
- **drainage_coefficient 更新:** {{LLM_FILL}}
```

## Step 6: 等待用戶審批 + SIP 套用

### 6a. 等待審批
向用戶提交覆盤報告,**強制停止所有行動**,等待用戶決定。

### 6b. SIP 套用(用戶批准後)
修改對應 Analyst resource 檔案,同時更新 `00_sip_index.md`。

### 6c. 🚨 強制 Validator 調用協議 (P31)

> [!CAUTION]
> SIP 套用完成後,必須立即輸出驗證提示。嚴禁只完成 6b 就停止。

**Step 6c-1 — 輸出驗證提示:**
```
🔬 SIP 已套用完成。修改清單:
{SIP_CHANGELOG_SUMMARY}

為確保新邏輯真正改善預測準確度,需要進行 LLM 歷史回測驗證:
→ 揀選 2-3 場與 SIP 相關嘅歷史賽事
→ 以完整 14-step 引擎重新分析,比對新舊 Top 4

是否開始回測驗證?(Y/N)
```

**Step 6c-2 — 用戶確認後:**
立即執行 Step 7 (SIP Validation 3-Tier) 流程。

**Step 6c-3 — 用戶拒絕:**
記錄「用戶選擇跳過驗證」,結束流程。
