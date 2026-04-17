### 4a. 命中率統計

**Python 自動化統計(強制):**
覆盤分析前,先行以下腳本自動計算所有命中率指標,取代人手計算:
```bash
python .agents/skills/hkjc_racing/hkjc_reflector/scripts/reflector_auto_stats.py "[TARGET_DIR]" "[RESULTS_FILE]"
```
此腳本會自動提取 Top 3/4 精選、比對實際賽果、計算所有 KPI。你只需引用腳本輸出嘅數據,**嚴禁自行手動數。**

> [!IMPORTANT]
> **位置命中率 (Place Hit Rate) 是最重要的 KPI**,優先於冠軍命中率。
> 以下為三級判定標準(由高到低):
> - 🏆 **黃金標準**:Top 3 精選全部跑入實際前三名(理想情況:Top 4 精選全入實際前四)
> - ✅ **良好結果**:Top 1 + Top 2 精選同時跑入實際前三名
> - ⚠️ **最低門檻**:Top 3 精選中,至少 2 匹跑入實際前三名(無極端情況下的通過標準)
> - 冠軍命中率為次要指標,位置一致性才是引擎可靠度的衡量標準

**必須統計以下指標(按優先順序排列):**

**A. 位置命中率(最重要 🔴)**
- **🏆 黃金標準率**:Top 3 精選全部入位前 3 的場次比率(🎯 目標 ≥30%)
- **✅ 良好結果率**:Top 1 + Top 2 精選同時入位前 3 的場次比率(🎯 目標 ≥40%)
- **⚠️ 最低門檻率**:Top 3 精選中有 ≥2 匹入位前 3 的場次比率(🎯 目標 ≥60%)
- **Top 3 單入位率**:Top 3 精選中至少 1 匹入位前 3 的場次比率(🎯 目標 ≥80%)


**B. 冠軍命中率(次要)**
- Top 1 精選命中率(預測冠軍 = 實際冠軍)
- Top 4 含冠軍率(Top 4 精選中包含實際冠軍)

**C. 整體校準**
- 整體評級校準(A 級以上馬匹的平均名次 vs B 級以下的平均名次)

**D. 排名順序分析 (Ranking Order Analysis) 🔴**
> [!IMPORTANT]
> 除左命中/入位率之外,引擎對 Top 4 嘅**排名順序**亦非常重要。
> 此指標專門捕捉「引擎搵到正確嘅馬但排錯次序」嘅情況。

- **Pick 3/4 超越 Pick 1/2 率**:Top 4 精選中,Pick 3 或 Pick 4 嘅實際名次**優於** Pick 1 或 Pick 2 嘅場次比率
- **逆序分析**:對每場出現 Pick 3/4 超越 Pick 1/2 嘅情況,記錄:
  - 邊匹馬被高估(Pick 1/2 但實際名次差)?邊匹被低估(Pick 3/4 但實際名次好)?
  - 高估/低估嘅具體原因(歷史率過度信任?場地偏差低估?騎練訊號低估?)
- **目標:** Pick 3/4 超越 Pick 1/2 率 ≤30%(即 70% 以上場次,Pick 1/2 確實跑得比 Pick 3/4 好)
- **SIP 觸發門檻:** 若連續 ≥3 場出現 Pick 3/4 超越 Pick 1/2 → 標記為「排名順序系統性偏差」,必須生成對應 SIP

### 4b. 逐場斷層分析
對每場失誤(預測 Top 4 與實際 Top 4 不符),檢查:
- **步速判斷是否正確?** — 預測的 PACE_TYPE 與實際步速是否吻合
- **場地/偏差判斷是否正確?** — 當日實際偏差與預測是否一致
- **EEM 判斷是否過度/不足?** — 高消耗馬是否真的崩潰?低消耗馬是否真的受惠?
- **騎師因素** — 是否忽略了騎師的臨場部署變化
- **練馬師訊號** — 是否錯過了配備變動、首出訊號、部署改變
- **負重/班次** — 頂磅/升班的判斷是否過嚴或過鬆
- **寬恕檔案** — 是否錯誤地寬恕了一匹實際已衰退的馬,或錯誤地懲罰了一匹實際受困的馬

