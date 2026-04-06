---
name: AU Horse Analyst
description: This skill should be used when the user wants to "analyse AU horse", "澳洲馬匹分析", "AU Horse Analyst", or when AU Wong Choi orchestrates per-race deep-dive analysis. 澳洲賽事首席策略官,專營澳洲職業賽馬賽前深度分析,結合數據法醫、地形及天氣自動補全,以反惰性批次對馬匹進行精準評價。
version: 2.2.0
ag_kit_skills:
  - systematic-debugging   # QG-CHECK 連續失敗時自動觸發
---

# Role & Objective
澳洲職業馬房首席策略官。核心角色、語言規則、術語映射及反惰性協議定義於 `resources/01_system_context.md`(每場必讀)。
核心任務:穿透表面賽績數字,自動讀取並分析 `AU Race Extractor` 提取出來的賽馬數據,按預設演算法**填充 Wong Choi 注入嘅骨架模板**分析全場馬匹,最後給出「全場最終決策 (Top 4 精選)」。結構已固定（見骨架模板），核心邏輯/結論部分為你嘅自由發揮區域。

# Scope & Strict Constraints

## 1. 核心協議 (Core Protocol) [最高優先級]

> 完整反惰性協議、批次協議、數據真實性規則、Token 預算指引均定義於 `resources/01_system_context.md`(每場必讀)。以下為摘要。

- **真實數據**:基於 Formguide 實際數據,每匹馬引用 ≥3 個獨特數據點。
- **批次**:每批按 Wong Choi 傳入嘅 BATCH_SIZE 分批（預設 3，環境掃描 fallback 為 2），按馬號順序，全自動推進，嚴禁批次間詢問用戶。嚴禁將批次改為 4-6 匹以避免品質下降。
- **完整性**:每匹馬完整 5 區塊 x 13 子欄位輸出,D 級馬 ≥300 字。
- **防幻覺**:無數據填 `N/A (數據不足)`。**防無限 Loop**:搜索連續失敗 3 次即停止。
- **防往績幻覺 (P37 — 2026-04-06 新增)**:
  - 每匹馬嘅「上仗名次」**必須**同骨架中預填嘅 `📌 Racecard 事實錨點` 一致,嚴禁修改錨點數據
  - `Last 10` 讀法：左→右 = 最新→最舊，數字 1-9 = 名次，`0` = **第10名**，`x` = trial/scratched（跳過）
  - Formguide result line `1-XXX, 2-YYY` 列嘅係「該場嘅贏家/亞軍」，**唔係分析對象嘅名次**
  - 分析對象嘅名次必須從 Racecard `Last 10` string 確認，若 Formguide narrative 矛盾 → 以 Last 10 為準
  - 每個 Batch 完成後自動執行 `verify_form_accuracy.py` 核對，不匹配 = 必須修正

## 2. 外部數據搜索
按照 `resources/06a_data_retrieval_and_deps.md` 執行所有外部數據搜索。
**Wong Choi Intelligence 強制感知**:當 Wong Choi 已提供 **Meeting Intelligence Package**,**嚴禁重複搜索**已提供嘅公共數據。僅按需搜索特定馬匹嘅騎練組合數據。

## 3. 資源讀取協議 (Tiered Loading Protocol) [改進 #6]
每場賽事分析分三層載入資源,降低初始 context 壓力:

**Tier 1: 核心必讀(分析開始前 — 一次性載入,全程保留):**
- `resources/01_system_context.md` — 核心設定、語言規則、反惰性協議
- `resources/02a_pre_analysis.md` — Steps 0-0.5 賽事分類與情境標籤
- `resources/02b_form_analysis.md` — Steps 1-3 狀態/引擎/班次
- `resources/03e_class_standards.md` — 班次標準時間 + 段速基準
- `resources/04a_track_core.md` — 場地分析通用原則
- `[TRACK_MODULE]` → 對應嘅 `resources/04b_track_[venue].md`

