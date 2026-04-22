<!-- ============================================================ -->
<!-- Quality Control & Anti-Laziness Protocol (Consolidated) -->
<!-- Created 2026-04-05 — Phase 3.4 Engine Refactoring -->
<!-- Dependencies: None (standalone reference) -->
<!-- Referenced by: 01_system_context.md, Analyst SKILL.md, Wong Choi SKILL.md -->
<!-- ============================================================ -->

# Quality Control & Anti-Laziness Protocol (Consolidated)

> **Source:** Merged from:
> - `01_system_context.md` §1 Anti-Laziness Protocol
> - Analyst `SKILL.md` §Anti-Laziness 錨定 + QG-CHECK
> - Wong Choi `SKILL.md` P33 核心邏輯品質標準
> - Wong Choi `SKILL.md` P31 GEMINI ANTI-LAZINESS REINFORCEMENT

## 1. 結構完整性 (Structural Integrity)

- 每匹馬完整保留 9 個可見 section（⏱️📋🐴🔗🧭⚠️📊💡⭐）及 11 個語義錨點；🔬 段速與 ⚡ 形勢 已整合入 📋 / 💡，不可用舊獨立標題要求打回
- D 級馬零豁免：同 S 級馬使用相同骨架模板
- 禁止 `[FILL]` 佔位符：若寫完嘅分析仍然包含 `[FILL]` → 立即補回
- 🐴 馬匹剖析 5 項必填：班次負重 + 引擎距離 + 步態場地 + 配備意圖 + 人馬組合

## 2. 字數門檻 (Word Count Thresholds)

| Grade | Min Words (Total) | Min Words (Core Logic) |
|:--|:--|:--|
| S/A | ≥500 | ≥80 |
| B | ≥350 | ≥60 |
| C | ≥300 | ≥50 |
| D | ≥300 | ≥40 |

## 3. 語言風格 (P33 核心邏輯品質標準)

- 全程使用香港繁體中文（廣東話口吻）
- 馬匹名稱、練馬師、騎師保留英文原名
- 每匹馬引用 ≥3 個獨特數據點
- 禁止空泛評價（如「近績差唔推薦」），必須用數據解釋

## 4. Anti-Laziness 錨定 (Batch Quality Guard)

- **Batch 1 基線：** 首批次建立每匹馬平均字數基線
- **70% 地板：** 後續批次每匹馬平均字數不得低於 Batch 1 嘅 70%
- **跨場次一致性：** Race 2+ 必須維持 Race 1 嘅分析深度
- **偵測到壓縮 → 立即自我打回重寫**

## 5. QG-CHECK Protocol (品質守門員)

- **重複數據偵測：** 對本批次所有馬匹的段速值、走位形勢代碼、穩定性判定、騎練上名率進行去重
- **觸發條件：** ≥50% 馬匹出現完全相同數值 → 品質警報 🚨
- **處理：** 暫停並逐匹重新以獨立數據填充
- **關鍵馬交叉驗證：** Top 4 馬匹的核心邏輯必須能抵受「若 X 條件改變」壓力測試
- **[SIP-CB01] 維度合規自動偵測：**
  - 🚨 **Deep Prep 合規檢查：** 若馬匹狀態週期為 Deep Prep (≥6 仗) 但「狀態與穩定性」維度被判為 ✅ → 觸發品質警報。02f_synthesis.md 明確列 Deep Prep ≥6 仗為 ❌ 條件。近期案例：Cranbourne 2026-04-17 R4 #2 Parera (Deep Prep 第 10 仗被錯誤評為 ✅✅ → 導致 S 級嚴重過高)
  - 🚨 **Data Sufficiency 合規檢查：** 若場地適性維度 = ✅ 但同場地類型出賽次數 ≤2 場 → 觸發品質警報。若賽績線 = ✅✅ 但強組比例為 1/1 → 觸發品質警報

## 6. Engine Adaptation (P31 Gemini Anti-Laziness)

- **LOOP_CONTINUATION_MARKER：** 每個 batch 寫完後強制輸出繼續標記
- **PREMATURE_STOP_GUARD：** 回覆用戶前檢查分析檔案是否有 🏆 Top 4
- **Section 計數自檢：** 每匹馬寫完後確認 9 個可見 section 齊全，且核心邏輯內有段速 + 形勢 判斷。少任何一項 = 壓縮咗
- **字數門檻硬執行：** 每匹馬完成後估算字數
- **骨架 [FILL] 零容忍**

## 7. COMPLETION_GATE (P31)

完成分析後必須執行：
```bash
python3 .agents/scripts/completion_gate_v2.py "<分析檔案路徑>" --domain au
```
Windows 或已配置 `python` launcher 嘅環境可將 `python3` 換成 `python`；正常 V11 流程由 AU Orchestrator 自動執行呢個 gate。
- ❌ FAILED → 立即修正並重新執行直到 ✅ PASSED
- 不過關不准完成任務
