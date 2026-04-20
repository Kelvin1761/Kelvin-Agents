# 🤖 香港賽馬機讀指令與硬性約束 (V3.0 Engine Directives)

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
            1. 標題包乾：每一匹馬必須完整包含 `📌情境`、`賽績總結`、`完整賽績檔案(含寬恕認定)`、`馬匹分析(含🎯檔位判讀+📊全段速剖面+📐頭馬距離+🔄走位段速複合+📉完成時間偏差+EEM能量)`、`🔗賽績線`、`📊評級矩陣`、`14.2/14.2B/14.3`、`💡結論`、`⭐最終評級`，不得省略。
            2. 字數下限硬執行：S/A 級馬 ≥ 500字，B 級馬 ≥ 350字，C/D 級馬 ≥ 300字。
            3. 零容忍 [FILL]：分析結束時若仍存有 `[FILL]` 或 `{{LLM_FILL}}` 標記，視為嚴重偷懶違規，需自動補回。
        </rules>
    </directive>

    <directive name="PREMATURE_STOP_GUARD" priority="CRITICAL">
        <description>防止全自動化分析中途停機等待用戶指令。</description>
        <rules>
            1. 在所有 Batch (Batch 1 to N 及 Verdict Batch) 完成前，嚴禁輸出給用戶的普通文本回覆。
            2. 連鎖寫入：每次 heredoc 寫檔通過後，如果還有剩餘馬匹，立即啟動下一個 tool call 生成下個 Batch，不可詢問「是否繼續」。
            3. 回覆攔截器：在打算結束回應前自問「Analysis.md 入面有冇 🏆 Top 4 位置精選?」，若沒有則退回繼續執行。
        </rules>
    </directive>

    <directive name="BATCH_EXECUTION_LOOP" priority="HIGH">
        <description>嚴格的多 Tool call 批次執行結構定義。</description>
        <protocol>
            Step 1: 先計算 BATCH_PLAN（例如 7匹馬 = Batch 0[戰場全景] + Batch 1[3匹] + Batch 2[3匹] + Batch 3[1匹] + Verdict Batch）。
            Step 2: Batch 0 (戰場全景) 必須優先獨立進行，確保在看馬匹前了解局勢。
            Step 3: 每個馬匹 batch 前必須強制 `view_file` 讀取 `horse_analysis_skeleton.md` 作為骨架。
            Step 4: 使用 Safe-Writer Protocol（Python base64 寫法）。第一個寫檔的 Batch 用 overwrite，後續全用 append。
            Step 5: 絕對嚴禁在 Batch 1~N 中提前寫入或給予 Verdict (最終判決)，Verdict Batch 必須壓軸。
            Step 6: 每個 batch 寫入完成均需留下 `🔒 BATCH_QA_RECEIPT` 標誌。
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
    
    <directive name="VERDICT_JIT_TEMPLATE_CHECKPOINT" priority="HIGH">
        <description>防止最後的 Verdict 格式因注意力衰退而漂移。</description>
        <rules>
            1. 在撰寫 VERDICT BATCH 前，必須強制 `view_file` 讀取 `08_templates_rules.md` (或同等格式文件)。
            2. 確保一定包含 🥇🥈🥉🏅 清單，並具備馬號、評級、理據、風險四大要點。嚴禁使用 Numbered List (1, 2, 3...) 代替名次。（注意：馬名由 compile 腳本自動從 JSON 取出，LLM 只需填寫 horse_num。）
        </rules>
    </directive>

    <directive name="PYTHON_SCRIPT_ENFORCEMENT" priority="CRITICAL">
        <description>強制 LLM 必須使用 Python 腳本處理所有數據操作，嚴禁自行跳過。</description>
        <rules>
            1. 嚴禁自行建立任何 .py 腳本（只有白名單內嘅腳本可以存在）
            2. 嚴禁自行計算評級矩陣分數（由 compile_analysis_template_hkjc.py 自動計算）
            3. 嚴禁自行生成 Analysis.md（由 Orchestrator 調用 compile 腳本自動生成）
            4. 嚴禁自行解析 Facts.md 全局數據（只讀取 .runtime/Active_Horse_Context.md）
            5. 嚴禁自行修改 _session_tasks.md（由 Orchestrator 自動管理）
            6. 每次完成 JSON 填寫後，必須重新執行 Orchestrator（唯一合法嘅下一步動作）
            7. 前置環境檢查：每次 Orchestrator 啟動自動執行 preflight_environment_check.py
        </rules>
        <forbidden_actions>
            - 自行建立 .py 檔案
            - 自行計算 ABCD 評級
            - 自行 compile markdown
            - 讀取 Active_Horse_Context.md 以外嘅 Facts 數據
            - 跳過 Orchestrator 直接處理下一匹馬
        </forbidden_actions>
    </directive>

</engine_directives>