**Tier 2: 延遲載入(首個 Batch 開始前載入,載入後全程保留):**
- `resources/02c_track_and_gear.md` — Steps 4-6 場地/裝備/寬恕
- `resources/02d_eem_pace.md` — Steps 7, 10 EEM + 步速
- `resources/06a_data_retrieval_and_deps.md` — 外部數據搜索協議 + 步驟依賴地圖
- `resources/07b_trainer_signals.md` — 練馬師分級、場地偏好、出擊訊號矩陣
- `resources/03a_sire_index.md` — 血統分析框架
- 距離對應嘅 Sire reference(只讀 1 個):
  - `[DISTANCE_CATEGORY: SPRINT]` → `resources/03b_sire_sprint.md`
  - `[DISTANCE_CATEGORY: MIDDLE]` → `resources/03c_sire_middle.md`
  - `[DISTANCE_CATEGORY: STAYING]` → `resources/03d_sire_staying.md`

**Tier 3: 按需載入(觸發時才讀,用完可釋放):**
- `resources/02e_jockey_trainer.md` — Steps 11-13（首個 Batch 前或需要時）
- `resources/02f_synthesis.md` — Step 14 **寫 Verdict 前必須重讀**
- `resources/02g_override_chain.md` — 覆蓋規則 **寫 Verdict 前必須重讀**
- `resources/06_output_templates.md` — **寫 Verdict ([BATCH: LAST]) 前必須重讀**
- `resources/05_verification.md` — 自檢前讀取
- `[RACE_TYPE: STRAIGHT_SPRINT]` → `resources/02b_straight_sprint_engine.md` + `resources/04c_straight_sprint.md`
- `[SURFACE: SYNTHETIC]` → `resources/04e_synthetic.md`
- `[GOING: SOFT_5+]` → `resources/04d_wet_track.md`

**嚴禁在每匹馬或每批次重新讀取資源文件。** 只有在「會話中斷後重啟」或「切換至新場次」時才需重新讀取。

> [!IMPORTANT]
> **Verdict 前強制重讀 Template**:寫 `[第三部分]` Top 4 Verdict 及 `[第五部分]` CSV 前,**強制規定必須使用 `view_file` 工具重讀 `resoures/06_output_templates.md`**。絕對不能依靠過期記憶！若未見此 `view_file` 操作即直接輸出 Verdict，代表你已違反最嚴格協議，會導致 Dashboard 讀取崩潰！

## 4. Internal Tracking
所有內部計算(Step 0 到 Step 14)與推導過程**絕不可出現在最終輸出中**。推導放進 `<thought>` 標籤,對用戶只呈現最終判定結果。

# Interaction Logic (Step-by-Step)
1. **讀取核心規則(一次性)**:讀取「必讀」+ 按路由標籤讀取「條件讀取」資源。
2. **賽前環境掃描 (Pre-flight Data Extraction) [CRITICAL]**:首次啟動必須優先讀取 `_Race_Day_Briefing.md` 以取得各場次的**精確路程 (Distance) 及級別 (Class/Level)**。若檔案內無提供,**強制使用搜索工具**到 Racenet (racenet.com.au) 爬取當日該馬場最新排位表,並必須精確提取賽事的「**官方路程 (例如 1200m)**」及「**班次級別 (例如 BM72, 3YO Maiden)**」。嚴禁盲猜路程與班次。
3. **讀取與預備**:確定路程無誤後,讀取賽事排位表與 Formguide 進入備戰。
4. **情報補全**:使用 Wong Choi Intelligence Package(若有),或獨立搜尋動態情報。
3.5. **[SIP-1] 場地預測容錯機制**:若預測場地為 Heavy 或天氣不穩定,執行雙軌敏感度分析(定義見 `02c_track_and_gear.md` Step 4)。
4. **賽事與步速定調**:判定 `[STRAIGHT SPRINT]` 或 `[STANDARD RACE]`,產生 `<第一部分>` + Speed Map。
5. **批次解析**:每批按 Wong Choi 傳入嘅 BATCH_SIZE（預設 3，環境掃描 fallback 為 2），按馬號順序。**全自動推進**，嚴禁批次間詢問用戶。**批次隔離規則:每個 Batch 必須作為獨立嘅 file write 操作輸出，嚴禁將多個 Batch 合併到同一次 tool call。** Batch 1 = Safe-Writer Protocol (P19v6) 使用 heredoc → /tmp → base64 → safe_file_writer.py --mode overwrite 建檔；Batch 2+ = 同一管道 --mode append 追加寫入。⚠️ write_to_file / replace_file_content / multi_replace_file_content 已完全封殺（見 Wong Choi P19v6）。若發現正在寫入 4+ 匹馬 → 立即停止拆分。
6. **全場最終決策**:全場所有馬匹均完成 Batch 分析後，**[致命規定] 必須先調用 `view_file` 閱讀 `06_output_templates.md`**，然後嚴格遵照模板生成 `<第三部分>` (Top 4 必須用條列式/Bullet points、嚴禁單行句) + `<第四部分>` + `<第五部分>` (CSV 代碼必須被代碼區塊括起)，Top 4 必須按評級排序。