### 4c. 系統性模式識別
跨全日所有場次,尋找反覆出現的判斷偏差:
- 某類型因素是否被系統性忽略?(例如:特定練馬師在特定場地的勝率)
- 某條規則是否觸發過頻/過少?
- 評級矩陣中的某個維度判斷是否持續偏離實際?

### 4d. 主動引擎健康掃描 (Proactive Engine Health Scan)
> [!IMPORTANT]
> **此步驟為強制性**,不得跳過。即使命中率極佳 (>80%),仍必須完成以下所有檢查項。
> 目的:防止 Reflector 因命中率尚可而跳過深度審查,導致潛在問題長期積累。

**你必須逐一檢查以下 6 個維度,並在覆盤報告中為每一項給出明確判定 (✅ 無需改動 / ⚠️ 觀察中 / 🔧 建議修改):**

#### 4d-1. 過時邏輯偵測 (Stale Logic Detection)
掃描引擎規則中是否有:
- 引用了已離港/退休/轉會的騎師或練馬師?
- 引用了已不再適用的賽事條件(如已改建的跑道、已停用的起步點)?
- 任何 SIP 的觸發條件是否因近期規律變化而需調整閾值?
- 騎師 Tier 分級是否仍然反映當前實力排名?

#### 4d-2. 斷裂邏輯偵測 (Disconnected Logic Detection)
掃描引擎規則中是否有:
- 某 Step 的輸出未被任何後續 Step 引用(產出了數據但無人消費)?
- 某 Step 引用了不存在的維度/標記名稱?
- 某條覆蓋規則(Override)的觸發條件在實際賽事中從未被滿足過(死規則)?
- SIP 之間是否存在互相矛盾或重複計算的情況?

#### 4d-3. 缺失規則偵測 (Missing Rule Detection)
根據今日賽事的實際情境,檢查是否存在:
- 今日出現了引擎沒有處理規則的情境(例如:新的跑道偏差類型、新的賽事條件組合)?
- 今日有馬匹因素在引擎中完全沒有對應規則(例如:全新的裝備類型、未涵蓋的血統線)?
- 是否存在「邊界條件」——馬匹剛好不符合觸發門檻但實際表現顯示應該被觸發?

#### 4d-4. 數據更新需求 (Data Freshness Check)
檢查引擎中的靜態數據是否需要更新:
- 騎師戰術特徵 (`07c_jockey_profiles.md` / `07_jockey_profiles.md`) 是否有新的表現趨勢未被記錄?
- 練馬師訊號是否有新模式尚未加入?
- 場地偏差/跑道模組的描述是否仍然準確?
- 血統參考數據是否需要補充新種馬/新血統線?

#### 4d-5. 規則校準驗證 (Rule Calibration Verification)
利用今日實際賽果驗證現有規則的校準度:
- 「致命死檔」觸發的馬匹,今日實際是否大敗?若否 → 是否需放寬?
- 「前速紅利」觸發的馬匹,今日是否真的受惠?若否 → 閾值是否需收緊?
- 「輕磅紅利」觸發的馬匹,表現是否符合預期?
- 溢價校正(Premium Jockey Correction)是否成功防止過度追捧?

#### 4d-6. 輸出品質抽查 (Output Quality Spot Check)
抽查 2-3 場分析報告的輸出品質:
- 分析是否出現模板化/重複數據(SIP-ST8 品質守門員檢查)?
- Top 4 排序的邏輯是否一致(同級別馬匹的排名是否有明確區分理由)?
- 段速/EEM/穩定性數據是否看起來合理(非默認值填充)?

> **輸出要求:** 即使所有 6 項均為 ✅,仍必須在覆盤報告中列出每項的簡短判定理由(各 1-2 句)。嚴禁簡單寫「無需改善」而不提供具體檢查結果。

### 4e. 逐場賽後敘事分析 (Narrative Post-Mortem)
> [!IMPORTANT]
> **此步驟為強制性**,針對每匹失敗嘅精選馬(預測 Top 4 但實際未入三甲)必須完成以下分析。
> 目的:區分「邏輯錯誤」(Bad Logic — 需要修改 SIP)同「運氣差」(Bad Luck — 可寬恕),避免因個別事件過度修改模型。

