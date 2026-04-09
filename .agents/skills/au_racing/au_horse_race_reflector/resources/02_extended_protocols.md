**你必須逐一檢查以下 6 個維度,並在覆盤報告中為每一項給出明確判定 (✅ 無需改動 / ⚠️ 觀察中 / 🔧 建議修改):**

#### 4d-1. 過時邏輯偵測 (Stale Logic Detection)
掃描引擎規則中是否有:
- 引用了已退休/轉會/暫停的騎師或練馬師?
- 引用了已不再適用的賽事條件(如已改建的跑道、已更改的欄位設置)?
- 任何 SIP 的觸發條件是否因近期規律變化而需調整閾值?
- 騎師 Tier 分級是否仍然反映當前實力排名?
- 血統參考 (`03a-03d_sire_*.md`) 中是否有新興種馬/停產種馬未更新?

#### 4d-2. 斷裂邏輯偵測 (Disconnected Logic Detection)
掃描引擎規則中是否有:
- 某 Step 的輸出未被任何後續 Step 引用(產出了數據但無人消費)?
- 某 Step 引用了不存在的維度/標記名稱?
- 某條覆蓋規則(Override)的觸發條件在實際賽事中從未被滿足過(死規則)?
- SIP 之間是否存在互相矛盾或重複計算的情況?
- 場地模組 (`04b_track_*.md`) 之間的邏輯是否一致?

#### 4d-3. 缺失規則偵測 (Missing Rule Detection)
根據今日賽事的實際情境,檢查是否存在:
- 今日出現了引擎沒有處理規則的情境(例如:新的跑道偏差類型、新的場地掛牌等級)?
- 今日有馬匹因素在引擎中完全沒有對應規則?
- 是否存在「邊界條件」——馬匹剛好不符合觸發門檻但實際表現顯示應該被觸發?
- 是否有新場地/新賽場尚未建立對應的 `04b_track_*.md` 模組?

#### 4d-4. 數據更新需求 (Data Freshness Check)
檢查引擎中的靜態數據是否需要更新:
- 騎師戰術特徵 (`07_jockey_profiles.md`) 是否有新的表現趨勢未被記錄?
- 練馬師訊號是否有新模式尚未加入(例如:新練馬師的初出馬模式)?
- 場地模組描述是否仍然反映當前實際跑道特性?
- 血統參考數據是否需要補充新種馬/新血統線?
- 班次標準 (`03e_class_standards.md`) 的時間段是否需要刷新?

#### 4d-5. 規則校準驗證 (Rule Calibration Verification)
利用今日實際賽果驗證現有規則的校準度:
- 「致命死檔 (Fatal Draw)」觸發的馬匹,今日實際是否大敗?若否 → 是否需放寬?
- 「頂級騎師檔位豁免 (SIP-R14-2)」觸發時,騎師是否真的克服了外檔?
- 「見習騎師減磅 (SIP-7)」觸發的馬匹,表現是否符合預期?
- 濕地/膠沙地模組的判斷是否與實際場地表現吻合?
- 「卡士碾壓」觸發的馬匹是否確實碾壓對手?

#### 4d-6. 輸出品質抽查 (Output Quality Spot Check)
抽查 2-3 場分析報告的輸出品質:
- 分析是否出現模板化/重複數據?
- Top 3 排序的邏輯是否一致(同級別馬匹的排名是否有明確區分理由)?
- 段速/穩定性/場地適性數據是否看起來合理(非默認值填充)?
- 血統適性判定是否引用了具體的 sire reference 數據?

> **輸出要求:** 即使所有 6 項均為 ✅,仍必須在覆盤報告中列出每項的簡短判定理由(各 1-2 句)。嚴禁簡單寫「無需改善」而不提供具體檢查結果。

### 4e. 逐場賽後敘事分析 (Narrative Post-Mortem)
> [!IMPORTANT]
> **此步驟為強制性**,針對每匹失敗嘅精選馬(預測 Top 3 但實際未入三甲)必須完成以下分析。
> 目的:區分「邏輯錯誤」(Bad Logic — 需要修改 SIP)同「運氣差」(Bad Luck — 可寬恕),避免因個別事件過度修改模型。

