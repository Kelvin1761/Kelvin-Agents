# SIP Changelog (AU)
> 合規 Agent 每次掃描時讀取此文件,特別檢查最近 2 次更新嘅 SIP 是否被正確套用。
> **只保留最近 5 條。** 完整歷史記錄見 `00_sip_index.md`。

## Latest Updates
### 2026-04-23 — AU SIP Lifecycle Audit + Facts-backed SIP Slimming
- **Changed:**
  - **ACTIVE SIP 大幅瘦身:** `ACTIVE` 重新定義為「需要即場場景路由、賠率後置審視、投注輸出或 Reflector protocol」的 live rule；多數舊覆盤 SIP 改列 `✅ BAKED`。
  - **Facts-backed baking:** Last 10 解碼、試閘/正式分離、場地/距離/跑法、PI 趨勢、賽績線、負重、track profile 已由 `Facts.md`/Python pipeline 提供，相關 SIP 不再作獨立 conflict source。
  - **市場錨定清理:** `SIP-RH01` 移除「市場熱門禁止低於 B+」評級底線；市場差距只可交由 `SIP-SL04` 作矩陣後第二次審視。
  - **退出馬應急退役:** `SIP-RR03` 改為 deprecated；大規模 scratchings 必須重跑 orchestrator，不准 LLM 手動迷你重排。
  - **Scanner lifecycle support:** `sip_conflict_scanner.py` 現在識別 `ACTIVE / BAKED / OBSERVATION / COMPLETE / DEPRECATED`，只有 ACTIVE SIP 參與方向衝突與重複計算掃描。
- **Target Files:** `00_sip_index.md`, `sip_conflict_scanner.py`, `02b_form_analysis.md`, `06_templates_rules.md`
- **Regression Check:** 若 baked SIP 仍被 scanner 當 active conflict source；或 SP/市場熱門直接改變矩陣評級 = 回歸。

### 2026-04-22 — EEM → 形勢與走位 重構 (EEM Elimination & Dimension Rename)
- **Changed:** 
  - **EEM 能量消耗公式完全移除:** 距離消耗量化公式（1-wide/2-wide/3-wide 基準）、場地消耗係數表（×0.6-×1.6）、疲勞累積乘數（×1.3/×1.6）全部刪除。LLM 無法可靠計算呢啲假精確數字。
  - **維度改名:** `EEM與形勢` 半核心維度改名為 `形勢與走位`，所有跨檔案引用同步更新。
  - **保留:** 所有步速適配矩陣、檔位風險規則（致命死檔/急彎封頂/內檔被困/C欄分級）、走位定性判斷全部保留。
  - **新判斷標準:** ✅ Strong = 步速配合引擎 / 好檔慢步速偷襲 / 上仗蝕位今仗改善 / 低消耗大勝。❌ Weak = 步速錯配 / 急彎外檔後追 / 靚位慢步速仍大敗。
- **Target Files:** 全引擎所有 .md 檔案（02d, 02f, 06_templates, SKILL.md, 00_sip_index, au_factor_interaction, 02g, 02h, 02b, 02c, 04c, 04d, engine_directives 等）
- **Regression Check:** 若引擎仍出現 `EEM` 字樣（sip_changelog 除外）= 回歸。若引擎仍嘗試計算走位距離公式 = 回歸。


### 2026-04-22 — EEM → 形勢與走位 重構 (EEM Quantitative Removal)
- **Changed:** 
  - **EEM 能量消耗公式全部移除:** 距離消耗公式 (1-wide +0m, 2-wide +3-5m...)、場地調節係數 (×0.6~×1.6)、疲勞累積乘數 (×1.3/×1.6)、四大觸發條件命名 ([逆境破格]/[超級反彈]/[隱形消耗]/[姿態破格]) 全部移除。
  - **維度重命名:** `EEM與形勢` / `EEM潛力` → `形勢與走位`（半核心），判斷標準改為純定性（步速適配/檔位利弊/走位風險）。
  - **保留:** 步速瀑布/Speed Map/引擎-步速適配矩陣/檔位風險 SIP (SIP-R14-2/R14-3/C14-1/RR11/RR13)/SIP-8 頂級後追豁免 — 全部保留。
  - **AU + HKJC 同步處理。**
- **Target Files:** `02d_eem_pace.md`, `02f_synthesis.md`, `06_templates_core.md`, `SKILL.md`, `au_factor_interaction.md`, `02g_override_chain.md` + HKJC `05_forensic_eem.md`, `06_rating_aggregation.md`, `SKILL.md`
- **Regression Check:** 若引擎再次出現量化 EEM 消耗公式（如 ×1.3 / +8-12m / [逆境破格 The Monster]） = 回歸。