#### 4e-1. 沿途走位解讀 (Running Position Interpretation)
從賽果數據中,每匹馬嘅 `running_positions` 欄位記錄咗沿途走位(HKJC 格式如 `2-2-2-1` 或 `(1W1W1W3W)`)。你必須逐匹精選馬解讀:

**走位代碼解讀規則:**
- 數字 = 該段嘅排位(1 = 領先,14 = 最後)
- `W` = Wide(走外疊)。如 `3W` = 第 3 位但走外疊
- 4 段走位分別對應:**首段 → 中段 → 轉彎 → 直路**
- 例:`(2W3W4W6W)` = 全程走外疊,且由第 2 跌至第 6 = 典型高消耗崩潰

**從走位推斷嘅關鍵判斷:**

| 走位模式 | 含義 | 覆盤判斷 |
|:---|:---|:---|
| `1-1-1-1` 或末段維持 | 一放到底/前領到底 | 步速利前領,如分析已預測此步速則命中 |
| `X-X-X-↓` (末段跌位) | 直路後勁不繼 | 可能體力不足、負重過大、或步速過快崩潰 |
| `X-X-X-↑` (末段追上) | 後段爆發 | 若分析評為後追型卻未入 Top 4 → False Negative 候選 |
| 全程帶 `W` | 全程走外疊 | 高消耗 → 若分析已給 EEM ❌ 則正確;若給 ✅ 則判斷錯誤 |
| 末段 `W` 突然出現 | 直路被逼走外 | 可能被前方馬匹封死後被逼繞路 → 檢查 競賽事件報告 |
| 位置穩定 (如 `3-3-3-2`) | 全程好位 | 低消耗 → 若仍大敗 = 實力不足 (邏輯錯誤) |
| 位置穩定但末段跌 (如 `3-3-3-7`) | 好位但跑唔動 | 實力見底信號,若分析給 A 級 → 嚴重 False Positive |

**比對分析預測:** 將走位與分析報告中嘅 Speed Map / 預測守位進行比對:
- 預測為前領但實際 `8-8-7-6` → 起步失誤或被搶位 → 檢查競賽事件報告
- 預測為後追但實際 `2-2-3-5` → 騎師臨場改變部署 → 標記為不可預見

#### 4e-2. 可預測性評估 (Predictability Assessment)
對每個走位劣勢,判斷 Analyst 係咪可以預見:
- **可預見嘅陷阱**:大外檔 + 大場 + 非前領型 = 被困外疊機率極高 → Analyst 應該已計入
- **可預見嘅步速受害**:明顯嘅慢步速 + 後追馬 = 步速劣勢 → Analyst 應該已計入
- **不可預見嘅意外**:臨場突然起步失誤、被旁邊馬匹夾擠、騎師臨時改變部署

> **判斷標準**:如果 Analyst 嘅引擎規則已涵蓋此類情境(例如 Step 7 死檔規則、Step 3 步速判斷)但未正確觸發 → 屬於「可避免陷阱」。如果引擎完全冇對應規則 → 屬於「缺失規則」(記入 SIP)。如果屬臨場意外 → 屬於「不可預見」。

#### 4e-2.5. 分段時間法醫 (Sectional Time Forensics)
從賽果數據中嘅 `分段時間` 欄位提取各段時間(通常為每 200m 或 400m 一段)。你必須將分段時間與分析預測嘅步速及段速進行交叉比對:

**分段時間分析步驟:**
1. **識別步速類型:** 首兩段時間快(如 ≤13.0s/200m)= Genuine-to-Fast;首兩段慢(如 ≥14.0s/200m)= Moderate-to-Crawl
2. **識別段速質量:** 末段時間 vs 首段時間 → 衰退率計算。衰退率 >15% = 體力崩潰
3. **比對分析預測:**
   - 分析預測 `步速: Crawl` 但實際首段極快 → 步速判斷錯誤 → 所有基於慢步速嘅評級加成失效
   - 分析預測 `步速: Genuine` 但實際極慢 → 前領偷襲成功 → 所有基於快步速嘅後追馬加成失效