#### 4e-1. 沿途走勢擷取 (Running Position Extraction)
對每匹失敗嘅精選馬,從賽果數據中提取沿途走勢:
- 起步位置(閘位 vs 實際起步排位)
- 各段走位(領先/中間/後方 × 內欄/中間/外疊)
- 直路走位變化(有冇被困、讓出、走大外疊)
- 最終衝線走勢(加速/維持/後勁不繼)
- 澳洲特有:衝線前是否受風向影響(直線衝刺賽尤其重要)

#### 4e-2. 可預測性評估 (Predictability Assessment)
對每個走位劣勢,判斷 Analyst 係咪可以預見:
- **可預見嘅陷阱**:大外檔 + 大場 + 非前領型 = 被困外疊機率極高 → Analyst 應該已計入
- **可預見嘅步速受害**:明顯嘅慢步速 + 後追馬 = 步速劣勢 → Analyst 應該已計入
- **可預見嘅場地受害**:場地升級至 Heavy 但 Analyst 未啟動 SIP-1 雙軌敏感度分析
- **不可預見嘅意外**:臨場突然起步失誤、被旁邊馬匹夾擠、騎師臨時改變部署

> **判斷標準**:如果 Analyst 嘅引擎規則已涵蓋此類情境(例如 Step 7 死檔規則、SIP-R14-2 騎師豁免)但未正確觸發 → 屬於「可避免陷阱」。如果引擎完全冇對應規則 → 屬於「缺失規則」(記入 SIP)。如果屬臨場意外 → 屬於「不可預見」。

#### 4e-3. Stewards' Report 審查 (Stewards' Report Review)
使用 `search_web` 搜索當日 Stewards' Report(Racing NSW / Racing Victoria / Racing Queensland 官方來源),提取以下關鍵資訊:
- **醫療問題**:流鼻血 (Bled)、跛行 (Lame)、呼吸異常 → 自動標記為「不可抗力」
- **嚴重干擾**:被判犯規、受到嚴重碰撞或夾擠 → 標記干擾程度(輕微/中度/嚴重)
- **裝備/部署問題**:口銜不順、馬匹不願上閘 → 可能屬臨場意外
- **騎師報告**:騎師對馬匹表現嘅評語(若有)
- **Barrier Trial 對比**:若馬匹近期有 barrier trial,比較 trial 表現與正賽表現嘅差異

> ⚠️ **失敗處理**:若搜索不到 Stewards' Report(例如報告尚未發布),標記為「Stewards' Report 待查」並繼續。嚴禁因此跳過整個 4e。

#### 4e-4. 裁定分類 (Verdict Classification)
對每匹失敗嘅精選馬,根據 4e-1 至 4e-3 嘅綜合證據,給出以下三類裁定之一:

| 裁定 | 條件 | 對 SIP 嘅影響 |
|:---|:---|:---|
| 🟢 **可寬恕 (Forgivable / Bad Luck)** | 有 Stewards' Report 紀錄嘅醫療問題或嚴重干擾;極冷門翻盤(賠率 >50 倍);不可預見嘅臨場意外;極端濕地爆冷(場地突然升至 Heavy 9+) | 唔需要修改 SIP,記入「⚠️ 單場特殊因素」 |
| 🔴 **邏輯錯誤 (Logic Failure / Bad Logic)** | 冇合理嘅走位/醫療藉口;引擎規則已涵蓋但判斷方向錯誤;或者馬匹本身實力被高估 | **必須**生成對應 SIP,指明需要修改嘅具體規則 |
| 🟡 **可避免陷阱 (Avoidable Trap)** | 走位劣勢係可預見嘅(例如死檔、步速不利)但 Analyst 未觸發對應規則;或規則閾值需要調整 | **必須**生成對應 SIP,聚焦於規則觸發條件嘅校準 |

