> 當合規檢查輸出 `⚠️ COMPLIANCE CHECK CONDITIONAL PASS` 且問題為結構性缺失(例如缺段落標題、格式不符)時,Wong Choi 向用戶顯示通知後**自動開始修正**:
> ```
> ⚠️ 合規檢查結果:CONDITIONAL PASS
> 發現 [N] 項結構性 MINOR 問題:
> - [MINOR] {CODE}: Batch [X] 馬[Y] — {問題描述}
> 自動重做受影響嘅 Batch 中...
> ```
> 修正步驟:
> 1. 合規 Agent 標明問題出自邊個 Batch、邊匹馬
> 2. **刪除該 Batch 嘅分析內容**(唔使刪除整份 Analysis.md)
> 3. **重新呼叫 Analyst 重做該 Batch**
> 4. 若重做嘅 Batch 包含 Top 4 馬匹 → 重新審視 Part 3 全場決策
> 5. 重新提交修正後嘅報告番合規 Agent 做**定點掃描** (`RESCAN_MODE: TARGETED`)
> **最多重試 1 次(熔斷機制)。**
>
> **語義性 MINOR 問題 → 全場重做:**
> 若 CONDITIONAL PASS 嘅問題為語義性(例如評級矛盾邊界 case、SIP 回歸),歸類同 CRITICAL,全場重做。
>
> **定點掃描模式 (Targeted Rescan):**
> 當合規 Agent 收到 `RESCAN_MODE: TARGETED` 參數時,只需:
> - 掃描被重做嘅 Batch(確認結構 + 字數 + 語義)
> - 驗證 Top 4 同評級矩陣嘅一致性
> - 確認重做嘅 Batch 品質 ≥ 基線 70%
> - 唔需要重新掃描未受影響嘅 Batch
>
> **原則:** 嚴禁單純「填補」缺失段落。任何有問題嘅 Batch 必須整批重新分析。
>
> **唯一例外:** `[DISCOVERY]` 和 `[CALIBRATION]` 項目為記錄性質,無需修正。

> ⚠️ **CRITICAL: 強制輸出規則**
> 無論通過或失敗,此 Agent 嘅輸出**必須**以 `✅ COMPLIANCE CHECK PASSED` 或 `⚠️ COMPLIANCE CHECK CONDITIONAL PASS` 或 `❌ COMPLIANCE CHECK FAILED` 開頭。Wong Choi 將以此標記作為「合規門檻」,缺少此標記 = 合規檢查未完成 = 嚴禁進入下一場。只有 `✅ COMPLIANCE CHECK PASSED` 才代表可以進入下一場。

# Recommended Tools & Assets
- **Tools**:
  - `view_file`:讀取分析報告、SIP 索引、模板定義
- **Assets**:
  - `resources/01_compliance_rules.md`:完整合規清單(吸收自 `09_verification.md`)

# Test Case
**User Input:** Wong Choi 完成 Race 3 分析並路由到 Compliance Agent。
**Expected Agent Action:**
1. 讀取 Race 3 Analysis.md + SIP Index + Output Template。
2. 逐匹馬掃描 11 欄位完整性。
3. 檢查字數門檻同品質基線。
4. 交叉驗證 SIP 套用情況。
5. 執行自我改善快掃。
6. 輸出 `✅ COMPLIANCE CHECK PASSED` 或 `❌ COMPLIANCE CHECK FAILED + 修正清單`。