### 2026-04-22 — V11 Pipeline SIP Cleanup (Data Verification & Batch Anchors)
- **Changed:** 
  - **DEPRECATED SIP-WF01, SIP-C14-4, SIP-CH18-1, SIP-CH18-3, SIP-SL03:** 由於 V11 Orchestrator 及 Data Scraper 穩定性大增，LLM 唔需再做人肉 Data Validator（退賽馬/負磅/距離/防幻覺檢查已交由 Python 處理）。
  - **DEPRECATED SIP-ST8, SIP-WF03:** V11 轉為逐匹馬處理並填寫 JSON，舊式 Batch 比較防惰性機制及 Markdown 畫獎牌榜強制規定已廢除。
  - **RETAINED:** 所有與賽馬實戰、領域知識（如場地偏差、步速耗損、冷門保護等）相關嘅 SIP 保持不變。
- **Target Files:** `01_system_context.md`, `02b_form_analysis.md`, `06a_data_retrieval.md`, `05_verification.md`, `SKILL.md`, `06_templates_rules.md`, `06_templates_core.md`, `00_sip_index.md`
- **Regression Check:** 若引擎再次因為退賽馬、負磅計算或 Batch 字數而觸發內部自我打回 = 回歸。

### 2026-04-17 — SIP-CB01: Cranbourne 覆盤 — 輔助維度 Data Sufficiency Guard + QG Deep Prep 偵測 + Scraper 更新
- **Changed:** 
  - **SIP-CB01 BAKED:** `02f_synthesis.md` 場地適性維度加入 ≥3 場門檻 + 賽績線 1/1 封頂 ✅ (非 ✅✅)
  - **QG-CHECK 強化:** `02h_quality_control.md` 加入 Deep Prep 合規自動偵測 + Data Sufficiency 合規檢查
  - **Scraper 更新:** `06a_data_retrieval.md` + `au_reflector/SKILL.md` Step 1 加入 `claw_racenet_results.py` (Racenet 賽果專用 Claw Code scraper)
  - **OBS-CB02/CB03 記入觀察:** Soft EEM 加權 + 排序可靠度分層 — 待累積數據
- **Target Files:** `02f_synthesis.md`, `02h_quality_control.md`, `00_sip_index.md`, `06a_data_retrieval.md`, `au_reflector/SKILL.md`
- **Regression Check:** 若場地適性 ≤2 場仍獲 ✅ = 回歸。若賽績線 1/1 仍獲 ✅✅ = 回歸。若 Deep Prep ≥6 仗 + 狀態 ✅ 無品質警報 = 回歸。

### 2026-04-07 — 全引擎深度審查 + 架構清理 (Engine Forensic Review & Cleanup)
- **Changed:** 全面審查 AU Horse Analyst 引擎，執行以下改動：
  - **邏輯矛盾修復:** `temp_03.md` Step 14 + `temp_02.md` Step 4 加 `[HKJC ENGINE ONLY]` 標記
  - **模板衝突解決:** 刪除 `au_template.md`，更新模板路徑至引擎自身 `06_templates_core.md` / `06_templates_rules.md`
  - **Logic Proof 簡化:** 15 步 checklist → 5 錨點（情境→段速→EEM→維度計數→查表）
  - **1000m 模組簡化:** 4 規則 → 2 規則（α: 後追降級, β: 前速加成）
  - **OBS-004 畢業:** Maiden 冷門馬盲點 → SIP-OBS04，BAKE 入 `02f_synthesis.md`
  - **檔案合併:** `06a` 兩個版本合併為一
  - **SIP Index 重新定位:** AU + HKJC 明確為 Lookup Table + Watchlist
  - **Reflector 更新:** AU + HKJC Reflector 加入 BAKED SIP 感知指引
  - **P33-WLTM 修復:** HKJC Reflector `write_to_file` → `run_command`
- **Target Files:** SKILL.md, 02a, 02f, 06a, 00_sip_index.md (AU+HKJC), observation_log.md, au-wong-choi.md, temp_02/03.md, Reflector SKILL.md (AU+HKJC)
- **Regression Check:** 若 AU 引擎仍引用 Purton/Moreira = 回歸。若 Logic Proof 仍為 15 步 = 回歸。

### 2026-04-06 — SIP-RH07~RH10 + OBS-004: Rosehill 覆盤批量 SIP（4 項 + 1 觀察項）
- **Changed:** 新增 4 項 SIP + 1 觀察項，源自 Rosehill 全日 Soft 6 場覆盤
- **Target Files:** `04d_wet_track.md`, `02g_override_chain.md`, `04b_track_rosehill.md`, `observation_log.md`
- **Regression Check:** 若 Soft 5-6 下前領型馬匹仍獲 S/S+ 評級 = 回歸

### 2026-04-06 — SIP-SL01~SL05: Sandown Lakeside 覆盤批量 SIP(5 項)
- **Changed:** S/A+ 實戰驗證門檻 + Good 場前領校準 + 退出馬驗證 + 市場偏差審視 + 初出馬通道升級
- **Target Files:** `02f_synthesis.md`, `02d_eem_pace.md`, `05_verification.md`, `06_templates_core.md`, `06_templates_rules.md`
- **Regression Check:** 若近 3 仗全無入位但引擎仍評 S/S- = 回歸

<!-- Newest entries at top. Keep last 5 updates only. Archive older entries to 00_sip_index.md. -->