> **嚴格要求**:每個裁定必須附帶 ≥2 個證據點支持(走位數據 + Stewards' Report / 步速分析 / 引擎規則比對)。嚴禁無證據裁定。

### 4d. Python 自動化輔助（強制前置）

> [!IMPORTANT]
> **以下 Python 腳本必須在 LLM 開始 Step 4d-5 之前執行。**
> 目的：將機械性數據抽取工作交畀 Python，LLM 只需聚焦高層次法醫判斷。

**4d-pre-1. 引擎健康掃描（自動化部分）:**
```bash
python .agents/scripts/engine_health_scanner.py --domain au --resources-dir ".agents/skills/au_racing/au_horse_analyst/resources"
```
此腳本自動檢查 4d-1（過時邏輯）、4d-2（斷裂邏輯）、4d-4（數據新鮮度）。LLM 只需處理 4d-3、4d-5、4d-6。

**4d-pre-1b. SIP 衝突掃描:**
```bash
python .agents/scripts/sip_conflict_scanner.py --domain au --resources-dir ".agents/skills/au_racing/au_horse_analyst/resources"
```
自動構建 SIP 規則關係圖，偵測方向衝突、重複計算、交叉引用、過時引用。LLM 只需判斷衝突係有意制衡定真衝突。

**4d-pre-1c. 規則觸發率統計:**
```bash
python .agents/scripts/rule_trigger_tracker.py --domain au --resources-dir ".agents/skills/au_racing/au_horse_analyst/resources" --analysis-dir "[TARGET_DIR]"
```
統計每條 SIP 嘅實際觸發次數，識別死規則（從未觸發）同過度觸發（>80%），LLM 只需判斷是否需修改門檻。

**4d-pre-1d. 引擎覆蓋率矩陣:**
```bash
python .agents/scripts/engine_coverage_matrix.py --domain au --resources-dir ".agents/skills/au_racing/au_horse_analyst/resources" --analysis-dir "[TARGET_DIR]"
```
計算引擎規則覆蓋率（類似 code coverage），識別未被使用嘅死代碼規則。

**4d-pre-2. 敘事覆盤數據抽取:**
```bash
python .agents/scripts/narrative_postmortem_extractor.py "[RESULTS_FILE]" "[TARGET_DIR]" --all --domain au
```
自動抽取失敗精選馬嘅走位、Stewards' Report 關鍵字分類。LLM 只需做 4e-4 裁定。

## Step 5: 輸出覆盤報告

### Step 5-pre: 生成報告骨架（Python 強制）
```bash
python .agents/scripts/reflector_report_skeleton.py "[TARGET_DIR]" "[RESULTS_FILE]" --domain au --output "[TARGET_DIR]/[Date]_[Venue]_覆盤報告.md"
```
> 此腳本自動生成完整報告框架，預填所有命中率表格、逐場比對、FP/FN 名單。
> LLM 只需填入 `{{LLM_FILL}}` 標記嘅定性分析欄位。
> **嚴禁 LLM 手動砌報告框架** — 必須使用腳本生成嘅骨架。

### Step 5-post: 報告驗證（Python 強制）
報告撰寫完成後，執行裁定驗證器：
```bash
python .agents/scripts/reflector_verdict_validator.py "[TARGET_DIR]/[Date]_[Venue]_覆盤報告.md" --domain au --resources-dir ".agents/skills/au_racing/au_horse_analyst/resources"
```
> 自動驗證每個裁定有 ≥2 證據點、SIP 引用存在、所有必要 section 齊全。
> 未通過驗證嘅報告**嚴禁**提交畀用戶。

按照以下格式生成報告,保存為 `[Date]_[Venue]_覆盤報告.md` 於 `TARGET_DIR` 內:

```markdown
# 🔍 AU 賽後覆盤報告
**日期:** [日期] | **馬場:** [馬場] | **場次:** [總場次]
**預測掛牌:** [Weather Prediction 預測] | **實際掛牌:** [實際]

## 📊 整體命中率

### 🔴 位置命中率(最重要 KPI)
| 指標 | 數值 | 目標 | 達標? |
|:---|:---|:---|:---|
| Top 2 雙入位率(首選+次選同入前三) | X/Y (Z%) | ≥40% | [✅/❌] |
| Top 3 雙入位率(Top 3 中 ≥2 匹入前三) | X/Y (Z%) | ≥50% | [✅/❌] |
| Top 3 單入位率(Top 3 中 ≥1 匹入前三) | X/Y (Z%) | ≥80% | [✅/❌] |

### 冠軍命中率(次要)
| 指標 | 數值 |
|:---|:---|
| Top 1 命中率 | X/Y (Z%) |
| Top 3 含冠軍率 | X/Y (Z%) |
| A級以上平均名次 | X.X |
| B級以下平均名次 | X.X |
| 場地預測準確度 | [預測 vs 實際] |

## 📋 逐場覆盤摘要

### 第 X 場 — [✅ 命中 / ❌ 失誤 / ⚠️ 部分命中]
**賽事規格:** [距離 / 班次 / 場地]
**實際前三名:** [X]
**預測 Top 3:** [X]
**關鍵偏差:** [一句話總結失誤原因]
**偏差類型:** [步速誤判 / EEM偏差 / 練馬師訊號遺漏 / 騎師變陣 / 場地偏差 / 血統誤判 / 寬恕錯誤 / 負重誤判 / 風向誤判]

## 🔴 False Positives (看高但大敗)
| 場次 | 馬匹 | 預測評級 | 實際名次 | 失誤根因 |
|:---|:---|:---|:---|:---|

## 🟢 False Negatives (看低但勝出/上名)
| 場次 | 馬匹 | 預測評級 | 實際名次 | 遺漏因素 |
|:---|:---|:---|:---|:---|

## 🌤️ 場地預測覆盤
- **Weather Prediction 預測:** [X]
- **實際最終掛牌:** [X]
- **偏差分析:** [準確 / 偏軟 / 偏硬 — 原因分析]
- **對分析的影響:** [因掛牌偏差導致哪些判斷出錯]

## 🧠 系統性改善建議 (Systemic Improvement Proposals)

### SIP-[DATE]-01: [建議標題]
- **問題:** [描述反覆出現的判斷偏差]
- **證據:** [列舉支持此結論的多場實例]
- **目標檔案:** [指明需要修改嘅具體 resource 檔案，例如 `02d_eem_pace.md` Step 7 EEM 能量]

**🧠 修正方案探索(AG Kit Brainstorming — 自動觸發):**
> 讀取 `.agent/skills/brainstorming/SKILL.md`,對每個 SIP 自動生成 ≥2 個結構化修正方案:

| 方案 | 修改內容 | ✅ Pros | ❌ Cons | 📊 Effort |
|:---|:---|:---|:---|:---|
| A | [具體修改] | [好處] | [風險] | Low/Med/High |
| B | [替代修改] | [好處] | [風險] | Low/Med/High |

**💡 Recommendation:** [推薦方案 + 理據]

- **影響範圍:** [此修改會影響哪些場景]

### SIP-2: [建議標題]
...

## 🎭 敘事覆盤 (Narrative Post-Mortem)

| 場次 | 馬匹 | 預測評級 | 實際名次 | 沿途走勢摘要 | Stewards' Report | 裁定 | 證據 |
|:---|:---|:---|:---|:---|:---|:---|:---|
| [X] | [馬名] | [A/B+/...] | [名次] | [走位關鍵描述] | [醫療/干擾/無] | [🟢/🔴/🟡] | [≥2 個證據點] |

### 裁定統計
- 🟢 可寬恕 (Bad Luck): X 匹
- 🔴 邏輯錯誤 (Bad Logic): X 匹 → 對應 SIP: [SIP-X, SIP-Y]
- 🟡 可避免陷阱 (Avoidable Trap): X 匹 → 對應 SIP: [SIP-Z]

## ⚠️ 單場特殊因素 (Non-Systemic, 僅供記錄)
- [不建議修改模型的個別事件,如意外傷患、極端天氣等]

## 🔬 引擎健康掃描結果 (Engine Health Scan)

| 檢查維度 | 判定 | 簡述 |
|:---|:---|:---|
| 4d-1 過時邏輯 | [✅/⚠️/🔧] | [1-2句判定理由] |
| 4d-2 斷裂邏輯 | [✅/⚠️/🔧] | [1-2句判定理由] |
| 4d-3 缺失規則 | [✅/⚠️/🔧] | [1-2句判定理由] |
| 4d-4 數據更新 | [✅/⚠️/🔧] | [1-2句判定理由] |
| 4d-5 規則校準 | [✅/⚠️/🔧] | [1-2句判定理由] |
| 4d-6 輸出品質 | [✅/⚠️/🔧] | [1-2句判定理由] |
```


> **P32 — Knowledge Graph 整合:** 生成覆盤報告後,使用 Memory MCP 將以下關鍵發現寫入 Knowledge Graph:
> - 場地偏差觀察(Entity: `{VENUE}_{DATE}_bias`,Observations: Rail Position / 內外欄偏差 / 跨道特性)
> - 天氣預測準確度(Entity: `weather_accuracy_{DATE}`,記錄預測掛牌 vs 實際掛牌)
> - False Positive/Negative 模式(Entity: `FP_pattern_{SIP_ID}` 或 `FN_pattern_{SIP_ID}`)
> - 引擎健康掃描結果(Entity: `engine_health_{DATE}`)
> - 這樣下次覆盤同一場地時,Reflector 可以先查詢 `read_graph` 發現過往場地偏差歷史。

## Step 5.5: Instinct Evolution（P35 新增）

> **設計理念:** 受 ECC `continuous-learning-v2` 嘅 Instinct 模型啟發。
> 將一次性嘅 SIP 修改升級為帶 confidence score 嘅長期學習機制。

覆盤報告生成後，執行 instinct 評估：
```bash
python3 .agents/scripts/instinct_evaluator.py "{TARGET_DIR}" \
  --registry ".agents/skills/shared_instincts/instinct_registry.md" \
  --domain au \
  --reflector-report "{TARGET_DIR}/{DATE}_{VENUE}_覆盤報告.md"
```

將評估結果加入覆盤報告嘅新 section：
```markdown
## 🧬 Instinct Evolution Report
[腳本輸出]

### 趨勢分析
- 上升中 (confidence ↑): [列表]
- 下跌中 (confidence ↓): [列表]
- 建議 Deprecate: [列表]
- 建議升級為 Core Rule: [列表]
```

> 此步驟失敗唔影響覆盤報告。首次使用時 registry 為空，腳本會提示需要先完成一次覆盤以初始化。

## Step 6: 等待用戶審批 + SIP 套用 + 驗證提醒

### 6a. 等待審批
向用戶提交覆盤報告路徑同摘要,並**強制停止所有行動**,等待用戶回覆決定是否採納建議。
**嚴禁未經審批就修改任何 Agent 檔案。**

### 6b. SIP 套用(用戶批准後)
用戶批准邊啲 SIP 後,按指示修改對應嘅 Analyst resource 檔案。同時更新 `00_sip_index.md`。

**Changelog 維護:**
每次套用新 SIP 後,必須更新 `../au_horse_analyst/resources/sip_changelog.md`:
- 新增一個 entry(最新嘅放最上面)
- 保留最近 5 條記錄
- 超過 5 條嘅舊記錄移除(已由 00_sip_index.md 永久記錄)

### 6c. 🚨 強制 Validator 調用協議 (Mandatory Validator Invocation — P31)

> [!CAUTION]
> **🚨 MUST_INVOKE_VALIDATOR — 強制驗證調用(P31 — Priority 0):**
>
> **歷史教訓:** Reflector 完成 SIP 套用後經常只顯示「建議盲測驗證」嘅文字提示,但從未真正調用 Validator。根本原因:Step 6c 只係被動提示,冇執行協議、冇數據交接格式、冇自檢機制。
>
> **強制規定:**
> 1. **SIP 套用完成後,Validator 調用提示係你嘅最後一個強制動作。** 唔可以喺 6b 完成後就停止。
> 2. **提示文字中所有 `{VARIABLE}` 必須被實際值替換。** 嚴禁輸出未填充嘅佔位符。
> 3. **用戶確認後,你必須立即執行 Validator 調用**(見下方調用協議),唔可以再停低等下一個 prompt。
> 4. **自檢觸發器:** 若你完成 6b(SIP 套用)但冇執行 6c(Validator 提示)→ 你已違規 → 立即補上。

**Step 6c-1 — 輸出驗證提示(SIP 套用完成後立即執行):**

```
🔬 SIP 已套用完成。修改清單:
{SIP_CHANGELOG_SUMMARY}

為確保新邏輯真正改善預測準確度,需要進行盲測驗證:
→ 調用 AU Reflector Validator,以更新後嘅規則重新分析今日 {VENUE} 賽事
→ 驗證將由 Race 1 開始,逐場進行,每場通過先可進入下一場
→ 預計需要分析 {TOTAL_RACES} 場(SIP Scope Analysis 會決定實際數量)

是否要從 Race 1 開始盲測驗證?(Y/N)
```

**Step 6c-2 — 用戶確認後,立即調用 Validator(強制執行):**

若用戶確認 (Y),你**必須立即**讀取 `AU Reflector Validator` 技能 (`au_reflector_validator/SKILL.md`),並以以下完整數據包調用:

```
🔬 Validator 調用指令:
────────────────────
SKILL: AU Reflector Validator
TARGET_DIR: {TARGET_DIR 絕對路徑}
VENUE: {VENUE}
DATE: {DATE}
TOTAL_RACES: {TOTAL_RACES}
SIP_CHANGELOG: |
  {逐條列出本次修改嘅 SIP,格式如下:}
  - SIP-XX: [標題] → 修改咗 [resource 檔案名] 嘅 [Step/規則]
  - SIP-YY: [標題] → 修改咗 [resource 檔案名] 嘅 [Step/規則]
REFLECTOR_REPORT: {覆盤報告檔案路徑}
────────────────────
```

> **執行要求:** 你必須喺同一個 session 中開始執行 Validator 嘅 Step 1(初始化),唔可以只輸出調用指令然後停低。Validator 嘅完整流程(Step 1 → Step 1.5 Scope Analysis → 呈現驗證計劃)應喺用戶確認後立即啟動。

**Step 6c-3 — 用戶拒絕:**

若用戶拒絕 (N):
- 記錄「用戶選擇跳過 Validator 驗證」到 `_session_issues.md`
- 輸出:「⚠️ 已記錄跳過驗證。SIP 修改已套用但未經盲測驗證。日後可隨時執行 `@au reflector validator` 進行補測。」
- 結束流程

### 6d. 設計模式建議 (Design Pattern Proposal)
若本次覆盤發現咗一個**通用嘅失敗模式**(唔係個別賽事嘅特殊情況,而係會影響未來所有 agent 設計嘅教訓),你必須額外提出一個 Design Pattern 建議:

```
📐 新設計模式建議:
- **模式名稱:** [Pattern Name]
- **問題:** [What went wrong and why it's systemic]
- **解決方案:** [How future agents should handle this]
- **來源:** [哪場賽事 / 哪個 agent 觸發]
- **建議加入:** `agent_architect/resources/design_patterns.md`
```

用戶批准後,由用戶或 Agent Architect 將此模式加入 design_patterns.md。

# Recommended Tools & Assets
- **Tools**:
  - `run_command`:用於執行 `extract_race_result.py`。
  - `view_file`:讀取過往賽前預測報告與剛抓取的賽果檔。
  - `search_web`:若需要補充搜索實際賽日情報(如當日實際偏差報告、Stewards Report)。
  - Safe-Writer Protocol (P33-WLTM)：heredoc → /tmp → base64 → safe_file_writer.py 保存覆盤報告。⚠️ write_to_file 已封殺（改用 safe_file_writer.py）。
- **Assets**:

- **MCP Tools (P32 新增)**:
  - `read_graph` / `search_nodes` — Knowledge Graph 查詢(檢查過往場地偏差觀察、騎練組合紀錄)
  - `read_query` / `list_tables` — SQLite 歷史數據查詢(查等評級歷史、命中率追蹤)
  - `create_entities` / `create_relations` — 將覆盤發現寫入 Knowledge Graph(SIP 觸發模式、引擎健康掃描結果)
  - `scripts/extract_race_result.py`:專門用於解析 Racenet 賽果的腳本。

# Test Case
**User Input:** `「幫我覆盤今日 Caulfield Heath 賽事:https://www.racenet.com.au/results/horse-racing/caulfield-heath-20260304」`
**Expected Agent Action:**
1. 記錄 `DATE` = 2026-03-04,`VENUE` = Caulfield Heath,`TARGET_DIR` = 對應資料夾。
2. 執行 `extract_race_result.py`,抓取並生成含全日賽果的文檔至 `TARGET_DIR`。
3. 搜尋並讀取 `TARGET_DIR/Race Analysis/` 中的所有 `*Analysis.md` 檔案。
4. 逐場比對 Top 3 預測與實際賽果,執行 False Positive / False Negative 分析,識別系統性偏差模式,覆盤場地預測準確度。
5. 生成覆盤報告 `2026-03-04_Caulfield Heath_覆盤報告.md`。
6. 向用戶提交報告摘要,等待審批。