4. **段速驗證:** 若分析報告中某馬被標為「末段前3」但實際分段時間顯示其末段衰退嚴重 → False Positive 信號
5. **全場比較:** 冠軍馬嘅末段時間 vs 失敗精選馬嘅末段時間 → 差距反映真實能力差距

**分段時間紅旗:**
- 全場首段極快(前 400m ≤ 23.5s)但分析預測慢步速 → 步速預測系統性失準
- 冠軍馬末段 22.5s(最後 400m)但被評為 C 級 → 段速引擎嚴重低估
- 前領馬首段領先 3+ 身位但末段崩潰 → 自殺式步速未被識別

#### 4e-3. 競賽事件報告深度審查 (Race Incident Report Deep Review)
從賽果數據中嘅 `📋 競賽事件報告` 段落提取每匹馬嘅事件報告。此報告由馬會競賽事務部發出,為官方紀錄。

**關鍵詞分類與裁定影響:**

| 關鍵詞/描述 | 分類 | 對裁定影響 |
|:---|:---|:---|
| 「流鼻血」/「Bled」 | 🩸 醫療 | **自動 🟢 可寬恕** — 不可抗力,不需修改 SIP |
| 「跛行」/「不良於行」 | 🩸 醫療 | **自動 🟢 可寬恕** — 賽前無法預測 |
| 「心律不正」/「呼吸異常」 | 🩸 醫療 | **自動 🟢 可寬恕** |
| 「受碰撞」/「被夾擠」/「碰撞」 | 🏇 干擾 | 視程度:**輕微 = 🟡 參考因素**;**嚴重(導致失去平衡/急拉避讓)= 🟢 可寬恕** |
| 「走勢受阻」/「未能走出」 | 🏇 受困 | **若分析已預測受困風險(如內檔被困)= 🟡 可避免**;若不可預見 = 🟢 可寬恕 |
| 「出閘緩慢」/「起步笨拙」 | ⚡ 起步 | **若馬匹有慢閘歷史且分析未計入 = 🟡 可避免陷阱**;若首次慢閘 = 🟢 不可預見 |
| 「不願加速」/「毫無表現」 | 💀 實力 | **🔴 邏輯錯誤** — 馬匹本身實力不足,分析高估 |
| 「搶口」/「不受控」 | 🐎 行為 | 若分析未標記行為風險 = 🟡;若已標記 = 正確預判 |
| 「蹄鐵鬆脫」/「口銜不順」 | 🔧 裝備 | **🟢 不可預見** — 臨場裝備故障 |

**競賽事件報告 × 沿途走位 × 分段時間 三角交叉驗證:**
> [!IMPORTANT]
> 裁定必須綜合三個數據源,不可僅憑單一來源下結論。

- 若競賽事件報告顯示「受碰撞」+ 沿途走位顯示走位突變(如 `3-3-8-10`)+ 分段時間末段極慢 → **🟢 可寬恕**(碰撞導致失位再無法追回)
- 若競賽事件報告顯示「正常出閘」+ 沿途走位顯示全程好位(`2-2-2-5`)+ 分段時間末段嚴重衰退 → **🔴 邏輯錯誤**(好位但跑唔動 = 實力不足)
- 若競賽事件報告無特別記錄 + 沿途走位顯示全程外疊(`W`)+ 分段時間末段追近但仍大敗 → **🟡 可避免陷阱**(外疊消耗可預見,分析應已計入 EEM)
- 若競賽事件報告顯示「出閘緩慢」+ 沿途走位顯示 `12-12-10-8`(末段追近)+ 分段時間末段為全場最快 → **🟢 可寬恕**(慢閘導致落後但末段顯示能力強勁,寬恕且記入下仗反彈候選)

> ⚠️ **失敗處理**:若搜索不到競賽事件報告(例如報告尚未發布),標記為「競賽事件報告待查」並繼續。此時裁定僅基於 沿途走位 + 分段時間,但信心度標記為「降低」。嚴禁因此跳過整個 4e。

