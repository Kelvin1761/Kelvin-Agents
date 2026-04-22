# Engine Directives (Pattern 23: 4-Block XML 嚴格約束協議)

本文件存放純機讀（Machine-Readable）之 `<xml>` 標籤約束規則。此設計旨在確保 Agent 能夠精確解析並執行底層約束，防止 Template Drift 同埋強制執行賠率/EV門檻。

<engine_directives>

<anti_hallucination_guidelines>
  <rule id="AHN-01">
    <description>強制執行 Chain of Verification (CoVe)。</description>
    <action>在產出最終分析報告前，必須在內部生成 `<self_correction>` 區塊自查，對比發現的問題是否已完全修正。</action>
  </rule>
  <rule id="AHN-02">
    <description>指令後置法則 (Instruction Placement Rule)。</description>
    <action>推理時，必須將核心操作指令放於思考結構的最後。順序為：先行分析 `<context>`，接著處理 `<data>`，最後才給出 `<decision>` 和 `<output>`。</action>
  </rule>
</anti_hallucination_guidelines>

<structural_output_configuration>
  <rule id="SOC-01">
    <description>強制結構化與 Pydantic 防線。</description>
    <action>若是擷取數據或審查資料，輸出必須嚴格依照預設 JSON Schema 格式；若是分析報告，必須嚴格依照 Markdown 目錄結構，禁止擅自變更表格標題或順序。</action>
  </rule>
  <rule id="SOC-02">
    <description>反惰性指令 (Anti-Laziness Enforcement)。</description>
    <action>嚴禁使用任何省略語（如 `...`、`[略]`、`[見上文]`）。每個分析維度或組合即使與前項相似，也必須重新完整表述邏輯。一旦偵測出 `[FILL]` 佔位符未被實際字句填滿，該報告立刻視為嚴重失敗 (FAIL)。字數門檻：每場賽事分析 ≥1500 字。</action>
  </rule>
</structural_output_configuration>

<workflow_state_integrity>
  <rule id="WSI-01">
    <description>狀態機閘門鎖定 (State Machine Gate)。</description>
    <action>嚴格遵守 [ENTRY CONDITION] 和 [EXIT CONDITION]。在前置條件（如數據包完整性）未達標前，立刻阻斷，不准進入下一步。</action>
  </rule>
</workflow_state_integrity>

