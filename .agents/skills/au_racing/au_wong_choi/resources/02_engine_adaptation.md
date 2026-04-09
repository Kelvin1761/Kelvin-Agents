# Engine Adaptation

# 🤖 ENGINE ADAPTATION(P31 — 2026-03-31 新增 — Priority 0)

> **歷史教訓:** 2026-03 月下旬起主要使用 Gemini 3.1 Pro 跑分析,發現 Batch 1 完成後 LLM 停機等用戶、Verdict 被遺漏。根本原因:Gemini 唔會好似 Opus 咁自動連鎖多個 tool calls。
>
> **適配規定(Priority 0 — 適用所有引擎):**
>
> 1. **LOOP_CONTINUATION_MARKER(每個 batch 寫完後強制輸出):**
>    喺每個 batch 嘅 tool call 完成後,你必須喺你嘅內部思考中明確寫:
>    `CONTINUE_LOOP: Batch [N] done, [M] batches + VERDICT remaining. Proceeding to Batch [N+1].`
>    若 M = 0(所有馬匹 batch 完成),寫:
>    `CONTINUE_LOOP: All horse batches done. VERDICT BATCH remaining. Proceeding to write VERDICT.`
>    **呢個標記嘅目的**係提醒你自己仲有嘢做,唔好停機。
>
> 2. **PREMATURE_STOP_GUARD(回覆用戶前攔截器):**
>    若你準備向用戶輸出文字回覆(非 tool call),必須先問自己:
>    「Analysis.md 入面有冇 🏆 Top 4 位置精選?」
>    → 若冇 → ⛔ 你仲未寫完!返回 batch 循環繼續!
>    → 若有 → 繼續正常流程
>
> 3. **Tool Call Chaining 指引:**
>    - 每完成一個 batch 嘅寫入 + QA → 立刻進入下一個 batch
>    - 唔好等用戶回覆、唔好輸出中間報告
>    - 唯一允許停機嘅情況:(a) 全場完成含 Verdict、(b) 錯誤需要用戶介入
>
> 4. **GEMINI ANTI-LAZINESS REINFORCEMENT(防止 Gemini 跳過邏輯):**
>    Gemini 引擎傾向喺 token 壓力下壓縮或跳過分析步驟。以下措施強制對抗:
>    - **Emoji 計數自檢:** 每匹馬寫完後,喺內部思考中數 emoji 標題:⏱️🐴🔬⚡📋🔗🧭⚠️📊💡⭐ = 11 個。少於 11 個 = 你壓縮咗 → 立即補全。
>    - **字數門檻硬執行:** 每匹馬完成後估算字數。S/A ≥500 | B ≥350 | C/D ≥300。若明顯不足 → 你偷懶咗 → 擴展分析。
>    - **禁止「因為評級低所以簡寫」:** D 級馬同 S 級馬用同一個骨架模板。D 級需要用數據解釋「點解差」,唔係寫一句「近績差唔推薦」就算。
>    - **骨架 [FILL] 零容忍:** 若寫完嘅分析仍然包含 `[FILL]` 文字 → 你跳過咗填充 → 立即補回。
>    - **🐴 馬匹剖析 5 項必填:** 班次負重 + 引擎距離 + 步態場地 + 配備意圖 + 人馬組合。缺任何一項 = 骨架未完全填充。
>    - **🐴 馬匹剖析格式嚴規 (P35 — 2026-04-06 新增 — Priority 0):**
>      - 馬匹剖析**僅為簡潔分類標籤**，每項以 `[標籤]` 格式撰寫，禁止寫成段落或散文。
>      - ✅ 正確示範: `- **步態場地:** [未有 Soft 地數據，但血統顯示應能應付]`
>      - ✅ 正確示範: `- **引擎距離:** [Type A 短途爆發]`
>      - ✅ 正確示範: `- **人馬組合:** [Rachel King 騎法硬朗，適合此駒]`
>      - ❌ 錯誤示範: `- **步態場地:** [無]` （禁止用「無」一字帶過）
>      - ❌ 錯誤示範: 在馬匹剖析下寫整段 200+ 字分析文章（這些內容屬於 💡結論 > 核心邏輯）
>      - **深度法醫分析（戰術推演、歷史比較、風險評估、綜合判定）必須全部歸入 `💡 結論 > 核心邏輯` 區域。**
>      - **自檢觸發器:** 若你嘅馬匹剖析任何一項超過 30 字 → 你已違規 → 將多餘內容搬去核心邏輯。

# 🚨 OUTPUT_TOKEN_SAFETY(P28 — 2026-03-29 新增 — Priority 0)

> **歷史教訓:** 2026-03-29 HKJC Heison 140/140 匹馬 FAILED。根本原因:**output token limit exceeded**。
>
> **適應性規定(Priority 0):**
>
> 1. **DEFAULT BATCH_SIZE = 3**(標準)。環境掃描通過後可以使用 3。
> 2. **環境掃描失敗 → BATCH_SIZE = 2**(安全 fallback)。
> 3. **VERDICT BATCH 必須為獨立 tool call**。
> 4. **Token 壓力自測**:若壓縮內容 → 立即停止拆到下一個 batch。
> 5. **若任何 batch 被截斷 → 自動降級為 BATCH_SIZE=2 並重做。**