#### 4e-4. 裁定分類 (Verdict Classification)
對每匹失敗嘅精選馬,根據 4e-1 至 4e-3 嘅**綜合證據**,給出以下三類裁定之一:

| 裁定 | 條件 | 對 SIP 嘅影響 |
|:---|:---|:---|
| 🟢 **可寬恕 (Forgivable / Bad Luck)** | 有競賽事件報告紀錄嘅醫療問題或嚴重干擾;極冷門翻盤(賠率 >50 倍);不可預見嘅臨場意外(慢閘首次出現、裝備故障);沿途走位證實受困且非分析可預見 | 唔需要修改 SIP,記入「⚠️ 單場特殊因素」。**但必須記錄該馬為下仗潛在反彈候選** |
| 🔴 **邏輯錯誤 (Logic Failure / Bad Logic)** | 走位正常(無外疊/無受困)+ 競賽事件報告無異常 + 分段時間末段衰退 = 純粹跑唔動;引擎規則已涵蓋但判斷方向錯誤;馬匹實力系統性被高估 | **必須**生成對應 SIP,指明需要修改嘅具體規則 |
| 🟡 **可避免陷阱 (Avoidable Trap)** | 走位劣勢係可預見但分析未計入(如外疊消耗、步速不利);分段時間揭示步速預測錯誤;競賽事件報告中嘅行為問題(搶口/外閃)在歷史紀錄中已有但未觸發風險標記 | **必須**生成對應 SIP,聚焦於規則觸發條件嘅校準 |

> **嚴格要求**:每個裁定必須附帶 ≥2 個證據點支持,且必須來自至少 2 個不同數據源(沿途走位 + 競賽事件報告 / 分段時間 / 引擎規則比對)。嚴禁無證據裁定或僅憑單一來源裁定。

### 4d. Python 自動化輔助（強制前置）

> [!IMPORTANT]
> **以下 Python 腳本必須在 LLM 開始 Step 4d-5 之前執行。**
> 目的：將機械性數據抽取工作交畀 Python，LLM 只需聚焦高層次法醫判斷。

**4d-pre-1. 引擎健康掃描（自動化部分）:**
```bash
python .agents/scripts/engine_health_scanner.py --domain hkjc --resources-dir ".agents/skills/hkjc_racing/hkjc_horse_analyst/resources"
```
此腳本自動檢查 4d-1（過時邏輯）、4d-2（斷裂邏輯）、4d-4（數據新鮮度）。LLM 只需處理 4d-3、4d-5、4d-6。

**4d-pre-1b. SIP 衝突掃描:**
```bash
python .agents/scripts/sip_conflict_scanner.py --domain hkjc --resources-dir ".agents/skills/hkjc_racing/hkjc_horse_analyst/resources"
```
自動構建 SIP 規則關係圖，偵測方向衝突、重複計算、交叉引用、過時引用。LLM 只需判斷衝突係有意制衡定真衝突。

**4d-pre-1c. 規則觸發率統計:**
```bash
python .agents/scripts/rule_trigger_tracker.py --domain hkjc --resources-dir ".agents/skills/hkjc_racing/hkjc_horse_analyst/resources" --analysis-dir "[TARGET_DIR]"
```
統計每條 SIP 嘅實際觸發次數，識別死規則（從未觸發）同過度觸發（>80%），LLM 只需判斷是否需修改門檻。

**4d-pre-1d. 引擎覆蓋率矩陣:**
```bash
python .agents/scripts/engine_coverage_matrix.py --domain hkjc --resources-dir ".agents/skills/hkjc_racing/hkjc_horse_analyst/resources" --analysis-dir "[TARGET_DIR]"
```
計算引擎規則覆蓋率（類似 code coverage），識別未被使用嘅死代碼規則。

**4d-pre-2. 敘事覆盤數據抽取:**
```bash
python .agents/scripts/narrative_postmortem_extractor.py "[RESULTS_FILE]" "[TARGET_DIR]" --all --domain hkjc
```
自動抽取失敗精選馬嘅走位、分段時間、競賽事件報告關鍵字分類。LLM 只需做 4e-4 裁定。

