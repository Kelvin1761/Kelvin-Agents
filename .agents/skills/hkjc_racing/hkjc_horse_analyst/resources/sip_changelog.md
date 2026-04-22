# 規則變更紀錄 (Rule Change Log)
> 合規 Agent 每次掃描時讀取此文件。

## Latest Updates

### 2026-04-23 — SIP 標籤系統全面淘汰
- **Changed:**
  - **55+ 個 SIP 標籤全部移除。** 規則文字保持不變，直接嵌入 Steps 0-14 分析流程。
  - `00_sip_index.md` 重寫為「覆盤決策紀錄」，降級至 Tier 3（歷史參考）。
  - SIP-P3a~d 改名為 DATA-xxx（Python 數據自動化）。
  - LLM 無需再記住任何 SIP 編號 — 跟住分析步驟自然流走即可。
- **Target Files:** 全部 resource 檔案
- **Regression Check:** 若任何 resource 檔案仍出現 `SIP-` 前綴 = 回歸。00_sip_index + sip_changelog 除外。

### 2026-04-23 — Analyst 深度清理 (Deep Cleanup)
- **Changed:**
  - Template 去重（`08_templates_core.md` -60行）
  - 維度命名統一（`形勢與消耗` → `形勢與走位`）
  - `06_rating_aggregation.md` 拆分為 06a/06b/06c
  - WALL-017 防幻覺規則（原 SIP-009）
  - Standalone 模式移除
- **Target Files:** 08_templates_core.md, 06a/b/c, SKILL.md, 05_forensic_eem.md

### 2026-04-22 — EEM → 形勢與走位 重構
- **Changed:** EEM 能量消耗公式完全移除，維度改名，致命死檔數據化。
- **Target Files:** 05_forensic_eem.md, 06a_rating_table.md, SKILL.md 等

### 2026-04-06 — 冷門馬訊號標準化
- **Changed:** 冷門馬訊號新增 7 項標準化觸發條件
- **Target File:** `08_templates_rules.md`

### 2026-04-06 — 沙田草地覆盤系列
- **Changed:** 直路賽放頭壟斷覆蓋、大熱崩潰壓力測試、二班後追馬加分、跨場減分馬偵測
- **Target Files:** 10a, 06b, 04

<!-- Newest entries at top. Keep last 5 updates only. -->
