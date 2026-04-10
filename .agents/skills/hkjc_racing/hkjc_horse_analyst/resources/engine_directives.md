# 🤖 香港賽馬分析專員引擎防呆協定 (Analyst Engine Directives)

本文件涵蓋 HKJC Horse Analyst 的所有硬性生成法則與防偷懶邊界。本檔案中的 `<xml>` 標籤具有最高優先級。

<engine_directives>

    <directive name="P19V6_SAFE_WRITER_PROTOCOL" priority="CRITICAL">
        <description>文件寫入防撞策略，防禦 Google Drive 鎖定漏洞。嚴禁調用 write_to_file 或 replace_file_content。</description>
        <rules>
            1. 絕對禁用：`write_to_file`, `replace_file_content`, `multi_replace_file_content`，一律不准用。
            2. 唯一合法寫檔方法：透過 `run_command` 利用 heredoc 建立 `/tmp` 檔案，然後 base64 傳入 safe_file_writer.py。
        </rules>
        <implementation>
            <![CDATA[
            SAFE_WRITER="/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/safe_file_writer.py"

            cat > /tmp/batch_N.md << 'ENDOFCONTENT'
            [你的分析內容]
            ENDOFCONTENT

            base64 < /tmp/batch_N.md | python3 "$SAFE_WRITER" \
              --target "{TARGET_DIR}/{ANALYSIS_FILE}" \
              --mode append \
              --stdin
            ]]>
        </implementation>
    </directive>

    <directive name="GEMINI_ANTI_LAZINESS_REINFORCEMENT" priority="CRITICAL">
        <description>LLM 字數流失與內容漂移防範。</description>
        <rules>
            1. 骨架複製法：嚴禁無中生有寫出馬匹分析，必須原封不動照抄 `08_templates_core.md` 中的 9 大 Emoji 標題。
            2. 自我點算：輸出完畢前，內心盤點是否有 9 個不同的標題，缺一不可。
            3. 字數硬性執行：S/A 級馬必須 ≥ 500字。B級 ≥ 350字。D級劣等馬至少需要數據解釋，不能一句帶過 (≥ 300字)。
            4. `[FILL]` 零容忍：如果在生成的最終 markdown 裏發現 `[FILL]`、`{{LLM_FILL}}` 等佔位符，視為不及格，必須重寫補回。
        </rules>
    </directive>
    
    <directive name="NO_RECALCULATION_FROM_FORMGUIDE" priority="CRITICAL">
        <description>必須依賴 Python 的預算，禁止 LLM 自作聰明。</description>
        <rules>
            1. 所有需要數學推導的值（L400 走勢、配備變動、體重趨勢）均已注入在 `Facts.md` 的頭部表格。
            2. 你不得擅自重看純文字 Formguide 來推翻 Facts 中的數值，只能發揮你的「解讀」同「預測」能力。
        </rules>
    </directive>

    <directive name="VERDICT_FORMAT_ANTI_DRIFT_HARDENER" priority="CRITICAL">
        <description>防禦 Verdict (Top 4) 格式崩潰及漂移。</description>
        <rules>
            1. 全場 Top 4 結論必須使用 `🥇🥈🥉🏅` 作為主標籤之清單結構，嚴禁使用表格 (Markdown Table) 或一般數字符號 (1. 2. 3.)。
            2. 第二部分「核心理據」及第三部分「風險」絕對不得壓縮為單行。
            3. 強制輸出防呆：完成 Verdict 之後內心自檢 — `🥇 **第一選**` 和 ` ```csv ` 是否同時存在。若缺失任何元素，即判定違規，重寫。
        </rules>
    </directive>

    <directive name="ANTI_HALLUCINATION_DEEP_VERIFICATION" priority="CRITICAL">
        <description>防禦賽馬分析中常見的 6 種嚴重邏輯幻覺與偏誤 (P39)。</description>
        <rules>
            1. RATING_BLINDNESS（反錨定偏差）：分析時，必須先看 Facts 賽績，然後才看 Rating 與大馬房。嚴禁「先預設這匹馬很強，再找賽績證據支持」的逆向偏誤。
            2. SETTLED ≠ FINISHED（反走位混淆）：Formguide 中的中途走位絕對不等於該場的最終名次！
            3. LAST_10_ZERO_RULE：若賽績包含 `0`，代表該場名次為第 10 名。
            4. TRIAL_AWARENESS（試閘識別）：若最新一次出賽標記為試閘，上仗名次必須自動跳過試閘，引用上一次真實比賽的名次。
            5. ODDS_INDEPENDENCE（反賠率偏差）：你必須先客觀完成評級矩陣，之後才允許參考賠率。嚴禁因為一匹馬是大熱門，就在未經矩陣證明前直接賜予 S 級。
            6. GEMINI_ANTI_NARRATIVE：禁止使用虛構形容詞如「全場最快末段」、「驚人追勢」等誇飾。一切形容詞必須基於 Facts.md 提供的客觀數據。
        </rules>
    </directive>

    <directive name="P37_BATCH_GENERATION_BAN" priority="CRITICAL">
        <description>禁止使用 Python for-loop 自動生成分析報告，防止 LLM 以泛泛之詞塞字過關。</description>
        <rules>
            1. 絕對禁止用 Python script 批量生成分析報告：每場 `Analysis.md` 必須由 LLM 原生撰寫，禁止寫腳本 for-loop 自動灌入模板。
            2. 嚴禁 Generic Filler：「數據正常」、「發揮水準」等沒有針對該場次具體歷史背景的廢話視為違規，必須具備「深度法醫分析」。
            3. 分工明確：Python 只負責抽數、排版與初級數學，所有「戰術推演、賽事法醫、風險定斷」的血肉必須由你原生生成。
        </rules>
    </directive>

    <directive name="P38_VERDICT_LOGIC_HARDENER" priority="CRITICAL">
        <description>強制邏輯防呆，防止排名與評分脫節及單向偏誤。</description>
        <rules>
            1. 排名必須跟隨評級：Top 4 的名次必須嚴格依照其最終「評級矩陣」的等級從高到低排列。等級階梯為：S > S- > A+ > A > A- > B+ > B > B- > C+ > C > C- > D。絕對不允許等級較低的馬排在較高之上！同分情況下，取決於 ✅ 的數量。
            2. 強制反面論證：給予 S 或 A 級的推薦馬匹，必須在「風險」欄位明確列出「最大失敗原因」。
            3. 禁止孤立判斷：任何對馬匹能力的極端評價，必須有至少 2 個數據點支持。
            4. 矩陣排版禁令：評級矩陣必須使用純文字條列 / List 形式。嚴禁使用 Markdown Table 輸出評級矩陣，以免被手機預覽截斷。
        </rules>
    </directive>

</engine_directives>