## Step 5: 輸出覆盤報告

### Step 5-pre: 生成報告骨架（Python 強制）
```bash
python .agents/scripts/reflector_report_skeleton.py "[TARGET_DIR]" "[RESULTS_FILE]" --domain hkjc --output "[TARGET_DIR]/[Date]_[Racecourse]_覆盤報告.md"
```
> 此腳本自動生成完整報告框架，預填所有命中率表格、逐場比對、FP/FN 名單。
> LLM 只需填入 `{{LLM_FILL}}` 標記嘅定性分析欄位。
> **嚴禁 LLM 手動砌報告框架** — 必須使用腳本生成嘅骨架。

### Step 5-post: 報告驗證（Python 強制）
報告撰寫完成後，執行裁定驗證器：
```bash
python .agents/scripts/reflector_verdict_validator.py "[TARGET_DIR]/[Date]_[Racecourse]_覆盤報告.md" --domain hkjc --resources-dir ".agents/skills/hkjc_racing/hkjc_horse_analyst/resources"
```
> 自動驗證每個裁定有 ≥2 證據點、SIP 引用存在、所有必要 section 齊全。
> 未通過驗證嘅報告**嚴禁**提交畀用戶。

按照以下格式生成報告,保存為 `[Date]_[Racecourse]_覆盤報告.md` 於 `TARGET_DIR` 內:

```markdown
# 🔍 HKJC 賽後覆盤報告
**日期:** [日期] | **馬場:** [馬場] | **場次:** [總場次]

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
| Top 4 含冠軍率 | X/Y (Z%) |
| A級以上平均名次 | X.X |
| B級以下平均名次 | X.X |

## 📋 逐場覆盤摘要

### 第 X 場 — [✅ 命中 / ❌ 失誤 / ⚠️ 部分命中]
**實際前三名:** [X]
**預測 Top 4:** [X]
**關鍵偏差:** [一句話總結失誤原因]
**偏差類型:** [步速誤判 / EEM偏差 / 練馬師訊號遺漏 / 騎師變陣 / 場地偏差 / 寬恕錯誤 / 負重誤判]

## 🔴 False Positives (看高但大敗)
| 場次 | 馬匹 | 預測評級 | 實際名次 | 失誤根因 |
|:---|:---|:---|:---|:---|

## 🟢 False Negatives (看低但勝出/上名)
| 場次 | 馬匹 | 預測評級 | 實際名次 | 遺漏因素 |
|:---|:---|:---|:---|:---|

## 🧠 系統性改善建議 (Systemic Improvement Proposals)

### SIP-1: [建議標題]
- **問題:** [描述反覆出現的判斷偏差]
- **證據:** [列舉支持此結論的多場實例]
- **目標檔案:** [指明需要修改嘅具體 resource 檔案,例如 `04_engine_corrections.md` Step 7]

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

| 場次 | 馬匹 | 預測評級 | 實際名次 | 沿途走位 | 分段時間摘要 | 競賽事件報告 | 裁定 | 證據 |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| [X] | [馬名] | [A/B+/...] | [名次] | [走位代碼 + 關鍵解讀] | [末段時間 + 衰退率] | [醫療/干擾/無] | [🟢/🔴/🟡] | [≥2 個來自不同數據源嘅證據點] |

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
> - 場地偏差觀察(Entity: `{VENUE}_{DATE}_bias`,Observations: 內欄/外欄/前速偏差等)
> - False Positive/Negative 模式(Entity: `FP_pattern_{SIP_ID}` 或 `FN_pattern_{SIP_ID}`)
> - 引擎健康掃描結果(Entity: `engine_health_{DATE}`,記錄 6 個維度判定)
> - 這樣下次覆盤同一場地時,Reflector 可以先查詢 `read_graph` 發現過往場地偏差歷史。

## Step 5.5: Instinct Evolution（P35 新增）

> **設計理念:** 受 ECC `continuous-learning-v2` 嘅 Instinct 模型啟發。
> 將一次性嘅 SIP 修改升級為帶 confidence score 嘅長期學習機制。

覆盤報告生成後，執行 instinct 評估：
```bash
python3 .agents/scripts/instinct_evaluator.py "{TARGET_DIR}" \
  --registry ".agents/skills/shared_instincts/instinct_registry.md" \
  --domain hkjc \
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
每次套用新 SIP 後,必須更新 `hkjc_horse_analyst/resources/sip_changelog.md`:
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