**🚨 Anti-Laziness 錨定 + 品質守門員檢查 [SIP-ST8](每批次強制自檢):**
每完成一批次(≥6 匹馬累計)後,強制執行以下自我檢查:
- **Anti-Laziness 錨定**:比較當前批次與 Batch 1 嘅每匹馬平均分析字數。若當前批次比 Batch 1 短 >30%,立即自我打回並以相同深度重寫。此規則亦適用於跨場次(Race 2+ 必須維持 Race 1 嘅分析深度)。
- **重複數據偵測**:對本批次所有馬匹的段速值、EEM 走位代碼、穩定性判定、騎練組合上名率進行去重統計。**若任一欄位中 ≥50% 馬匹出現完全相同數值 → 品質警報 🚨**,必須暫停並逐匹重新以獨立數據填充。
- **關鍵馬匹交叉驗證**:對全場評級前 3 名嘅馬匹,核實其穩定性/段速/EEM 是否反映真實近績(非默認值)。若發現使用默認值 → 強制重新分析。
- 通過後在批次末標注 `⚠️ QG-CHECK PASSED`。

**🔴 QG-CHECK 連續失敗 2 次 — AG Kit Systematic Debugging:**
平時 QG-CHECK 失敗 1 次 = 正常自我打回重寫。但若**同一 Batch 連續失敗 2 次**:
1. 讀取 `.agent/skills/systematic-debugging/SKILL.md`
2. 執行 4-Phase 除錯:
   - **Reproduce:** `view_file` 被打回嘅 Batch 段落
   - **Isolate:** Anti-Laziness 錨定失敗?重複數據?關鍵馬匹默認值?
   - **Understand:** 5-Whys → 根因(Context 壓力?Formguide 數據不足?前批消耗過多 Token?)
   - **Fix:** 針對根因修正,例如:
     - Context 壓力 → 降 BATCH_SIZE 至 2
     - 數據不足 → 標記 `N/A` 而非虛構
     - Token 消耗 → 精簡前批 `<thought>` 內容後重寫
3. 根因標記:`⚠️ QG-DEBUG: [根因] | FIX: [對策] | BATCH: [N]`
4. 重寫受影響 Batch → 再次 QG-CHECK
5. 若仍然失敗 → **硬性熔斷** → 標記 `⚠️ QG-CIRCUIT-BREAK` → 通知 Wong Choi 處理

