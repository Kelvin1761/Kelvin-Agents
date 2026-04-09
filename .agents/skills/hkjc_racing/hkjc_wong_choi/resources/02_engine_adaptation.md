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
>    - **Emoji 計數自檢:** 每匹馬寫完後,喺內部思考中數 emoji 標題:📌⏱️🔬⚡📋🔗📊💡⭐ = 9 個。少於 9 個 = 你壓縮咗 → 立即補全。
>    - **字數門檻硬執行:** 每匹馬完成後估算字數。S/A ≥500 | B ≥350 | C/D ≥300。若明顯不足 → 你偷懶咗 → 擴展分析。
>    - **禁止「因為評級低所以簡寫」:** D 級馬同 S 級馬用同一個骨架模板。D 級需要用數據解釋「點解差」,唔係寫一句「近績差唔推薦」就算。
>    - **骨架 [FILL] 零容忍:** 若寫完嘅分析仍然包含 `[FILL]` 文字 → 你跳過咗填充 → 立即補回。
>    - **引擎距離必填:** 每匹馬必須有「引擎距離:Type [X]...」一行。缺失 = 骨架未完全填充 = 需要補回。

# 🚨 OUTPUT_TOKEN_SAFETY(P28 — 2026-03-29 新增 — Priority 0)

> **歷史教訓(根本原因確認):** 2026-03-29 Heison 嘅分析質量崩潰,140/140 匹馬全部 FAILED。根本原因:**output token limit exceeded**。模型喺 Batch 寫入時超出最大 output token 上限,被截斷。
>
> **適應性規定(Priority 0):**
>
> 1. **DEFAULT BATCH_SIZE = 3**(標準)。環境掃描通過後可以使用 3。
> 2. **環境掃描失敗 → BATCH_SIZE = 2**(安全 fallback)。
> 3. **VERDICT BATCH 必須為獨立 tool call**,唔可以同馬匹分析合併。防止最後一批超出 token limit。
> 4. **Token 壓力自測**:若你感覺到自己正在壓縮內容 → **立即停止當前 batch,將剩餘馬匹拆到下一個 batch**。
> 5. **若任何 batch 被截斷(output truncated)→ 自動降級為 BATCH_SIZE=2 並重做該 batch**。