為確保新邏輯真正改善預測準確度,需要進行 LLM 歷史回測驗證:
→ 揀選 2-3 場與 SIP 相關嘅歷史賽事（優先揀 FP/FN 觸發場次）
→ 以完整 14-step 引擎重新分析,比對新舊 Top 4
→ MC Sanity Check 作為輔助（非主驗證）

是否開始回測驗證?(Y/N)
```

**Step 6c-2 — 用戶確認後,立即執行 Step 7 SIP Validation (強制執行):**

若用戶確認 (Y),你**必須立即**執行 SKILL.md Step 7 (SIP Validation — 3-Tier):

1. **Tier 1 LLM 歷史回測 (Primary):**
   - 揀選 2-3 場與 SIP 相關嘅歷史賽事
   - 用更新後嘅 SIP 規則以完整 14-step 引擎重新分析
   - 比對新舊 Top 4 排名是否更接近實際賽果

2. **Tier 2 MC Sanity Check (Secondary):**
   - `python mc_simulator.py --logic "[LOGIC_JSON]" --platform hkjc`
   - 只檢查不合理偏移 (非驗證閘口)

3. **Tier 3 深度覆審 (條件觸發):**
   - 只有 Tier 1 同 Tier 2 結論矛盾時觸發

> **執行要求:** 你必須喺同一個 session 中開始執行 Tier 1 回測,唔可以只輸出提示然後停低。

**Step 6c-3 — 用戶拒絕:**

若用戶拒絕 (N):
- 記錄「用戶選擇跳過 SIP 回測驗證」到 `_session_issues.md`
- 輸出:「已記錄跳過驗證。SIP 修改已套用但未經回測驗證。日後可隨時執行覆盤進行補測。」
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
  - `run_command`:用於執行 `extract_race_results.py`。
  - `view_file`:讀取過往賽前預測報告與剛抓取的賽果檔。
  - `search_web`:若需要補充搜索實際賽日情報(如當日實際偏差報告)。
  - `run_command`:用於執行 Python 腳本及 P19v6 安全寫入（`run_command` + heredoc → `/tmp` → `cp`）。嚴禁使用 `write_to_file`。
- **Assets**:
  - `batch_extract_results.py`:專門用於併發解析 HKJC 賽果的腳本。
    - **Windows:** `g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\hkjc_racing\hkjc_race_extractor\scripts\batch_extract_results.py`

- **MCP Tools (P32 新增)**:
  - `read_graph` / `search_nodes` — Knowledge Graph 查詢(檢查過往場地偏差觀察、騎練組合紀錄)
  - `read_query` / `list_tables` — SQLite 歷史數據查詢(查等評級歷史、命中率追蹤)
  - `create_entities` / `create_relations` — 將覆盤發現寫入 Knowledge Graph(SIP 觸發模式、引擎健康掃描結果)
    - **macOS:** `/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/skills/hkjc_racing/hkjc_race_extractor/scripts/batch_extract_results.py`

# Test Case
**User Input:** `「幫我覆盤今日賽事:https://racing.hkjc.com/zh-hk/local/information/localresults?racedate=2026/03/04&Racecourse=HV&RaceNo=1」`
**Expected Agent Action:**
1. 記錄 `DATE` = 2026-03-04,`VENUE` = HappyValley,`TARGET_DIR` = 對應資料夾。
2. 執行 `extract_race_results.py`,抓取並生成含全日賽果的文檔至 `TARGET_DIR`。
3. 搜尋並讀取 `TARGET_DIR` 中的所有 `*Analysis.md` 檔案。
4. 逐場比對 Top 4 預測與實際賽果,執行 False Positive / False Negative 分析,識別系統性偏差模式。
5. 生成覆盤報告 `2026-03-04_HappyValley_覆盤報告.md`。
6. 向用戶提交報告摘要,等待審批。
