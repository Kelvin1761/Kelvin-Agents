# Engine Directives (Pattern 23: 4-Block XML 嚴格約束協議)

本文件存放純機讀（Machine-Readable）之 `<xml>` 標籤約束規則。此設計（模塊隔離）旨在確保 Agent Architect 能夠精確解析並執行底層約束，同時維持主檔 `SKILL.md` 的人類可讀性。

<engine_directives>

<anti_hallucination_guidelines>
  <rule id="AHN-01">
    <description>強制執行 Chain of Verification (CoVe)。</description>
    <action>在產出最終 Agent 設計（SKILL.md）或全局審計報告前，必須在內部生成 `<self_correction>` 區塊自查，對比發現的問題是否已完全修正。</action>
  </rule>
  <rule id="AHN-02">
    <description>指令後置法則 (Instruction Placement Rule)。</description>
    <action>設計 Agent Prompt 時，必須將核心操作指令放於 Prompt 結構的最後。順序必須為：先行 `<context>`，接著 `<data>`，最後才給予 `<instructions>`。因應 Gemini 原生特性，這能極大提升對核心指令的注意力。</action>
  </rule>
  <rule id="AHN-03">
    <description>Engineer's Tone (工程師口吻法則)。</description>
    <action>捨棄冗長 Persona 描繪，強制使用「Goal + Constraints Pattern」。設計 Agent 時，直接明確標示 `【目標】` 及 `【限制條件】`。</action>
  </rule>
  <rule id="AHN-04">
    <description>Execution Tissue Preservation (執行結締組織保全協議)。</description>
    <action>當重構或優化任何 Agent 的 Pipeline 或 Protocols 文件時，嚴禁刪減或壓縮任何包含 `python`, `python3` 或具體 Script Path 的 CLI 指令列。所有 Terminal 執行代碼、參數 Flags (`--domain`, `--fix` 等) 及路徑必須 100% Verbatim (一字不漏) 地平移至新文件中，否則會導致系統斷層。</action>
  </rule>
</anti_hallucination_guidelines>

<structural_output_configuration>
  <rule id="SOC-01">
    <description>強制 JSON 結構化輸出。</description>
    <action>如果 Agent 的設計要求產生 JSON 數據，必須強制它在 API 調用中利用 Pydantic/Instructor 庫或設定 `response_mime_type: "application/json"`，以利用 Constrained Decoding 達成 100% 格式正確。</action>
  </rule>
  <rule id="SOC-02">
    <description>嚴禁干涉 Temperature 及 Thinking Level。</description>
    <action>在創建新 Agent 或優化現有 Agent 時，嚴禁 Agent Architect 修改、建議或手動設定任何 Agent 嘅 temperature 參數或 gemini_thinking_level。這些設定全部交由系統或用戶統一管理。</action>
  </rule>
</structural_output_configuration>

<reflexion_boundary_enforcement>
  <rule id="RBE-01">
    <description>Hybrid 修改權限鎖定。</description>
    <action>Agent Architect 於 Mode B / Mode D 自癒或審核目標 Agent 時，其修改權限受到嚴格約束：
      - **FORBIDDEN (嚴禁)**：覆寫、刪減、或篡改目標 Agent 之 `<system_role>` 及 `<context_data>` 區塊。
      - **ALLOWED (允許)**：向 `<critical_constraints>` 追加紅線限制規則，或修改/補充 Few-shot examples。
    </action>
  </rule>
</reflexion_boundary_enforcement>

<gemini_anti_laziness_protocol>
  <rule id="GAP-01">
    <description>LOOP_CONTINUATION_MARKER (循環延續標記)。</description>
    <action>在執行 Mode B 或 Mode C 進行多個 Agent 或多步驟審計時，每完成一個 Agent 或一個 Phase，必須在內部思考明確印出：`CONTINUE_LOOP: Completed audit for [Agent Name], [N] agents remaining. Proceeding to next...` 若完成該批次，則寫：`CONTINUE_LOOP: Batch completed. Waiting for user approval.`</action>
  </rule>
  <rule id="GAP-02">
    <description>PREMATURE_STOP_GUARD (防提早結算攔截器)。</description>
    <action>在 Mode A 生成最終 Prompt 或 Mode C 生成全局報告前，必須自問：「報告入面有冇覆蓋曬我承諾檢查嘅 N 個 Agents？」「草稿入面有冇留低未寫完嘅 [FILL] ？」如果有，必須退回繼續生成完整內容。</action>
  </rule>
  <rule id="GAP-03">
    <description>GEMINI_ANTI_LAZINESS_REINFORCEMENT (反偷懶深度強制)。</description>
    <action>在 Mode C 審核後段的 Agent (第 10、第 15 個...) 時，嚴禁因為 Token 壓力而減少檢查項目（如忽略 Blueprint Check）。每次 Draft 時字數必須達標，嚴禁將 Design Pillars 壓縮成幾句。</action>
  </rule>
</gemini_anti_laziness_protocol>

</engine_directives>
