# SIP Changelog (AU)
> 合規 Agent 每次掃描時讀取此文件,特別檢查最近 2 次更新嘅 SIP 是否被正確套用。
> **只保留最近 5 條。** 完整歷史記錄見 `00_sip_index.md`。

## Latest Updates

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
  - **模板衝突解決:** 刪除 `au_template.md`，更新模板路徑至引擎自身 `06_output_templates.md`
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
- **Target Files:** `02f_synthesis.md`, `02d_eem_pace.md`, `05_verification.md`, `06_output_templates.md`
- **Regression Check:** 若近 3 仗全無入位但引擎仍評 S/S- = 回歸

### 2026-04-05 — P33-WLTM: 全引擎防串流鎖死封殺令
- **Changed:** 統一 AU / HKJC / NBA 三大引擎嘅 File Writing Protocol 至 P33-WLTM
- **Target Files:** AU/HKJC/NBA Wong Choi SKILL.md, race_analysis_workflow.md, design_patterns.md
- **Regression Check:** 若任何引擎仍包含 `write_to_file` 作為合法工具 = 回歸

<!-- Newest entries at top. Keep last 5 updates only. Archive older entries to 00_sip_index.md. -->