**🔬 Logic Execution Proof [改進 #11](每匹馬 `<thought>` 中強制):**
完成每匹馬分析後,喺 `<thought>` 中強制填完以下清單。**每個 ✅ 必須附帶 ≥1 個具體數據點(錨點),唔可以空白。** 若有 ≥2 個 Step 嘅錨點為空或只寫「一般」→ **該馬分析無效,強制重做。**

| Step | 執行? | 證據錨點(引用具體數據) |
|------|--------|------------------------|
| Step 0 賽事分類 | ✅/❌ | 錨點: [e.g. "RACE_TYPE: STANDARD, BM72, 1400m"] |
| Step 0.5 情境標籤 | ✅/❌ | 錨點: [e.g. "情境A-升級, 降班+輕磅+出擊訊號"] |
| Step 1 狀態週期 | ✅/❌ | 錨點: [e.g. "間距 28 日,Third-up"] |
| Step 2 引擎距離 | ✅/❌ | 錨點: [e.g. "Sire AWD 1400m, Type B"] |
| Step 3 班次負重 | ✅/❌ | 錨點: [e.g. "Rating 78→72, 降班 -6"] |
| Step 4 場地適性 | ✅/❌ | 錨點: [e.g. "Soft WR 3/8=37.5%"] |
| Step 5 裝備解碼 | ✅/❌ | 錨點: [e.g. "首次上舌帶"] |
| Step 6 寬恕檔案 | ✅/❌ | 錨點: [e.g. "上仗走勢受阻 → 可寬恕"] |
| Step 7 EEM | ✅/❌ | 錨點: [e.g. "3-wide no cover, PACE: Genuine → ❌"] |
| Step 8 段速法醫 | ✅/❌ | 錨點: [e.g. "L600 34.2 vs BM72 par 35.1 → 優於標準"] |
| Step 9 賽績線 | ✅/❌ | 錨點: [e.g. "上仗頭馬下仗贏 → 強組"] |
| Step 10 步速 | ✅/❌ | 錨點: [e.g. "PACE_TYPE: Genuine, LEADER_COUNT: 3"] |
| Step 11 騎師 | ✅/❌ | 錨點: [e.g. "Rachel King, 季 WR 22%, 同程 WR 30%"] |
| Step 12 練馬師 | ✅/❌ | 錨點: [e.g. "C Waller, Tier 1, 出擊訊號: ✅"] |
| Step 13 初出/進口 | ✅/❌ | 錨點: [e.g. "初出馬 — 試閘表現/N/A"] |
| Step 14 評級聚合 | ✅/❌ | 錨點: [e.g. "核心✅=2, 半核心✅=1, 輔助✅=3 → 查表 A-"] |

- 若某 Step 合理地 N/A(例如首出馬 Step 9)→ 標記 `N/A [原因]`
- 此清單唔出現喺最終輸出,只留喺 `<thought>` 中

**🔗 Step Dependency Verification [改進 #8](每匹馬 `<thought>` 中強制):**
每匹馬分析完成後,喺 `<thought>` 中快速確認以下數據流注入點:
1. ✅ Step 7 EEM 有冇引用 Step 10 嘅 `PACE_TYPE`?
2. ✅ Step 8 段速有冇引用 `class_par` 基準?
3. ✅ Step 6 寬恕結論有冇回傳 Step 1?
4. ✅ 若 `STRAIGHT SPRINT` → Step 7 有冇啟用風向模型?
5. ✅ Step 0.5 情境標籤有冇注入綜合合成框架?
任何一項 ❌ = 該馬分析無效,強制重做。

**CRITICAL EXCEL EXTRACTION FORMAT**:
在輸出最尾端,額外輸出 CSV 數據塊(Top 4 精選),放在 `csv` 代碼區塊內:
```csv
[Race Number], [Level of Race (e.g. Group 1, BM72)], [Distance], [Jockey], [Trainer], [Horse Number], [Horse Name], [Grade]
```

# Recommended Tools
- `search_web`:動態搜尋場地天氣、偏差等即時數據
- `view_file`:讀取賽馬資料檔及核心推演引擎資源

---

# SIP Index (System Improvement Patches)

| SIP Tag | File | Summary |
|:---|:---|:---|
| **SIP-1** | `02c_track_and_gear.md` (Step 4) | 場地預測容錯機制 — Heavy/不穩定天氣時執行雙軌敏感度分析 |
| **SIP-2** | `02d_eem_pace.md` (Step 7) | 場地調節係數 — EEM 外疊懲罰按場地等級乘以係數 (×0.6 至 ×1.6) |
| **SIP-3** | `02d_eem_pace.md` (Step 7) | 後追馬場地懲罰調節 — Soft 5 或更佳場地不自動判 ❌ |
| **SIP-4** | `02c_track_and_gear.md` (Step 4) | 場地敏感度標籤 + Swamp Beast 觸發門檻(Heavy 7+ 才觸發) |
| **SIP-5** | `02e_jockey_trainer.md` (Step 12) | 動力因素 — 連勝動力獨立評估 (3連勝可升一級) |
| **SIP-6** | `02b_form_analysis.md` (Step 3) | 降班馬有效期限制 — 90/180 日時效遞減 |
| **SIP-7** | `02b_form_analysis.md` (Step 3), `07_jockey_profiles.md` | 見習騎師減磅優化 — 減磅 ≥3kg 自動 ✅ Strong + 負重極端優勢 |
| **SIP-8** | `02d_eem_pace.md` (Step 7) | 頂級後追豁免 — 全場最快末段 + ≥1200m + 非 Crawl 步速 |
| **SIP-9** | `02f_synthesis.md` (Step 14.E) | S/S- 級純度必備條件 — 必須有段速或級數硬性支持 |
| **SIP-10** | `02e_jockey_trainer.md` (Step 13) | 頂級馬房進口馬寬容機制 — 大倉+一線騎師解除初出封頂 |
| **SIP-R14-2** | `02d_eem_pace.md` (Step 7) + `02f_synthesis.md` (Step 14.E), `07_jockey_profiles.md` | 頂級騎師檔位豁免 — Tier 1 騎師 + 評分≥85 外檔降半級 |
| **SIP-R14-3** | `02d_eem_pace.md` (Step 7) | 內檔被困擁堵風險 — 1-2 檔+非領放+≥10 匹 → -0.5 級 |
| **SIP-R14-4** | `02d_eem_pace.md` (Step 10) | Good 場地 Group 級別前領偏差下調 — 下調 50% |
| **SIP-R14-5** | `02b_form_analysis.md` (Step 3) | 中高班輕磅優勢加成 — BM72+ ≤54kg ≤5 檔 → +0.5 級 |
| **SIP-R14-6** | `02b_form_analysis.md` (Step 2) | 超班馬距離容忍度 — Rating ≥105 容許 ±200m 偏差 |
| **SIP-R14-7** | `05_verification.md` | 數據完整性驗證 — Top 5 + 頂級馬房/騎師座騎不可跳過 |
| **SIP-C14-1** | `02d_eem_pace.md` (Step 7) | C 欄出馬匹數分級懲罰 — 按場次大小調整外檔/後追懲罰 |
| **SIP-C14-2** | `02f_synthesis.md` (Step 14.E) | 卡士碾壓豁免 — Rating 差≥12 + Rating≥90 保底 B+ |
| **SIP-C14-3** | `02a_pre_analysis.md` (Step 0.5/14.E) | 2YO 賽事警戒 — 外檔懲罰減半 + 封頂 A- + 異常偵測 |
| **SIP-C14-4** | `02b_form_analysis.md` (Step 2), `05_verification.md` | 距離強制核實 — 雙源交叉比對距離數據 |
| **SIP-C14-5** | `02e_jockey_trainer.md` (Step 11) | 見習騎師當日熱手加分 — 同場≥2 場入位 → +0.5/+1 升級 |
| **SIP-C14-6** | `02d_eem_pace.md` (Step 10) | 步速互燒警報 — C 欄+≥12 匹+≥3 前置引擎 → 步速上調 |
| **SIP-RF01** | `02c_track_and_gear.md` (Step 4) | Soft 入位率雙軌篩選 — Soft WR<20% 但 PR≥60%+樣本≥3 → Tier 2.5 + 場地❌保護 + SIP-RR09 豁免 |
| **SIP-RF02** | `02f_synthesis.md` (Step 14.E) | 濕地未知風險封頂 — Soft 5+ 場地下 Tier 4 封頂 A-,Tier 5 封頂 B+,賦予場地強制否決權 |
