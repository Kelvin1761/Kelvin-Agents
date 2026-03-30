# Agent Architecture — CHANGELOG

---

## P31 — MUST_INVOKE_VALIDATOR（強制 Validator 調用）

**日期：** 2026-03-29
**影響版本：** AU Reflector v1.1.0 + HKJC Reflector v1.1.0

| 變更 | 說明 |
|:---|:---|
| **Bug Fix** | Reflector 完成 SIP 套用後只顯示被動文字提示，從未真正調用 Validator |
| **根本原因** | Step 6c 只係 `[!IMPORTANT]` 提示 — 冇執行協議、冇數據交接格式、冇自檢機制 |
| **修正** | Step 6c 升級為 `[!CAUTION]` Priority 0 強制調用協議（P31） |
| **新增** | 3-step 調用流程：6c-1 輸出提示 → 6c-2 用戶確認後立即調用 Validator → 6c-3 拒絕處理 |
| **數據交接** | 新增完整 Validator 調用數據包格式（TARGET_DIR / VENUE / DATE / SIP_CHANGELOG / REFLECTOR_REPORT） |
| **自檢** | 新增 self-check trigger：「若完成 6b 但冇執行 6c → 已違規 → 立即補上」 |
| **設計參考** | 模仿 Wong Choi P29 MUST_OUTPUT_HANDOFF 嘅強制輸出模式 |

---

## P30 — Race Day Briefing（賽日總覽）

**日期：** 2026-03-29
**影響版本：** AU Wong Choi v2.1.0 + HKJC Wong Choi v2.1.0

| 變更 | 說明 |
|:---|:---|
| **新 Step** | HKJC: `Step 2.5` / AU: `Step 1.5` — Race Day Briefing |
| **用途** | 提取完成後自動生成全日賽事鳥瞰圖，包括每場距離、班級、出馬數、預計批次、Session 分割計劃、風險 Flag |
| **持久化** | 寫入 `{TARGET_DIR}/_Race_Day_Briefing.md`，Session Recovery 時可直接讀取 |
| **用戶確認** | Briefing 生成後停低等用戶確認分析範圍（全日 / 指定場次 / 前半日） |
| **設計理念** | 取代 AG Kit `/plan` 嘅通用 planning 功能，提供賽馬分析專用嘅 domain-specific planning step |

---

## Agent Architecture v2.0

**日期：** 2026-03-18
**版本：** 全部被修改嘅 Agent 升至 v2.0.0

---

## 新建 Agent（2 個）

| Agent | 路徑 | 用途 |
|:---|:---|:---|
| HKJC Batch QA | `hkjc_racing/hkjc_batch_qa/SKILL.md` | 每批次結構 + 語義 + 反惰性品質關卡 |
| AU Batch QA | `au_racing/au_batch_qa/SKILL.md` | 每批次品質關卡（AU 5×13 版） |

## 新建文件（2 個）

| 文件 | 路徑 | 用途 |
|:---|:---|:---|
| SIP Changelog (HKJC) | `hkjc_horse_analyst/resources/sip_changelog.md` | SIP 更新日誌，用於回歸偵測 |
| SIP Changelog (AU) | `au_horse_analyst/resources/sip_changelog.md` | AU SIP 更新日誌 |

## 修改 Agent（8 個 SKILL.md）

| Agent | 主要變更 |
|:---|:---|
| Agent Architect | Step 0 三模式路由 + Agent 健康檢查 |
| HKJC Wong Choi | 移除 QA 邏輯 → Batch QA 路由、情報寫檔、修復重複 Step 4b |
| AU Wong Choi | 移除 QA 邏輯 → Batch QA 路由、情報寫檔 |
| HKJC Compliance | 分級修正策略 + RESCAN_MODE + Batch QA 職責分界 |
| AU Compliance | 同 HKJC |
| HKJC Reflector | SIP Changelog 維護 + 設計模式建議輸出 |
| AU Reflector | 同 HKJC |
| AU Reflector Validator | 全面重寫（79→190 行） + 選擇性驗證 |
| HKJC Reflector Validator | Step 1.5 選擇性驗證 |

## 修改 Resource 文件（4 個）

| 文件 | 變更 |
|:---|:---|
| `design_patterns.md` | Pattern 8-16（9 個新模式） |
| `ecosystem_reference.md` | 資料夾結構 + Agent 表 + Pipeline 流程圖 |
| HKJC `01_compliance_rules.md` | Section G: 定點掃描協議 + 結構性/語義性 MINOR 分類 |
| AU `01_compliance_rules.md` | 同 HKJC |
