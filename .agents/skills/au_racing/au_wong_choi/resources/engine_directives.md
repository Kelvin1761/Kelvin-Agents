# 🇦🇺 澳洲賽馬機讀指令與硬性約束 (V3.0 Engine Directives)

本文件包含所有影響 Agent 運行邊界、Token 保護及防偷懶的底層約束。請嚴格遵守以下由 `<xml>` 標記的系統指令，這些指令凌駕於一切常規提示詞之上。

<engine_directives>

    <directive name="OUTPUT_TOKEN_SAFETY" priority="CRITICAL">
        <description>防止在寫入長篇分析時觸發 LLM Output Token Limit 截斷錯誤。</description>
        <rules>
            1. BATCH_SIZE 限制：DEFAULT BATCH_SIZE 設為 3。若 pre-flight 測試失敗，降級為 2。
            2. 獨立寫入：每批次必須使用獨立的 tool call。**嚴禁將 VERDICT BATCH 與任何馬匹分析合併。**
            3. Token 壓力自測：若在生成過程中感到 token 壓力導致內容壓縮，立即停止當前 batch，將剩餘馬匹拆至下一批次。
            4. 截斷重做：若發現輸出被 "output limit exceeded" 截斷，自動降級 BATCH_SIZE=2 並重做該批。
        </rules>
    </directive>

    <directive name="GEMINI_ANTI_LAZINESS_REINFORCEMENT" priority="CRITICAL">
        <description>對抗 Gemini 引擎在長對話中跳過步驟或過度壓縮的壞習慣。</description>
        <rules>
            1. 標題包乾：每一匹馬必須完整包含所有 11 個標題 (⏱️🐴🔬⚡📋🔗🧭⚠️📊💡⭐)，不得省略。
            2. 🐴 馬匹剖析格式：僅為簡潔「分項標籤」，嚴禁寫成散文或整段文章。所有深度推理必須歸入 `💡 結論 > 核心邏輯`。
            3. 字數下限硬執行：S/A 級馬 ≥ 500字，B 級馬 ≥ 350字，C/D 級馬 ≥ 300字。
            4. 零容忍 [FILL]：分析結束時若仍存有 `[FILL]` 或 `{{LLM_FILL}}` 標記，視為嚴重偷懶違規，需自動補回。
        </rules>
    </directive>

    <directive name="PREMATURE_STOP_GUARD" priority="CRITICAL">
        <description>防止全自動化分析中途停機等待用戶指令。</description>
        <rules>
            1. 每次 heredoc 寫檔通過後，如果還有剩餘馬匹，立即啟動下一個 tool call 生成下個 Batch，不可詢問「是否繼續」。
            2. 回覆攔截器：在打算結束回應前自問「Analysis.md 入面有冇 🏆 全場最終決策?」，若沒有則退回繼續執行。
        </rules>
    </directive>

    <directive name="BATCH_EXECUTION_LOOP" priority="HIGH">
        <description>嚴格的多 Tool call 批次執行結構定義。</description>
        <protocol>
            Step 1: 先計算 BATCH_PLAN（例如 7匹馬 = Batch 1[3匹] + Batch 2[3匹] + Batch 3[1匹] + Verdict Batch）。
            Step 1b: 生成 Speed Map 初稿 `python .agents/scripts/au_speed_map_generator.py <Racecard.md> --distance <Distance>`
            Step 2: 每個 batch 前必須強制 `view_file` 讀取 `06_templates_core.md` 作為骨架。
            Step 3: 使用 Safe-Writer Protocol（Python base64 寫法）。
            Step 4: 每次執行後必須留有 `🔒 BATCH_QA_RECEIPT`。
        </protocol>
    </directive>

    <directive name="P19V6_SAFE_WRITER_PROTOCOL" priority="CRITICAL">
        <description>禁止直接修改檔案內容，防止 Google Drive 雲端死鎖風險。嚴禁調用 write_to_file / replace_file_content。</description>
        <rules>
            1. ⚠️ 完全禁用：`write_to_file`, `replace_file_content`, `multi_replace_file_content`。
            2. 唯一合法寫檔方式：Heredoc 生成 python 腳本寫入至 `/tmp`，再以 `safe_file_writer.py` 進行操作。
        </rules>
        <implementation>
            <![CDATA[
            SAFE_WRITER=".agents/scripts/safe_file_writer.py"

            # 跨平台寫法 — 用 Python 生成 base64 並調用 safe_file_writer:
            import subprocess, base64
            content = "[你的分析內容 / 檔案內容]"
            encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            subprocess.run([
                'python', SAFE_WRITER,
                '--target', '{TARGET_DIR}/{FILE_NAME}',
                '--mode', 'overwrite',
                '--content', encoded
            ], check=True)
            ]]>
        </implementation>
    </directive>
    
    <directive name="P37_ANTI_HALLUCINATION_DEEP_VERIFICATION" priority="CRITICAL">
        <description>對抗幻覺及賽績混淆的極級驗證機制（澳洲賽事特設）。</description>
        <rules>
            1. FACTS_MD 唯一數據源：嚴禁 LLM 自行從 Formguide 重算，必須全面依賴 Python inject 產生之 `Facts.md`。
            2. 反跑位混淆 (SETTLED ≠ FINISHED)：Formguide 中的 Settled 位置絕對不等於名次，名次必須以 Facts.md 內的 Last 10 數值為準。
            3. 反試閘混淆 (TRIAL_AWARENESS)：若賽績標示為 Trial，該場次不算數，名次必須向上一仗追溯。
            4. 反錨定偏差 (RATING_BLINDNESS)：必須先完成賽績法醫再參考 Rating 及配搭，嚴禁因為騎練名氣盲目提升評級。
            5. 反賠率偏差 (ODDS_INDEPENDENCE)：在評估完 8 維度矩陣之前，嚴禁參考 Flucs 賠率（賠率只在 Value Check 時使用）。
        </rules>
    </directive>
    
    <directive name="SIP_DA01_MULTI_PERSPECTIVE_VERDICT" priority="CRITICAL">
        <description>最後 Verdict 裁決的多角度五步曲。</description>
        <rules>
            1. 寫 Verdict 前必須先在內部經歷 5 步辯論：(A) 表面實力選馬 (B) 步速場地覆核 (C) 位置概率審計 (D) 值博率檢查 (E) 最終裁決（必須說明被替換馬的理由）。
            2. 禁止將 Verdict 壓縮成單行形式，每一隻 Top 4 精選必須包含「馬號、評級、核心理據、最大風險」之獨立重點。（注意：馬名由 compile 腳本自動從 JSON 取出，LLM 只需填寫 horse_num。）
        </rules>
    </directive>    

    <directive name="PYTHON_SCRIPT_ENFORCEMENT" priority="CRITICAL">
        <description>Force the LLM to use Python scripts for all data operations, never skip them.</description>
        <rules>
            1. NEVER create any .py scripts (only whitelisted scripts may exist)
            2. NEVER self-calculate the rating matrix (compile_analysis_template.py handles this)
            3. NEVER self-generate Analysis.md (Orchestrator calls the compile script)
            4. NEVER parse the full Facts.md (only read .runtime/Active_Horse_Context.md)
            5. NEVER modify _session_tasks.md (Orchestrator manages this automatically)
            6. After completing JSON fills, MUST re-run the Orchestrator (the only legal next action)
            7. Preflight check: preflight_environment_check.py runs automatically on each Orchestrator start
        </rules>
        <forbidden_actions>
            - Creating .py files
            - Self-calculating ABCD grades
            - Self-compiling markdown
            - Reading Facts data outside Active_Horse_Context.md
            - Skipping the Orchestrator to process the next horse
        </forbidden_actions>
    </directive>

</engine_directives>
