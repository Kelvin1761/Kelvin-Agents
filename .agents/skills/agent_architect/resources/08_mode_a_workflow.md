# Mode A: 新建 Agent 流程

You must follow these steps strictly in order. **Do not generate the final prompt until the Discovery phase is complete.**

## Step 1: Adaptive Discovery (Dynamic — NOT Fixed Questions)
Do NOT ask all questions at once. Progress through phases sequentially, waiting for user response after each. **Questions are NEVER pre-written templates** — you MUST generate them dynamically based on the user's previous answers, domain, and the gaps you still need to fill before you can design.

### Discovery Principles
1. **Listen First**: Parse the user's initial request carefully. Extract domain signals, scale hints, complexity indicators, and any constraints already implied.
2. **Ask What You Don't Know**: Only ask about gaps. If the user already told you the agent chains with another agent — don't ask about chaining again.
3. **Show Consequences**: Every question should reveal an architectural decision. Use Brainstorming Skill format: `[P0]/Question/Why This Matters/Options table/If Not Specified`.
4. **Adapt Depth to Complexity**: Simple agents (single-purpose, standalone) may need only 2-3 questions total. Complex pipeline agents may need 5-6 across multiple phases. Match depth to scope.

### Phase Progression Guide (flexible — adapt as needed)

**Phase 1 — 理解意圖 (1-2 題):**
Start with open-ended understanding. Your goal is to grasp the *problem space*, not just the feature list. Typical first question: "What problem does this agent solve?" But adapt — if the user already described the problem in their request, skip ahead and ask about scope boundaries or success criteria instead.

**Phase 2 — 設計探索 (動態生成):**
Based on Phase 1 answers, identify the **2-3 biggest design decisions** that need user input. These vary by domain:
- For analysis agents → ask about data sources, output format, quality gates
- For automation agents → ask about trigger conditions, error recovery, human-in-the-loop needs
- For pipeline agents → ask about upstream/downstream contracts, batch vs streaming, checkpoint frequency
- For utility agents → ask about scope boundaries, what it should NOT do

Present each decision with an Options table (≥2 options + Pros/Cons/Best For). Recommend a default.

**Phase 3 — 族群配對 (自動 + contextual):**
`run_command agent_health_scanner.py --list-all` to get the agent registry. Match the user's described needs against existing agents by domain keywords. Show top 2-3 similar agents with what design patterns they use. Ask: "Want to use any of these as a design foundation, or start fresh?" If no similar agents exist, say so and move on.

**Phase 4 — 設計確認:**
Synthesize everything into a concise Design Summary (Name/Type/Chaining/Reference/Key Patterns/Python Scripts needed). Present it and wait for user confirmation before entering Step 2. If the user corrects anything, update and re-confirm.

### Anti-Patterns for Discovery
- ❌ Asking the same 5 fixed questions regardless of context
- ❌ Asking questions the user already answered in their initial request
- ❌ Asking low-value questions ("Who is the target audience?") when the context is obvious
- ✅ Generating questions that directly impact architectural decisions
- ✅ Skipping phases when sufficient information is already available

## Step 2: Modular Design & Draft Generation
Once you have the context, synthesize the user's answers and break down the internal configuration into six design pillars. Consult `resources/ecosystem_reference.md` to ensure the new agent is consistent with the existing Antigravity ecosystem.

**Blueprint 能力路由器(草擬前必須執行):**
查閱 `resources/04_blueprint_integration_guide.md` 嘅能力矩陣,將新 agent 嘅需求配對到現有藍圖:
- 若 agent 需要品質審查 → 參考 B2/B10 嘅多 Agent 審查 + 信心分數
- 若 agent 需要分階段工作流 → 參考 B7 嘅 7 階段或 B11 嘅 8 階段模式
- 若 agent 需要代碼生成/修改 → 參考 B1 嘅功能保全原則
- 若 agent 需要 UI 設計 → 參考 B8 嘅反 AI-slop 美學指引
- 若 agent 需要持續改善 → 參考 B17 嘅迭代循環 + completion promise
- 若 agent 需要安全檢查 → 參考 B13 嘅模式偵測
- 若 agent 需要 eval/基準測試 → 參考 B12 嘅 eval 系統
記錄設計文檔中參考咗邊啲藍圖。

Use these pillars to write a comprehensive, professional system prompt:
1. **Persona**: Define the tone, expertise level, and personality traits.
2. **Scope**: Clearly state what the agent must do, and draw a hard line on what it is *forbidden* from doing.
3. **Knowledge & Tools**: Identify any required data sources, logic frameworks, or tools (e.g., Web Search, Terminal, Python Interpreter, File System).
4. **Interaction Logic**: Specify how the agent should reason. Detail its step-by-step thinking process (e.g., using thinking blocks), how it handles missing information, and its ambiguity resolution protocol.
5. **Architectural Efficiency (Prompt Modularization)**: To prevent LLM memory overload and improve reasoning latency, the main `SKILL.md` must remain lean. If the system instructions, knowledge context, or templates are massive (e.g., >150 lines), you MUST split them into separate files (e.g., `resources/01_context.md`, `resources/02_engine.md`) and simply instruct the agent to use `view_file` to read them as Step 1 of its Interaction Logic.
6. **Python-First Tool Offloading (Pattern 22)**: Offload ALL deterministic work (math, format conversion, file scanning, template filling, data validation) to Python `scripts/`. Apply the Python-First Decision Matrix: "Can this step achieve 100% accuracy with a script?" If YES → build a script. LLM context is reserved for judgment, reasoning, and creative analysis only.

## Step 3: Robustness Checklist (MANDATORY)
Review draft against `resources/design_patterns.md` (Patterns 8-28). Verify:
1. **Loop Prevention + browser_subagent Ban**: browser_subagent is GLOBALLY BANNED. ALL data extraction → Python scripts. Max 3 retries then ask user.
2. **Chunking**: Large data → bounded chunks?
3. **Example Completeness**: Output examples show FULL realistic pattern?
4. **Self-Testing Phase**: Agent must verify its own output before declaring complete.
5. **Failure Warnings**: Explicit `⚠️ CRITICAL` for known failure modes?
6. **Ecosystem Conventions**: YAML frontmatter, resource naming, language, anti-laziness protocol.
7. **Battle-Tested Patterns**: P8-P22 checked — batch isolation, session recovery, checkpoints, quality gates, cross-platform, confidence scoring, Python offloading.
8. **Python Offloading Audit**: Every deterministic step reviewed against P22. Math/template/format/scan → script, not LLM.
9. **🆕 Gemini Optimization (P23)**: Instruction placement (last), Goal+Constraints pattern, CoVe self-check, Temperature in frontmatter?
10. **🆕 State Machine (P24)**: DoeS the agent have explicit state transitions with entry/exit conditions?
11. **🆕 Execution Journal (P26)**: Does the agent write structured logs per major step?
12. **🆕 Version Control (P27)**: Is `resources/archive/` directory present for snapshots?
13. **🆕 Sports Analytics (P28)**: If this is a Wong Choi agent — does it use Python scripts for ALL quant work? EV formula? Kelly? TimeSeriesSplit?

## Step 4: Iteration & Pre-flight Testing
Present the drafted configuration to the user. Explicitly ask for feedback:
- *「呢個設計有冇準確捕捉到你需要嘅行為?」*
- *「有冇任何 edge case 或約束需要收緊?」*
Continually refine the instructions based on their feedback until they approve the final design.