<nba_specific_directives>
  <rule id="P31" name="Engine Adaptation">
    <action>
      1. LOOP_CONTINUATION_MARKER: 每場完成後，內部思考必須寫 `CONTINUE_LOOP: Game [N] done...Proceeding to Game [N+1]`。
      2. PREMATURE_STOP_GUARD: 輸出回覆前自問「是否有 Parlay 組合？」。沒有則返回繼續。
      3. EMOJI_COUNT_CHECK: 分析完成後自動清點 Emoji 數量 (🧩, 🔢, 🧠, ⚠️, 💪)，少於模板規定即違規，需立即補全。
    </action>
  </rule>

  <rule id="P33" name="Data Visibility Protocol">
    <action>
      1. EXPLICIT_L10_ARRAY: 每一個 Leg 必須明確印出 `L10 逐場:[數組]`，嚴禁用均值替代或隱藏。
      2. DEEP_ANALYSIS_ALL_COMBOS: Combo 2 等後續組合的 Leg 必須維持與 Combo 1 同等深度 (核心邏輯、最大風險、信心度)。
      3. SEPARATED_COMBO_BLOCKS: 嚴禁將 SGM 兩支 Leg 合併在同一表格內，必須獨立板塊列出。
    </action>
  </rule>

  <rule id="P34" name="Game 4 Hard Split">
    <action>每完成 4 場分析後，強制切割 Session。並呼叫 Python API 將 session state 同步。</action>
  </rule>

  <rule id="P35" name="Anti-Drift Zero Tolerance">
    <action>禁止新增、省略模板欄位或 Emoji 標記。禁止改名 (如「數理引擎」變「數據引擎」)。</action>
  </rule>

  <rule id="P36" name="Anti-Rubber Stamp &amp; Must Respond">
    <action>
      1. 必須明確回應 Data Brief 內 `python_suggestions` 前 5 名 (同意/修改/拒絕)。
      2. LLM 必須提出至少 1 個 Python 未標記的潛在 Edge 項目。
      3. API 數據優先，嚴禁以「此球員不屬該隊伍」為拒絕理由。
    </action>
  </rule>

  <rule id="P37" name="Batch Generation Ban">
    <action>禁止使用 Python for-loop 腳本自動生成批量 Markdown 報告。必須一場一場逐次獨立分析及產出。嚴禁 Generic Fillers。</action>
  </rule>

  <rule id="P40" name="Milestones Source First">
    <action>Sportsbet 提取為主。如果遇到需要手動介入的情況，只准去 Sportsbet 官方網頁的 `Player Props` Tabs (`Player Points`, `Player Rebounds`, `Player Assists`)，嚴格比對盤口。</action>
  </rule>

  <rule id="P42" name="Sportsbet Milestones Only">
    <action>全面封殺所有 `Under` 盤口推介。只准推介 `X+` (Over) 階梯盤。</action>
  </rule>

  <rule id="P43" name="SGM Odds &amp; EV Enforcement">
    <action>
      1. 組合 1 (🛡️ 穩膽 SGM)：每腿 L10 命中率必須 ≥70%、Edge 必須 ≥0%，且全組賠率必須 ≥ 2.0x。若含有高波幅的「神經刀」球員，必須無條件剔除！
      2. 組合 2 (🔥 +EV 價值膽)：每腿 Edge 必須 ≥3%，全組賠率必須 ≥ 3.0x，目標朝向 5x。如有任何 Negative EV 或低於要求之賠率，必須重新選擇。
      3. 組合 3 (💎 高倍率進取型)：每腿 Edge 必須 ≥0%，全組賠率必須 ≥ 8.0x，可包含高回報風險項目。
      4. 組合 X (💣 Value Bomb)：條件觸發。只有當系統掃描到單一盤口 Edge ≥ 10% 並通過 MC Edge ≥5% 或 L5/L10 一致性檢查時，才獨立抽出展示。
      5. Team market (ML / Spread / Total) 不可混入 player milestone SGM 自動組合。
      6. 同隊 PTS Over 最多 2 腿，避免球權天花板衝突。
    </action>
  </rule>

  <rule id="P44" name="Season Phase and L10 Order">
    <action>
      1. 報告必須明確顯示 `season_phase`，可用值只限 EARLY_SEASON / MID_SEASON / LATE_REGULAR / PLAY_IN / PLAYOFFS。
      2. 報告必須明確顯示 `L10_ORDER: newest_first`。
      3. L3 必須使用 L10 前 3 項，L5 必須使用 L10 前 5 項，嚴禁反向讀取近期走勢。
    </action>
  </rule>

  <rule id="P19V6" name="Safe Writer Protocol">
    <action>
      遵循 GEMINI.md 嘅 Google Drive 寫入防護協議。嚴禁使用 write_to_file。
      小型編輯 (少於 50 行): 允許使用 replace_file_content / multi_replace_file_content。
      新建或覆蓋整個檔案: 透過 run_command 使用 safe_file_writer 或 PowerShell/shell 寫入。
      路徑: .agents/scripts/safe_file_writer.py (相對路徑，跨平台適用)
    </action>
  </rule>

  <rule id="INJURY_GUARD" name="Injury Guard Protocol">
    <action>讀取前必須核對 status。若遇上頂級球星，分析前絕對要有常識判斷其是否已報銷，嚴防 Hallucination。</action>
  </rule>

  <rule id="P50" name="Anti-Padding Zero Tolerance">
    <action>
      1. 嚴禁喺同一段落內重複任何句子。每個句子都必須提供新信息。
      2. 嚴禁使用 "Player A/B/C" 等 placeholder — 必須使用真實球員名。
      3. L10 數據必須來自 Data Brief JSON 或 Sportsbet odds JSON，嚴禁自創假數據。
      4. 「這包含了各種盤口對照」、「能夠提供更清楚的賭注建議」等通用填充句一律視為嚴重違規。
      5. 若被 validate_nba_output.py 偵測到灌水行為，整份報告將被 BLOCK。
      6. 字數要求應透過增加分析深度（更多球員、更多情境分析）嚟達成，而唔係重複同一句話。
    </action>
  </rule>

  <rule id="P51" name="Python-Generated Skeleton Mandatory">
    <action>
      所有 Full_Analysis.md 必須基於 generate_nba_reports.py 生成嘅 skeleton report。
      Skeleton 已包含所有數學數據（賠率/Edge/Kelly/組合選擇/Monte Carlo）。
      LLM 只負責填寫 [FILL] 欄位（核心邏輯/角色/趨勢解讀/防守對位分析）。
      嚴禁自行從零建立任何分析報告。
      若輸出缺少 「Python Auto-Selection」、「8-Factor」 等 Python 簽名標記，
      即判定為非法跳過 pipeline，報告無效。
    </action>
  </rule>

  <rule id="P52" name="Post-Generation Firewall (validate_nba_output.py)">
    <action>
      每份 Game_*_Full_Analysis.md 生成後，必須執行:
      python .agents/skills/nba/nba_wong_choi/scripts/validate_nba_output.py {FILE_PATH}
      任何 ❌ BLOCKED 結果 → 必須立即重寫該報告。
      嚴禁提交未通過防火牆檢查嘅報告。
    </action>
  </rule>
</nba_specific_directives>

</engine_directives>
